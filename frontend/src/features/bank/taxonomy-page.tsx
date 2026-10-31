import {
  ArrowLeft,
  BookOpen,
  Edit2,
  FolderPlus,
  Info,
  Loader2,
  Plus,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import { useMe } from "@/api/hooks/auth";
import { useBankStats } from "@/api/hooks/bank";
import { useSubjects } from "@/api/hooks/subjects";
import {
  useCreateChapter,
  useDeleteSubject,
  useSubjectTree,
} from "@/api/hooks/taxonomy";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SubjectDialog } from "@/features/bank/taxonomy-dialogs";
import { TaxonomyTree } from "@/features/bank/taxonomy-tree";

const STORAGE_KEY_SUBJECT = "qbank_selected_subject_id";

export function TaxonomyPage() {
  const { t } = useTranslation();
  const { data: user } = useMe();
  const canEdit = user?.role !== "teacher";

  const { data: subjectsData, isLoading: subjectsLoading } = useSubjects();
  const subjects = useMemo(
    () => (Array.isArray(subjectsData?.items) ? subjectsData.items : []),
    [subjectsData],
  );

  const [selectedSubjectId, setSelectedSubjectId] = useState<string>(() => {
    if (typeof window !== "undefined") {
      return window.localStorage.getItem(STORAGE_KEY_SUBJECT) ?? "";
    }
    return "";
  });

  useEffect(() => {
    if (!selectedSubjectId && subjects.length > 0) {
      const firstId = subjects[0]?.id ?? "";
      setSelectedSubjectId(firstId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY_SUBJECT, firstId);
      }
    }
  }, [selectedSubjectId, subjects]);

  const handleSelectSubject = (id: string) => {
    setSelectedSubjectId(id);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY_SUBJECT, id);
    }
  };

  const selectedSubject = subjects.find((s) => s.id === selectedSubjectId);

  // Subject Tree & Stats
  const treeQuery = useSubjectTree(selectedSubjectId);
  const statsQuery = useBankStats(selectedSubjectId);
  const deleteSubjectMut = useDeleteSubject();
  const createChapterMut = useCreateChapter();

  // Dialogs
  const [subjectDialogOpen, setSubjectDialogOpen] = useState(false);
  const [editingSubject, setEditingSubject] = useState<{
    id: string;
    name: string;
    grade?: string | null;
    language?: "ar" | "en";
  } | null>(null);

  // Add chapter inline
  const [addingChapter, setAddingChapter] = useState(false);
  const [newChapterTitle, setNewChapterTitle] = useState("");

  const handleDeleteSubject = async (id: string) => {
    try {
      await deleteSubjectMut.mutateAsync(id);
      if (selectedSubjectId === id) {
        setSelectedSubjectId("");
      }
    } catch (error) {
      const isNotEmpty =
        (error instanceof ApiError && error.code === "not_empty") ||
        (error instanceof ApiError && error.status === 409);
      toast.error(
        isNotEmpty
          ? t("bank.taxonomy.deleteSubjectNotEmpty")
          : error instanceof ApiError
            ? error.message
            : t("review.errors.action"),
      );
    }
  };

  const handleCreateChapter = async () => {
    if (!newChapterTitle.trim() || !selectedSubjectId) return;
    try {
      await createChapterMut.mutateAsync({
        subjectId: selectedSubjectId,
        data: { title: newChapterTitle.trim() },
      });
      setAddingChapter(false);
      setNewChapterTitle("");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.errors.action"),
      );
    }
  };

  const chapters = treeQuery.data?.chapters ?? [];

  return (
    <section className="flex flex-col gap-6">
      {/* Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              asChild
              className="p-0 hover:bg-transparent"
            >
              <Link
                to="/bank"
                className="text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                <ArrowLeft className="size-4" />
                <span>{t("bank.nav.questions")}</span>
              </Link>
            </Button>
            <span className="text-muted-foreground">/</span>
            <h1 className="text-2xl font-bold tracking-tight">
              {t("bank.taxonomy.title")}
            </h1>
          </div>
          <p className="text-muted-foreground mt-1 text-xs">
            {t("bank.taxonomy.description")}
          </p>
        </div>
      </div>

      {/* Read-Only Banner for Teachers */}
      {!canEdit && (
        <div
          role="alert"
          data-testid="taxonomy-readonly-notice"
          className="flex items-center gap-2 rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-xs font-medium text-blue-900 dark:text-blue-200"
        >
          <Info className="size-4 shrink-0 text-blue-600 dark:text-blue-400" />
          <span>{t("bank.taxonomy.readOnlyNotice")}</span>
        </div>
      )}

      {/* Main Grid: Subjects list on the side, tree in the center */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-4">
        {/* Subjects Column */}
        <div className="flex flex-col gap-3 md:col-span-1">
          <div className="flex items-center justify-between">
            <h2 className="text-foreground text-sm font-semibold">
              {t("bank.taxonomy.subjects")}
            </h2>
            {canEdit && (
              <Button
                variant="outline"
                size="sm"
                data-testid="new-subject-btn"
                onClick={() => {
                  setEditingSubject(null);
                  setSubjectDialogOpen(true);
                }}
                className="h-7 gap-1 px-2 text-xs"
              >
                <Plus className="size-3.5" />
                <span>{t("bank.taxonomy.newSubject")}</span>
              </Button>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            {subjectsLoading ? (
              <div className="text-muted-foreground p-4 text-center text-xs">
                <Loader2 className="mx-auto size-5 animate-spin" />
              </div>
            ) : subjects.length === 0 ? (
              <p className="text-muted-foreground p-4 text-center text-xs">
                No subjects yet.
              </p>
            ) : (
              subjects.map((sub) => {
                const isSelected = sub.id === selectedSubjectId;
                return (
                  <div
                    key={sub.id}
                    role="button"
                    tabIndex={0}
                    data-testid={`subject-item-${sub.id}`}
                    onClick={() => {
                      handleSelectSubject(sub.id);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleSelectSubject(sub.id);
                      }
                    }}
                    className={`group flex cursor-pointer items-center justify-between rounded-lg border p-2.5 text-start transition-colors ${
                      isSelected
                        ? "border-primary bg-primary/5 text-foreground font-semibold"
                        : "border-border hover:bg-muted/50 text-foreground/80"
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <BookOpen className="text-primary size-4 shrink-0" />
                      <div className="flex flex-col">
                        <span className="text-xs">{sub.name}</span>
                        {sub.grade && (
                          <span className="text-muted-foreground text-[10px] font-normal">
                            {sub.grade}
                          </span>
                        )}
                      </div>
                    </div>

                    {canEdit && isSelected && (
                      <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                        <Button
                          variant="ghost"
                          size="sm"
                          data-testid={`rename-subject-${sub.id}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingSubject(sub);
                            setSubjectDialogOpen(true);
                          }}
                          className="size-6 p-0"
                          aria-label={t("bank.taxonomy.renameSubject")}
                        >
                          <Edit2 className="size-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          data-testid={`delete-subject-${sub.id}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleDeleteSubject(sub.id);
                          }}
                          className="text-destructive hover:bg-destructive/10 hover:text-destructive size-6 p-0"
                          aria-label={t("bank.taxonomy.deleteSubject")}
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Tree Column */}
        <div className="flex flex-col gap-4 md:col-span-3">
          <Card className="flex flex-col gap-4 p-5 shadow-2xs">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
              <div>
                <h3 className="text-foreground text-lg font-bold">
                  {selectedSubject?.name ?? t("bank.taxonomy.tree")}
                </h3>
                {selectedSubject?.grade && (
                  <p className="text-muted-foreground text-xs">
                    {selectedSubject.grade} ·{" "}
                    {selectedSubject.language === "ar" ? "العربية" : "English"}
                  </p>
                )}
              </div>

              {canEdit && selectedSubjectId && (
                <Button
                  size="sm"
                  data-testid="add-chapter-btn"
                  onClick={() => {
                    setAddingChapter(true);
                  }}
                  className="gap-1.5 text-xs"
                >
                  <FolderPlus className="size-4" />
                  <span>{t("bank.taxonomy.addChapter")}</span>
                </Button>
              )}
            </div>

            {/* Inline Add Chapter */}
            {addingChapter && (
              <div
                data-testid="add-chapter-inline-form"
                className="bg-muted/20 flex items-center gap-2 rounded-lg border p-3"
              >
                <Input
                  data-testid="new-chapter-title-input"
                  placeholder={t("bank.taxonomy.addChapter")}
                  value={newChapterTitle}
                  onChange={(e) => {
                    setNewChapterTitle(e.target.value);
                  }}
                  className="h-8 max-w-sm text-xs"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleCreateChapter();
                    else if (e.key === "Escape") setAddingChapter(false);
                  }}
                />
                <Button
                  size="sm"
                  data-testid="confirm-add-chapter-btn"
                  onClick={() => {
                    void handleCreateChapter();
                  }}
                  disabled={createChapterMut.isPending}
                  className="h-8 px-3 text-xs"
                >
                  {createChapterMut.isPending
                    ? "..."
                    : t("bank.taxonomy.confirm")}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setAddingChapter(false);
                  }}
                  className="h-8 px-2 text-xs"
                >
                  {t("bank.taxonomy.cancel")}
                </Button>
              </div>
            )}

            {/* Tree Component */}
            {treeQuery.isLoading ? (
              <div className="text-muted-foreground flex flex-col items-center justify-center p-12">
                <Loader2 className="size-7 animate-spin" />
              </div>
            ) : chapters.length === 0 ? (
              <div className="text-muted-foreground flex flex-col items-center justify-center py-12 text-center">
                <p className="text-sm">{t("bank.taxonomy.emptyTree")}</p>
              </div>
            ) : (
              <TaxonomyTree
                chapters={chapters}
                subjectId={selectedSubjectId}
                stats={statsQuery.data ?? null}
                canEdit={canEdit}
              />
            )}
          </Card>
        </div>
      </div>

      {/* Subject Create / Edit Dialog */}
      <SubjectDialog
        open={subjectDialogOpen}
        onOpenChange={setSubjectDialogOpen}
        subjectToEdit={editingSubject}
      />
    </section>
  );
}
