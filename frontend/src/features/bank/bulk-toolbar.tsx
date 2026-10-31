import {
  AlertCircle,
  Check,
  Edit,
  FolderTree,
  PlusCircle,
  X,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { type BulkOut, useBulkQuestions } from "@/api/hooks/bank";
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
import { AddToExamDialog } from "@/features/bank/add-to-exam-dialog";
import { MoveLessonDialog } from "@/features/bank/move-lesson-dialog";

export interface BulkToolbarProps {
  selectedIds: Set<string>;
  allSelected: boolean;
  onToggleSelectAll: () => void;
  onClearSelection: () => void;
  subjectId: string;
  canEdit: boolean;
}

export function BulkToolbar({
  selectedIds,
  allSelected,
  onToggleSelectAll,
  onClearSelection,
  subjectId,
  canEdit,
}: BulkToolbarProps) {
  const { t } = useTranslation();
  const bulkMut = useBulkQuestions();

  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [metaOpen, setMetaOpen] = useState(false);
  const [difficulty, setDifficulty] = useState<string>("");
  const [tagsAdd, setTagsAdd] = useState("");
  const [tagsRemove, setTagsRemove] = useState("");
  const [moveOpen, setMoveOpen] = useState(false);
  const [examOpen, setExamOpen] = useState(false);
  const [partialErrors, setPartialErrors] = useState<string | null>(null);

  if (selectedIds.size === 0) return null;

  const ids = Array.from(selectedIds);

  const handleBulkResult = (result: BulkOut, successMsg: string) => {
    if (result.succeeded > 0) {
      toast.success(successMsg);
    }
    if (result.failed > 0) {
      const failedItems = result.results.filter((r) => !r.ok);
      const details = failedItems
        .map((r) => `${r.id}${r.code ? ` (${r.code})` : ""}`)
        .join(", ");
      const errMsg = t("bank.bulk.partialFailure", {
        count: result.failed,
        details,
      });
      setPartialErrors(details);
      toast.error(errMsg);
    } else {
      setPartialErrors(null);
      onClearSelection();
    }
  };

  const handleApprove = async () => {
    try {
      const res = await bulkMut.mutateAsync({
        action: "approve",
        ids,
      });
      handleBulkResult(
        res,
        t("bank.bulk.approveSuccess", { count: res.succeeded }),
      );
    } catch {
      toast.error(t("review.errors.action"));
    }
  };

  const handleRejectConfirm = async () => {
    try {
      const res = await bulkMut.mutateAsync({
        action: "reject",
        ids,
        reason: rejectReason.trim() ? rejectReason.trim() : null,
      });
      setRejectOpen(false);
      setRejectReason("");
      handleBulkResult(
        res,
        t("bank.bulk.rejectSuccess", { count: res.succeeded }),
      );
    } catch {
      toast.error(t("review.errors.action"));
    }
  };

  const handleMetadataConfirm = async () => {
    try {
      const add = tagsAdd
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const remove = tagsRemove
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const diffNum = difficulty ? Number(difficulty) : undefined;

      const res = await bulkMut.mutateAsync({
        action: "set_metadata",
        ids,
        metadata: {
          difficulty: diffNum ?? null,
          tags_add: add,
          tags_remove: remove,
        },
      });
      setMetaOpen(false);
      setDifficulty("");
      setTagsAdd("");
      setTagsRemove("");
      handleBulkResult(
        res,
        t("bank.bulk.metadataSuccess", { count: res.succeeded }),
      );
    } catch {
      toast.error(t("review.errors.action"));
    }
  };

  return (
    <>
      <div
        data-testid="bank-bulk-toolbar"
        className="bg-card/95 sticky top-2 z-30 flex flex-wrap items-center justify-between gap-3 rounded-lg border p-3 shadow-md backdrop-blur-sm"
      >
        <div className="flex items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={onToggleSelectAll}
              className="accent-primary size-4 rounded-xs"
            />
            <span className="text-foreground text-xs font-semibold">
              {t("bank.bulk.selectAll")}
            </span>
          </label>
          <span className="text-muted-foreground text-xs">
            ({t("bank.bulk.selected", { count: selectedIds.size })})
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearSelection}
            className="text-muted-foreground hover:text-foreground h-7 px-2 text-xs"
          >
            {t("bank.bulk.clearSelection")}
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Add to Exam: available to everyone */}
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setExamOpen(true);
            }}
            className="h-8 gap-1.5 text-xs"
          >
            <PlusCircle className="size-3.5" />
            <span>{t("bank.bulk.addToExam")}</span>
          </Button>

          {/* Editor-only bulk actions */}
          {canEdit && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setMoveOpen(true);
                }}
                className="h-8 gap-1.5 text-xs"
              >
                <FolderTree className="size-3.5" />
                <span>{t("bank.bulk.moveToLesson")}</span>
              </Button>

              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setMetaOpen(true);
                }}
                className="h-8 gap-1.5 text-xs"
              >
                <Edit className="size-3.5" />
                <span>{t("bank.bulk.setMetadata")}</span>
              </Button>

              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setRejectOpen(true);
                }}
                className="text-destructive hover:bg-destructive/10 hover:text-destructive h-8 gap-1.5 text-xs"
              >
                <X className="size-3.5" />
                <span>{t("bank.bulk.reject")}</span>
              </Button>

              <Button
                size="sm"
                onClick={() => {
                  void handleApprove();
                }}
                disabled={bulkMut.isPending}
                className="h-8 gap-1.5 text-xs font-semibold"
              >
                <Check className="size-3.5" />
                <span>{t("bank.bulk.approve")}</span>
              </Button>
            </>
          )}
        </div>
      </div>

      {partialErrors && (
        <div
          data-testid="bulk-partial-failure-alert"
          className="border-destructive/40 bg-destructive/10 text-destructive flex items-start justify-between gap-3 rounded-lg border p-3 text-xs"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0" />
            <span>
              {t("bank.bulk.partialFailure", {
                count: 1,
                details: partialErrors,
              })}
            </span>
          </div>
          <button
            type="button"
            onClick={() => {
              setPartialErrors(null);
            }}
            className="opacity-70 hover:opacity-100"
            aria-label="Dismiss errors"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      {/* Reject Reason Dialog */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent data-testid="bulk-reject-dialog" className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("bank.bulk.reject")}</DialogTitle>
            <DialogDescription>
              {t("bank.bulk.selected", { count: selectedIds.size })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2 py-2">
            <Label htmlFor="bulk-reject-reason">
              {t("bank.bulk.rejectPrompt")}
            </Label>
            <Input
              id="bulk-reject-reason"
              value={rejectReason}
              onChange={(e) => {
                setRejectReason(e.target.value);
              }}
              placeholder="..."
            />
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => {
                setRejectOpen(false);
              }}
            >
              {t("bank.taxonomy.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                void handleRejectConfirm();
              }}
              disabled={bulkMut.isPending}
            >
              {bulkMut.isPending ? "..." : t("bank.bulk.reject")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Bulk Metadata Dialog */}
      <Dialog open={metaOpen} onOpenChange={setMetaOpen}>
        <DialogContent
          data-testid="bulk-metadata-dialog"
          className="sm:max-w-md"
        >
          <DialogHeader>
            <DialogTitle>{t("bank.bulk.setMetadata")}</DialogTitle>
            <DialogDescription>
              {t("bank.bulk.selected", { count: selectedIds.size })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="meta-difficulty">
                {t("bank.bulk.difficultyLabel")}
              </Label>
              <select
                id="meta-difficulty"
                value={difficulty}
                onChange={(e) => {
                  setDifficulty(e.target.value);
                }}
                className="border-input bg-background focus-visible:ring-ring h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs focus-visible:ring-1 focus-visible:outline-none"
              >
                <option value="">{t("bank.bulk.keepDifficulty")}</option>
                {[1, 2, 3, 4, 5].map((lvl) => (
                  <option key={lvl} value={lvl}>
                    {lvl}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="meta-tags-add">
                {t("bank.bulk.addTagsLabel")}
              </Label>
              <Input
                id="meta-tags-add"
                placeholder="algebra, exam2026"
                value={tagsAdd}
                onChange={(e) => {
                  setTagsAdd(e.target.value);
                }}
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="meta-tags-remove">
                {t("bank.bulk.removeTagsLabel")}
              </Label>
              <Input
                id="meta-tags-remove"
                placeholder="old_tag"
                value={tagsRemove}
                onChange={(e) => {
                  setTagsRemove(e.target.value);
                }}
              />
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              variant="outline"
              onClick={() => {
                setMetaOpen(false);
              }}
            >
              {t("bank.taxonomy.cancel")}
            </Button>
            <Button
              onClick={() => {
                void handleMetadataConfirm();
              }}
              disabled={bulkMut.isPending}
            >
              {bulkMut.isPending ? "..." : t("bank.taxonomy.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Move to Lesson Dialog */}
      <MoveLessonDialog
        subjectId={subjectId}
        questionIds={ids}
        open={moveOpen}
        onOpenChange={setMoveOpen}
        onSuccess={onClearSelection}
      />

      {/* Add to Exam Dialog */}
      <AddToExamDialog
        questionIds={ids}
        open={examOpen}
        onOpenChange={setExamOpen}
        onSuccess={onClearSelection}
      />
    </>
  );
}
