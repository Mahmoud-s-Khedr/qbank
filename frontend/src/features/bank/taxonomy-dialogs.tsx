import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import {
  type ChapterTree,
  type LessonOut,
  useCreateSubject,
  useMergeChapter,
  useMergeLesson,
  useUpdateLesson,
  useUpdateSubject,
} from "@/api/hooks/taxonomy";
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

export function SubjectDialog({
  open,
  onOpenChange,
  subjectToEdit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  subjectToEdit?: {
    id: string;
    name: string;
    grade?: string | null;
    language?: "ar" | "en";
  } | null;
}) {
  const { t } = useTranslation();
  const createMut = useCreateSubject();
  const updateMut = useUpdateSubject();

  const [name, setName] = useState(subjectToEdit?.name ?? "");
  const [grade, setGrade] = useState(subjectToEdit?.grade ?? "");
  const [language, setLanguage] = useState<"ar" | "en">(
    subjectToEdit?.language ?? "ar",
  );

  const isEditing = Boolean(subjectToEdit);

  const handleSubmit = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    try {
      if (isEditing && subjectToEdit) {
        await updateMut.mutateAsync({
          id: subjectToEdit.id,
          data: {
            name: name.trim(),
            grade: grade.trim() || null,
            language,
          },
        });
      } else {
        await createMut.mutateAsync({
          name: name.trim(),
          grade: grade.trim() || null,
          language,
        });
      }
      onOpenChange(false);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="subject-dialog" className="sm:max-w-md">
        <form
          onSubmit={(e) => {
            void handleSubmit(e);
          }}
        >
          <DialogHeader>
            <DialogTitle>
              {isEditing
                ? t("bank.taxonomy.renameSubject")
                : t("bank.taxonomy.newSubject")}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-4 py-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="subject-name">
                {t("bank.taxonomy.subjectName")}
              </Label>
              <Input
                id="subject-name"
                data-testid="subject-name-input"
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                }}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="subject-grade">
                {t("bank.taxonomy.subjectGrade")}
              </Label>
              <Input
                id="subject-grade"
                value={grade}
                onChange={(e) => {
                  setGrade(e.target.value);
                }}
                placeholder="Grade 10"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="subject-language">
                {t("bank.taxonomy.subjectLanguage")}
              </Label>
              <select
                id="subject-language"
                value={language}
                onChange={(e) => {
                  setLanguage(e.target.value as "ar" | "en");
                }}
                className="border-input bg-background h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs"
              >
                <option value="ar">العربية (Arabic)</option>
                <option value="en">English</option>
              </select>
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                onOpenChange(false);
              }}
            >
              {t("bank.taxonomy.cancel")}
            </Button>
            <Button
              type="submit"
              data-testid="subject-submit-btn"
              disabled={createMut.isPending || updateMut.isPending}
            >
              {t("bank.taxonomy.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function MergeDialog({
  open,
  onOpenChange,
  sourceType,
  sourceItem,
  availableTargets,
  subjectId,
  questionCount,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceType: "chapter" | "lesson";
  sourceItem: { id: string; title: string };
  availableTargets: { id: string; title: string }[];
  subjectId: string;
  questionCount: number;
}) {
  const { t } = useTranslation();
  const mergeChapterMut = useMergeChapter();
  const mergeLessonMut = useMergeLesson();
  const [targetId, setTargetId] = useState<string>("");

  const handleMerge = async () => {
    if (!targetId) return;
    try {
      if (sourceType === "chapter") {
        await mergeChapterMut.mutateAsync({
          id: sourceItem.id,
          subjectId,
          data: { into_chapter_id: targetId },
        });
      } else {
        await mergeLessonMut.mutateAsync({
          id: sourceItem.id,
          subjectId,
          data: { into_lesson_id: targetId },
        });
      }
      onOpenChange(false);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  const selectedTarget = availableTargets.find((t) => t.id === targetId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="merge-confirm-dialog" className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("bank.taxonomy.mergeConfirmTitle")}</DialogTitle>
          <DialogDescription>
            {sourceType === "chapter"
              ? t("bank.taxonomy.mergeChapterConfirm", {
                  source: sourceItem.title,
                  target: selectedTarget ? selectedTarget.title : "...",
                  count: questionCount,
                })
              : t("bank.taxonomy.mergeLessonConfirm", {
                  source: sourceItem.title,
                  target: selectedTarget ? selectedTarget.title : "...",
                  count: questionCount,
                })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 py-3">
          <Label htmlFor="merge-target-select">
            {sourceType === "chapter"
              ? t("bank.taxonomy.targetChapter")
              : t("bank.taxonomy.targetLesson")}
          </Label>
          <select
            id="merge-target-select"
            data-testid="merge-target-select"
            value={targetId}
            onChange={(e) => {
              setTargetId(e.target.value);
            }}
            className="border-input bg-background h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs"
          >
            <option value="">-- Choose target --</option>
            {availableTargets.map((tgt) => (
              <option key={tgt.id} value={tgt.id}>
                {tgt.title}
              </option>
            ))}
          </select>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            {t("bank.taxonomy.cancel")}
          </Button>
          <Button
            data-testid="merge-confirm-btn"
            onClick={() => {
              void handleMerge();
            }}
            disabled={
              !targetId || mergeChapterMut.isPending || mergeLessonMut.isPending
            }
          >
            {t("bank.taxonomy.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function MoveLessonChapterDialog({
  open,
  onOpenChange,
  lesson,
  chapters,
  subjectId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lesson: LessonOut;
  chapters: ChapterTree[];
  subjectId: string;
}) {
  const { t } = useTranslation();
  const updateLessonMut = useUpdateLesson();
  const [targetChapterId, setTargetChapterId] = useState<string>("");

  const availableChapters = chapters.filter((c) => c.id !== lesson.chapter_id);

  const handleMove = async () => {
    if (!targetChapterId) return;
    try {
      await updateLessonMut.mutateAsync({
        id: lesson.id,
        subjectId,
        data: { chapter_id: targetChapterId },
      });
      onOpenChange(false);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="move-lesson-chapter-dialog"
        className="sm:max-w-md"
      >
        <DialogHeader>
          <DialogTitle>{t("bank.taxonomy.moveLesson")}</DialogTitle>
          <DialogDescription>{lesson.title}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 py-3">
          <Label htmlFor="target-chapter-select">
            {t("bank.taxonomy.targetChapter")}
          </Label>
          <select
            id="target-chapter-select"
            value={targetChapterId}
            onChange={(e) => {
              setTargetChapterId(e.target.value);
            }}
            className="border-input bg-background h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs"
          >
            <option value="">-- Choose target chapter --</option>
            {availableChapters.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            {t("bank.taxonomy.cancel")}
          </Button>
          <Button
            onClick={() => {
              void handleMove();
            }}
            disabled={!targetChapterId || updateLessonMut.isPending}
          >
            {t("bank.taxonomy.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
