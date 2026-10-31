import { Folder, FolderTree } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { useMoveQuestions } from "@/api/hooks/bank";
import { useSubjectTree } from "@/api/hooks/taxonomy";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";

export interface MoveLessonDialogProps {
  subjectId: string;
  questionIds: string[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export function MoveLessonDialog({
  subjectId,
  questionIds,
  open,
  onOpenChange,
  onSuccess,
}: MoveLessonDialogProps) {
  const { t } = useTranslation();
  const treeQuery = useSubjectTree(open ? subjectId : null);
  const moveMut = useMoveQuestions();
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);

  const handleMove = async () => {
    if (!selectedLessonId) return;
    try {
      const res = await moveMut.mutateAsync({
        ids: questionIds,
        lesson_id: selectedLessonId,
      });
      toast.success(t("bank.bulk.moveSuccess", { count: res.moved }));
      onSuccess();
      onOpenChange(false);
    } catch {
      toast.error(t("review.errors.action"));
    }
  };

  const chapters = treeQuery.data?.chapters ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="move-lesson-dialog" className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("bank.bulk.moveToLesson")}</DialogTitle>
          <DialogDescription>
            {t("bank.bulk.selected", { count: questionIds.length })}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-80 overflow-y-auto py-2">
          {treeQuery.isLoading ? (
            <div className="flex flex-col gap-2 p-2">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-full" />
            </div>
          ) : chapters.length === 0 ? (
            <p className="text-muted-foreground p-4 text-center text-sm">
              {t("bank.taxonomy.emptyTree")}
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {chapters.map((chapter) => (
                <div key={chapter.id} className="flex flex-col gap-1">
                  <div className="text-foreground flex items-center gap-1.5 px-2 py-1 text-xs font-semibold">
                    <Folder className="text-muted-foreground size-3.5" />
                    <span>{chapter.title}</span>
                  </div>
                  <div className="ms-4 flex flex-col gap-1 border-s ps-2">
                    {chapter.lessons.length === 0 ? (
                      <span className="text-muted-foreground py-1 text-xs italic">
                        {t("bank.question.noLesson")}
                      </span>
                    ) : (
                      chapter.lessons.map((lesson) => (
                        <button
                          key={lesson.id}
                          type="button"
                          onClick={() => {
                            setSelectedLessonId(lesson.id);
                          }}
                          className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-start text-xs transition-colors ${
                            selectedLessonId === lesson.id
                              ? "bg-primary text-primary-foreground font-medium"
                              : "hover:bg-muted text-foreground"
                          }`}
                        >
                          <FolderTree className="size-3.5 shrink-0 opacity-70" />
                          <span>{lesson.title}</span>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
            disabled={moveMut.isPending}
          >
            {t("bank.taxonomy.cancel")}
          </Button>
          <Button
            onClick={() => {
              void handleMove();
            }}
            disabled={!selectedLessonId || moveMut.isPending}
          >
            {moveMut.isPending ? "..." : t("bank.bulk.moveToLesson")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
