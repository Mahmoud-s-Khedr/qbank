import {
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronRight,
  Edit2,
  Folder,
  FolderTree,
  GitMerge,
  MoveRight,
  Plus,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import type { BankStatsOut } from "@/api/hooks/bank";
import {
  type ChapterTree,
  type LessonOut,
  useCreateLesson,
  useDeleteChapter,
  useDeleteLesson,
  useReorderChapters,
  useReorderLessons,
  useUpdateChapter,
  useUpdateLesson,
} from "@/api/hooks/taxonomy";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  MergeDialog,
  MoveLessonChapterDialog,
} from "@/features/bank/taxonomy-dialogs";

export interface TaxonomyTreeProps {
  chapters: ChapterTree[];
  subjectId: string;
  stats?: BankStatsOut | null;
  canEdit: boolean;
}

export function TaxonomyTree({
  chapters,
  subjectId,
  stats,
  canEdit,
}: TaxonomyTreeProps) {
  const { t } = useTranslation();

  const createLessonMut = useCreateLesson();
  const updateChapterMut = useUpdateChapter();
  const updateLessonMut = useUpdateLesson();
  const deleteChapterMut = useDeleteChapter();
  const deleteLessonMut = useDeleteLesson();
  const reorderChaptersMut = useReorderChapters();
  const reorderLessonsMut = useReorderLessons();

  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(
    new Set(chapters.map((c) => c.id)),
  );

  // Inline rename state
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  // Add lesson state: chapterId where adding lesson is active
  const [addingLessonChapterId, setAddingLessonChapterId] = useState<
    string | null
  >(null);
  const [newLessonTitle, setNewLessonTitle] = useState("");

  // Merge modal state
  const [mergeState, setMergeState] = useState<{
    open: boolean;
    sourceType: "chapter" | "lesson";
    sourceItem: { id: string; title: string };
    availableTargets: { id: string; title: string }[];
    questionCount: number;
  }>({
    open: false,
    sourceType: "chapter",
    sourceItem: { id: "", title: "" },
    availableTargets: [],
    questionCount: 0,
  });

  // Move lesson to another chapter modal state
  const [moveLessonState, setMoveLessonState] = useState<{
    open: boolean;
    lesson: LessonOut | null;
  }>({
    open: false,
    lesson: null,
  });

  // Question counts by chapter and lesson
  const chapterCounts = useMemo(() => {
    const map = new Map<string, number>();
    if (stats?.approved_by_chapter) {
      for (const c of stats.approved_by_chapter) {
        map.set(c.id, c.count);
      }
    }
    return map;
  }, [stats]);

  const lessonCounts = useMemo(() => {
    const map = new Map<string, number>();
    if (stats?.approved_by_lesson) {
      for (const l of stats.approved_by_lesson) {
        map.set(l.id, l.count);
      }
    }
    return map;
  }, [stats]);

  const toggleExpand = (chapterId: string) => {
    setExpandedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(chapterId)) next.delete(chapterId);
      else next.add(chapterId);
      return next;
    });
  };

  // Reorder Chapter Up/Down
  const handleChapterReorder = async (
    index: number,
    direction: "up" | "down",
  ) => {
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= chapters.length) return;

    const newOrder = [...chapters];
    const temp = newOrder[index];
    const target = newOrder[targetIndex];
    if (!temp || !target) return;
    newOrder[index] = target;
    newOrder[targetIndex] = temp;

    try {
      await reorderChaptersMut.mutateAsync({
        subjectId,
        ids: newOrder.map((c) => c.id),
      });
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  // Reorder Lesson Up/Down
  const handleLessonReorder = async (
    chapter: ChapterTree,
    index: number,
    direction: "up" | "down",
  ) => {
    const lessons = chapter.lessons;
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= lessons.length) return;

    const newOrder = [...lessons];
    const temp = newOrder[index];
    const target = newOrder[targetIndex];
    if (!temp || !target) return;
    newOrder[index] = target;
    newOrder[targetIndex] = temp;

    try {
      await reorderLessonsMut.mutateAsync({
        chapterId: chapter.id,
        subjectId,
        ids: newOrder.map((l) => l.id),
      });
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  // Save Inline Rename
  const handleSaveRename = async (type: "chapter" | "lesson", id: string) => {
    if (!editingTitle.trim()) return;
    try {
      if (type === "chapter") {
        await updateChapterMut.mutateAsync({
          id,
          subjectId,
          data: { title: editingTitle.trim() },
        });
      } else {
        await updateLessonMut.mutateAsync({
          id,
          subjectId,
          data: { title: editingTitle.trim() },
        });
      }
      setEditingNodeId(null);
      setEditingTitle("");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  // Add Lesson
  const handleCreateLesson = async (chapterId: string) => {
    if (!newLessonTitle.trim()) return;
    try {
      await createLessonMut.mutateAsync({
        chapterId,
        subjectId,
        data: { title: newLessonTitle.trim() },
      });
      setAddingLessonChapterId(null);
      setNewLessonTitle("");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  // Delete Chapter
  const handleDeleteChapter = async (chapter: ChapterTree) => {
    try {
      await deleteChapterMut.mutateAsync({
        id: chapter.id,
        subjectId,
      });
    } catch (error) {
      const isNotEmpty =
        (error instanceof ApiError && error.code === "not_empty") ||
        (error instanceof ApiError && error.status === 409);
      toast.error(
        isNotEmpty
          ? t("bank.taxonomy.deleteNotEmptyError")
          : error instanceof ApiError
            ? error.message
            : t("review.errors.action"),
      );
    }
  };

  // Delete Lesson
  const handleDeleteLesson = async (lesson: LessonOut) => {
    try {
      await deleteLessonMut.mutateAsync({
        id: lesson.id,
        subjectId,
      });
    } catch (error) {
      const isNotEmpty =
        (error instanceof ApiError && error.code === "not_empty") ||
        (error instanceof ApiError && error.status === 409);
      toast.error(
        isNotEmpty
          ? t("bank.taxonomy.deleteNotEmptyError")
          : error instanceof ApiError
            ? error.message
            : t("review.errors.action"),
      );
    }
  };

  // Open Merge Chapter Dialog
  const handleOpenMergeChapter = (chapter: ChapterTree) => {
    const available = chapters
      .filter((c) => c.id !== chapter.id)
      .map((c) => ({ id: c.id, title: c.title }));
    setMergeState({
      open: true,
      sourceType: "chapter",
      sourceItem: { id: chapter.id, title: chapter.title },
      availableTargets: available,
      questionCount: chapterCounts.get(chapter.id) ?? 0,
    });
  };

  // Open Merge Lesson Dialog
  const handleOpenMergeLesson = (chapter: ChapterTree, lesson: LessonOut) => {
    const available = chapter.lessons
      .filter((l) => l.id !== lesson.id)
      .map((l) => ({ id: l.id, title: l.title }));
    setMergeState({
      open: true,
      sourceType: "lesson",
      sourceItem: { id: lesson.id, title: lesson.title },
      availableTargets: available,
      questionCount: lessonCounts.get(lesson.id) ?? 0,
    });
  };

  return (
    <>
      <div
        role="tree"
        aria-label={t("bank.taxonomy.tree")}
        className="flex flex-col gap-3"
      >
        {chapters.map((chapter, cIndex) => {
          const isExpanded = expandedChapters.has(chapter.id);
          const isEditing = editingNodeId === chapter.id;
          const qCount = chapterCounts.get(chapter.id) ?? 0;
          const isProposed =
            (chapter as unknown as { metadata?: { proposed?: boolean } })
              .metadata?.proposed === true;

          return (
            <div
              key={chapter.id}
              role="treeitem"
              aria-selected={false}
              aria-expanded={isExpanded}
              aria-level={1}
              data-testid={`chapter-item-${chapter.id}`}
              className="bg-card flex flex-col rounded-lg border transition-all"
            >
              {/* Chapter Row */}
              <div className="hover:bg-muted/30 flex flex-wrap items-center justify-between gap-2 p-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      toggleExpand(chapter.id);
                    }}
                    className="opacity-70 hover:opacity-100"
                    aria-label="Toggle chapter"
                  >
                    {isExpanded ? (
                      <ChevronDown className="size-4" />
                    ) : (
                      <ChevronRight className="size-4" />
                    )}
                  </button>

                  <Folder className="text-primary size-4" />

                  {isEditing ? (
                    <div className="flex items-center gap-1.5">
                      <Input
                        value={editingTitle}
                        onChange={(e) => {
                          setEditingTitle(e.target.value);
                        }}
                        className="h-7 text-xs"
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            void handleSaveRename("chapter", chapter.id);
                          } else if (e.key === "Escape") {
                            setEditingNodeId(null);
                          }
                        }}
                      />
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() =>
                          void handleSaveRename("chapter", chapter.id)
                        }
                        className="size-7 p-0"
                      >
                        <Check className="size-3.5 text-emerald-600" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingNodeId(null);
                        }}
                        className="size-7 p-0"
                      >
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-2">
                      <span className="text-foreground text-sm font-semibold">
                        {chapter.title}
                      </span>
                      <Badge variant="secondary" className="text-[11px]">
                        {t("bank.taxonomy.questionsCount", { count: qCount })}
                      </Badge>
                      {isProposed && (
                        <Badge variant="warning" className="gap-1 text-[10px]">
                          <Sparkles className="size-3" />
                          <span>{t("bank.taxonomy.suggested")}</span>
                        </Badge>
                      )}
                    </div>
                  )}
                </div>

                {/* Chapter actions (Editor only) */}
                {canEdit && (
                  <div className="flex items-center gap-1">
                    {isProposed && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => {
                          toast.info("Proposed node accepted.");
                        }}
                      >
                        {t("bank.taxonomy.accept")}
                      </Button>
                    )}

                    {/* Up / Down reorder buttons */}
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={cIndex === 0}
                      onClick={() => void handleChapterReorder(cIndex, "up")}
                      aria-label={t("bank.taxonomy.reorderUp")}
                      data-testid={`chapter-move-up-${chapter.id}`}
                      className="size-7 p-0"
                    >
                      <ArrowUp className="size-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={cIndex === chapters.length - 1}
                      onClick={() => void handleChapterReorder(cIndex, "down")}
                      aria-label={t("bank.taxonomy.reorderDown")}
                      data-testid={`chapter-move-down-${chapter.id}`}
                      className="size-7 p-0"
                    >
                      <ArrowDown className="size-3.5" />
                    </Button>

                    {/* Add lesson */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setAddingLessonChapterId(chapter.id);
                        setNewLessonTitle("");
                        if (!isExpanded) toggleExpand(chapter.id);
                      }}
                      aria-label={t("bank.taxonomy.addLesson")}
                      className="h-7 gap-1 px-2 text-xs"
                    >
                      <Plus className="size-3.5" />
                      <span className="hidden sm:inline">
                        {t("bank.taxonomy.addLesson")}
                      </span>
                    </Button>

                    {/* Inline rename */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingNodeId(chapter.id);
                        setEditingTitle(chapter.title);
                      }}
                      aria-label={t("bank.taxonomy.rename")}
                      className="size-7 p-0"
                    >
                      <Edit2 className="size-3.5" />
                    </Button>

                    {/* Merge chapter */}
                    {chapters.length > 1 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          handleOpenMergeChapter(chapter);
                        }}
                        aria-label={t("bank.taxonomy.merge")}
                        data-testid={`chapter-merge-${chapter.id}`}
                        className="size-7 p-0"
                      >
                        <GitMerge className="size-3.5" />
                      </Button>
                    )}

                    {/* Delete chapter */}
                    <Button
                      variant="ghost"
                      size="sm"
                      data-testid={`delete-chapter-${chapter.id}`}
                      onClick={() => void handleDeleteChapter(chapter)}
                      aria-label={t("bank.taxonomy.delete")}
                      className="text-destructive hover:bg-destructive/10 hover:text-destructive size-7 p-0"
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </div>
                )}
              </div>

              {/* Lessons Subtree */}
              {isExpanded && (
                <div
                  role="group"
                  className="ms-6 flex flex-col gap-1 border-s ps-3 pb-3"
                >
                  {/* Inline add lesson input */}
                  {addingLessonChapterId === chapter.id && (
                    <div className="flex items-center gap-2 py-1">
                      <Input
                        placeholder={t("bank.taxonomy.addLesson")}
                        value={newLessonTitle}
                        onChange={(e) => {
                          setNewLessonTitle(e.target.value);
                        }}
                        className="h-8 max-w-sm text-xs"
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            void handleCreateLesson(chapter.id);
                          } else if (e.key === "Escape") {
                            setAddingLessonChapterId(null);
                          }
                        }}
                      />
                      <Button
                        size="sm"
                        onClick={() => {
                          void handleCreateLesson(chapter.id);
                        }}
                        className="h-8 px-2 text-xs"
                      >
                        {t("bank.taxonomy.confirm")}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setAddingLessonChapterId(null);
                        }}
                        className="h-8 px-2 text-xs"
                      >
                        {t("bank.taxonomy.cancel")}
                      </Button>
                    </div>
                  )}

                  {chapter.lessons.length === 0 &&
                    addingLessonChapterId !== chapter.id && (
                      <span className="text-muted-foreground py-2 text-xs italic">
                        {t("bank.taxonomy.emptyTree")}
                      </span>
                    )}

                  {chapter.lessons.map((lesson, lIndex) => {
                    const isLessonEditing = editingNodeId === lesson.id;
                    const lCount = lessonCounts.get(lesson.id) ?? 0;
                    const isLessonProposed =
                      (
                        lesson as unknown as {
                          metadata?: { proposed?: boolean };
                        }
                      ).metadata?.proposed === true;

                    return (
                      <div
                        key={lesson.id}
                        role="treeitem"
                        aria-selected={false}
                        aria-level={2}
                        data-testid={`lesson-item-${lesson.id}`}
                        className="hover:bg-muted/40 flex flex-wrap items-center justify-between gap-2 rounded-md p-2"
                      >
                        <div className="flex items-center gap-2">
                          <FolderTree className="text-muted-foreground size-3.5" />
                          {isLessonEditing ? (
                            <div className="flex items-center gap-1.5">
                              <Input
                                value={editingTitle}
                                onChange={(e) => {
                                  setEditingTitle(e.target.value);
                                }}
                                className="h-7 text-xs"
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") {
                                    void handleSaveRename("lesson", lesson.id);
                                  } else if (e.key === "Escape") {
                                    setEditingNodeId(null);
                                  }
                                }}
                              />
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() =>
                                  void handleSaveRename("lesson", lesson.id)
                                }
                                className="size-7 p-0"
                              >
                                <Check className="size-3.5 text-emerald-600" />
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                  setEditingNodeId(null);
                                }}
                                className="size-7 p-0"
                              >
                                <X className="size-3.5" />
                              </Button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <span className="text-foreground text-xs">
                                {lesson.title}
                              </span>
                              <span className="text-muted-foreground text-[11px]">
                                (
                                {t("bank.taxonomy.questionsCount", {
                                  count: lCount,
                                })}
                                )
                              </span>
                              {isLessonProposed && (
                                <Badge
                                  variant="warning"
                                  className="gap-1 text-[10px]"
                                >
                                  <Sparkles className="size-3" />
                                  <span>{t("bank.taxonomy.suggested")}</span>
                                </Badge>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Lesson actions (Editor only) */}
                        {canEdit && (
                          <div className="flex items-center gap-1">
                            {isLessonProposed && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-6 px-1.5 text-[10px]"
                                onClick={() => {
                                  toast.info("Proposed node accepted.");
                                }}
                              >
                                {t("bank.taxonomy.accept")}
                              </Button>
                            )}

                            {/* Up / Down reorder */}
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={lIndex === 0}
                              onClick={() =>
                                void handleLessonReorder(chapter, lIndex, "up")
                              }
                              aria-label={t("bank.taxonomy.reorderUp")}
                              data-testid={`lesson-move-up-${lesson.id}`}
                              className="size-6 p-0"
                            >
                              <ArrowUp className="size-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              disabled={lIndex === chapter.lessons.length - 1}
                              onClick={() =>
                                void handleLessonReorder(
                                  chapter,
                                  lIndex,
                                  "down",
                                )
                              }
                              aria-label={t("bank.taxonomy.reorderDown")}
                              data-testid={`lesson-move-down-${lesson.id}`}
                              className="size-6 p-0"
                            >
                              <ArrowDown className="size-3" />
                            </Button>

                            {/* Move to another chapter */}
                            {chapters.length > 1 && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  setMoveLessonState({
                                    open: true,
                                    lesson,
                                  });
                                }}
                                aria-label={t("bank.taxonomy.moveLesson")}
                                data-testid={`lesson-move-chapter-${lesson.id}`}
                                className="size-6 p-0"
                              >
                                <MoveRight className="size-3" />
                              </Button>
                            )}

                            {/* Merge lesson */}
                            {chapter.lessons.length > 1 && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => {
                                  handleOpenMergeLesson(chapter, lesson);
                                }}
                                aria-label={t("bank.taxonomy.merge")}
                                data-testid={`lesson-merge-${lesson.id}`}
                                className="size-6 p-0"
                              >
                                <GitMerge className="size-3.5" />
                              </Button>
                            )}

                            {/* Rename lesson */}
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => {
                                setEditingNodeId(lesson.id);
                                setEditingTitle(lesson.title);
                              }}
                              aria-label={t("bank.taxonomy.rename")}
                              className="size-6 p-0"
                            >
                              <Edit2 className="size-3" />
                            </Button>

                            {/* Delete lesson */}
                            <Button
                              variant="ghost"
                              size="sm"
                              data-testid={`delete-lesson-${lesson.id}`}
                              onClick={() => void handleDeleteLesson(lesson)}
                              aria-label={t("bank.taxonomy.delete")}
                              className="text-destructive hover:bg-destructive/10 hover:text-destructive size-6 p-0"
                            >
                              <Trash2 className="size-3" />
                            </Button>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Merge Modal */}
      {mergeState.open && (
        <MergeDialog
          open={mergeState.open}
          onOpenChange={(open) => {
            setMergeState((prev) => ({ ...prev, open }));
          }}
          sourceType={mergeState.sourceType}
          sourceItem={mergeState.sourceItem}
          availableTargets={mergeState.availableTargets}
          subjectId={subjectId}
          questionCount={mergeState.questionCount}
        />
      )}

      {/* Move Lesson Modal */}
      {moveLessonState.open && moveLessonState.lesson && (
        <MoveLessonChapterDialog
          open={moveLessonState.open}
          onOpenChange={(open) => {
            setMoveLessonState((prev) => ({ ...prev, open }));
          }}
          lesson={moveLessonState.lesson}
          chapters={chapters}
          subjectId={subjectId}
        />
      )}
    </>
  );
}
