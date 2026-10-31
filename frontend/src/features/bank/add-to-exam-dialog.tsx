import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useAddItemsToExam, useDraftExams } from "@/api/hooks/bank";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";

export interface AddToExamDialogProps {
  questionIds: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export function AddToExamDialog({
  questionIds,
  open,
  onOpenChange,
  onSuccess,
}: AddToExamDialogProps) {
  const { t } = useTranslation();
  const draftExamsQuery = useDraftExams();
  const addItemsMut = useAddItemsToExam();

  const [selectedExamId, setSelectedExamId] = useState<string>("");
  const [points, setPoints] = useState<number>(1);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [hasAdded, setHasAdded] = useState(false);

  const draftExams = draftExamsQuery.data?.items ?? [];

  const handleAdd = async () => {
    if (!selectedExamId) return;
    try {
      const examDetail = await addItemsMut.mutateAsync({
        examId: selectedExamId,
        data: {
          points,
          question_ids: questionIds,
        },
      });

      // Detect response warnings
      const detectedWarnings: string[] = [];
      const rawWarnings = (examDetail as { warnings?: unknown }).warnings;
      if (Array.isArray(rawWarnings)) {
        for (const w of rawWarnings) {
          if (typeof w === "string") detectedWarnings.push(w);
        }
      }

      // Check if extra items (like a stimulus group) were pulled in
      const allItemQuestionIds = new Set<string>();
      let hasStimulus = false;
      for (const section of examDetail.sections) {
        for (const item of section.items) {
          allItemQuestionIds.add(item.question_id);
          if (item.stimulus) {
            hasStimulus = true;
          }
        }
      }

      const extraItemsCount = allItemQuestionIds.size - questionIds.length;
      if (extraItemsCount > 0 || hasStimulus) {
        detectedWarnings.push(t("bank.addToExam.stimulusWarning"));
      }

      if (detectedWarnings.length > 0) {
        setWarnings(detectedWarnings);
        setHasAdded(true);
        toast.warning(detectedWarnings[0]);
      } else {
        toast.success(t("bank.addToExam.success"));
        onSuccess();
        onOpenChange(false);
      }
    } catch {
      toast.error(t("review.errors.action"));
    }
  };

  const handleClose = () => {
    if (hasAdded) {
      onSuccess();
    }
    setWarnings([]);
    setHasAdded(false);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent data-testid="add-to-exam-dialog" className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("bank.addToExam.title")}</DialogTitle>
          <DialogDescription>
            {t("bank.addToExam.description", { count: questionIds.length })}
          </DialogDescription>
        </DialogHeader>

        {warnings.length > 0 && (
          <div
            data-testid="add-to-exam-warnings"
            className="flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-900 dark:text-amber-200"
          >
            <AlertCircle className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <div className="flex flex-col gap-1">
              {warnings.map((w, idx) => (
                <p key={idx} className="font-medium">
                  {w}
                </p>
              ))}
            </div>
          </div>
        )}

        {!hasAdded && (
          <div className="flex flex-col gap-4 py-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="exam-select">
                {t("bank.addToExam.examSelect")}
              </Label>
              {draftExamsQuery.isLoading ? (
                <Skeleton className="h-9 w-full" />
              ) : draftExams.length === 0 ? (
                <p className="text-muted-foreground text-xs">
                  {t("bank.addToExam.noDrafts")}
                </p>
              ) : (
                <select
                  id="exam-select"
                  data-testid="exam-select"
                  value={selectedExamId}
                  onChange={(e) => {
                    setSelectedExamId(e.target.value);
                  }}
                  className="border-input bg-background focus-visible:ring-ring h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs focus-visible:ring-1 focus-visible:outline-none"
                >
                  <option value="">{t("bank.addToExam.examSelect")}</option>
                  {draftExams.map((exam) => (
                    <option key={exam.id} value={exam.id}>
                      {exam.title} ({exam.question_count} questions)
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="points-input">
                {t("bank.addToExam.pointsPerQuestion")}
              </Label>
              <Input
                id="points-input"
                type="number"
                min={1}
                max={100}
                value={points}
                onChange={(e) => {
                  setPoints(Math.max(1, Number(e.target.value) || 1));
                }}
                className="h-9"
              />
            </div>
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={handleClose}>
            {hasAdded ? t("bank.drawer.close") : t("bank.taxonomy.cancel")}
          </Button>
          {!hasAdded && (
            <Button
              onClick={() => {
                void handleAdd();
              }}
              disabled={!selectedExamId || addItemsMut.isPending}
            >
              {addItemsMut.isPending ? "..." : t("bank.addToExam.add")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
