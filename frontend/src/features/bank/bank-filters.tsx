import { ChevronDown, ChevronRight, Filter, Search, X } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { type BankFacets, useBankTags } from "@/api/hooks/bank";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export interface FilterState {
  chapter_ids: string[];
  lesson_ids: string[];
  types: string[];
  difficulty_min: number | null;
  difficulty_max: number | null;
  statuses: string[];
  source_ids: string[];
  tags: string[];
  has_figure: boolean | null;
  has_answer: boolean | null;
  exam_title: string | null;
}

export interface BankFiltersProps {
  facets?: BankFacets | null;
  filters: FilterState;
  onChange: (next: FilterState) => void;
  onClearAll: () => void;
  subjectId?: string | null;
  canEditStatus: boolean;
  className?: string;
}

export function BankFiltersContent({
  facets,
  filters,
  onChange,
  onClearAll,
  subjectId,
  canEditStatus,
}: Omit<BankFiltersProps, "className">) {
  const { t } = useTranslation();
  const [tagSearch, setTagSearch] = useState("");
  const [expandedChapters, setExpandedChapters] = useState<Set<string>>(
    new Set(),
  );

  const tagsQuery = useBankTags(subjectId, tagSearch);
  const tagSuggestions = useMemo(() => {
    if (Array.isArray(tagsQuery.data)) return tagsQuery.data;
    if (Array.isArray(facets?.tags)) return facets.tags;
    return [];
  }, [tagsQuery.data, facets?.tags]);

  const toggleArrayFilter = (
    key:
      | "chapter_ids"
      | "lesson_ids"
      | "types"
      | "statuses"
      | "source_ids"
      | "tags",
    value: string,
  ) => {
    const current = filters[key];
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    onChange({ ...filters, [key]: next });
  };

  const toggleDifficulty = (level: number) => {
    if (filters.difficulty_min === level && filters.difficulty_max === level) {
      onChange({ ...filters, difficulty_min: null, difficulty_max: null });
    } else {
      onChange({ ...filters, difficulty_min: level, difficulty_max: level });
    }
  };

  const toggleChapterExpand = (chapterId: string) => {
    const next = new Set(expandedChapters);
    if (next.has(chapterId)) {
      next.delete(chapterId);
    } else {
      next.add(chapterId);
    }
    setExpandedChapters(next);
  };

  // Group lessons by chapter
  const lessonsByChapter = useMemo(() => {
    const map = new Map<
      string,
      { id: string; title: string; count: number }[]
    >();
    if (Array.isArray(facets?.lessons)) {
      for (const lesson of facets.lessons) {
        const list = map.get(lesson.chapter_id) ?? [];
        list.push(lesson);
        map.set(lesson.chapter_id, list);
      }
    }
    return map;
  }, [facets?.lessons]);

  const hasAnyFilter =
    filters.chapter_ids.length > 0 ||
    filters.lesson_ids.length > 0 ||
    filters.types.length > 0 ||
    filters.statuses.length > 0 ||
    filters.source_ids.length > 0 ||
    filters.tags.length > 0 ||
    filters.difficulty_min !== null ||
    filters.has_figure !== null ||
    filters.has_answer !== null ||
    Boolean(filters.exam_title);

  return (
    <div className="flex flex-col gap-6 text-sm">
      <div className="flex items-center justify-between">
        <h2 className="text-foreground font-semibold">
          {t("bank.filters.title")}
        </h2>
        {hasAnyFilter && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearAll}
            className="text-muted-foreground hover:text-foreground h-8 px-2 text-xs"
          >
            {t("bank.filters.clearAll")}
          </Button>
        )}
      </div>

      <Separator />

      {/* Chapter & Lesson Nested Filter */}
      {Array.isArray(facets?.chapters) && facets.chapters.length > 0 && (
        <div className="flex flex-col gap-2">
          <Label className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
            {t("bank.filters.chapterLesson")}
          </Label>
          <div className="flex flex-col gap-1">
            {facets.chapters.map((chapter) => {
              const chapterLessons = lessonsByChapter.get(chapter.id) ?? [];
              const isChapterSelected = filters.chapter_ids.includes(
                chapter.id,
              );
              const isExpanded =
                expandedChapters.has(chapter.id) || isChapterSelected;

              return (
                <div key={chapter.id} className="flex flex-col">
                  <div className="hover:bg-muted/50 flex items-center justify-between rounded-md p-1">
                    <div className="flex items-center gap-1.5">
                      {chapterLessons.length > 0 && (
                        <button
                          type="button"
                          onClick={() => {
                            toggleChapterExpand(chapter.id);
                          }}
                          className="text-muted-foreground hover:text-foreground"
                          aria-label="Toggle lessons"
                        >
                          {isExpanded ? (
                            <ChevronDown className="size-3.5" />
                          ) : (
                            <ChevronRight className="size-3.5" />
                          )}
                        </button>
                      )}
                      <label className="flex cursor-pointer items-center gap-2">
                        <input
                          type="checkbox"
                          checked={isChapterSelected}
                          onChange={() => {
                            toggleArrayFilter("chapter_ids", chapter.id);
                          }}
                          className="accent-primary size-3.5 rounded-xs"
                        />
                        <span className="text-foreground text-xs font-medium">
                          {chapter.title}
                        </span>
                      </label>
                    </div>
                    <span className="text-muted-foreground text-[11px]">
                      {chapter.count}
                    </span>
                  </div>

                  {isExpanded && chapterLessons.length > 0 && (
                    <div className="ms-5 flex flex-col gap-1 border-s ps-2">
                      {chapterLessons.map((lesson) => (
                        <label
                          key={lesson.id}
                          className="hover:bg-muted/50 flex cursor-pointer items-center justify-between rounded-md p-1 text-xs"
                        >
                          <div className="flex items-center gap-2">
                            <input
                              type="checkbox"
                              checked={filters.lesson_ids.includes(lesson.id)}
                              onChange={() => {
                                toggleArrayFilter("lesson_ids", lesson.id);
                              }}
                              className="accent-primary size-3.5 rounded-xs"
                            />
                            <span className="text-muted-foreground">
                              {lesson.title}
                            </span>
                          </div>
                          <span className="text-muted-foreground text-[11px]">
                            {lesson.count}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Question Type Filter */}
      {facets?.types &&
        typeof facets.types === "object" &&
        Object.keys(facets.types).length > 0 && (
          <div className="flex flex-col gap-2">
            <Label className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
              {t("bank.filters.type")}
            </Label>
            <div className="flex flex-col gap-1">
              {Object.entries(facets.types).map(([typeKey, count]) => (
                <label
                  key={typeKey}
                  className="hover:bg-muted/50 flex cursor-pointer items-center justify-between rounded-md p-1"
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={filters.types.includes(typeKey)}
                      onChange={() => {
                        toggleArrayFilter("types", typeKey);
                      }}
                      className="accent-primary size-3.5 rounded-xs"
                    />
                    <span className="text-xs">
                      {t(`bank.question.types.${typeKey}`, {
                        defaultValue: typeKey,
                      })}
                    </span>
                  </div>
                  <span className="text-muted-foreground text-[11px]">
                    {count}
                  </span>
                </label>
              ))}
            </div>
          </div>
        )}

      {/* Difficulty Filter */}
      <div className="flex flex-col gap-2">
        <Label className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
          {t("bank.filters.difficulty")}
        </Label>
        <div className="flex flex-wrap gap-1.5">
          {[1, 2, 3, 4, 5].map((lvl) => {
            const count = facets?.difficulties
              ? (facets.difficulties[String(lvl)] ?? 0)
              : 0;
            const isSelected =
              filters.difficulty_min === lvl && filters.difficulty_max === lvl;
            return (
              <button
                key={lvl}
                type="button"
                onClick={() => {
                  toggleDifficulty(lvl);
                }}
                className={cn(
                  "flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs transition-colors",
                  isSelected
                    ? "border-primary bg-primary text-primary-foreground font-semibold"
                    : "border-border hover:bg-muted text-foreground",
                )}
              >
                <span>{lvl}</span>
                <span
                  className={cn(
                    "text-[10px]",
                    isSelected
                      ? "text-primary-foreground/80"
                      : "text-muted-foreground",
                  )}
                >
                  ({count})
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Status Filter (Editors Only) */}
      {canEditStatus &&
        facets?.statuses &&
        typeof facets.statuses === "object" && (
          <div className="flex flex-col gap-2">
            <Label className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
              {t("bank.filters.status")}
            </Label>
            <div className="flex flex-col gap-1">
              {Object.entries(facets.statuses).map(([st, count]) => (
                <label
                  key={st}
                  className="hover:bg-muted/50 flex cursor-pointer items-center justify-between rounded-md p-1"
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={filters.statuses.includes(st)}
                      onChange={() => {
                        toggleArrayFilter("statuses", st);
                      }}
                      className="accent-primary size-3.5 rounded-xs"
                    />
                    <span className="text-xs">
                      {t(`review.status.${st}`, { defaultValue: st })}
                    </span>
                  </div>
                  <span className="text-muted-foreground text-[11px]">
                    {count}
                  </span>
                </label>
              ))}
            </div>
          </div>
        )}

      {/* Source Filter */}
      {Array.isArray(facets?.sources) && facets.sources.length > 0 && (
        <div className="flex flex-col gap-2">
          <Label className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
            {t("bank.filters.source")}
          </Label>
          <div className="flex flex-col gap-1">
            {facets.sources.map((source) => (
              <label
                key={source.id}
                className="hover:bg-muted/50 flex cursor-pointer items-center justify-between rounded-md p-1"
              >
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={filters.source_ids.includes(source.id)}
                    onChange={() => {
                      toggleArrayFilter("source_ids", source.id);
                    }}
                    className="accent-primary size-3.5 rounded-xs"
                  />
                  <span className="truncate text-xs">{source.title}</span>
                </div>
                <span className="text-muted-foreground text-[11px]">
                  {source.count}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Tags Filter */}
      <div className="flex flex-col gap-2">
        <Label className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
          {t("bank.filters.tags")}
        </Label>
        <div className="relative">
          <Search className="text-muted-foreground absolute start-2.5 top-2.5 size-3.5" />
          <Input
            placeholder={t("bank.filters.tagsPlaceholder")}
            value={tagSearch}
            onChange={(e) => {
              setTagSearch(e.target.value);
            }}
            className="h-8 ps-8 text-xs"
          />
        </div>
        <div className="flex max-h-36 flex-wrap gap-1 overflow-y-auto pt-1">
          {tagSuggestions.slice(0, 30).map((tc) => {
            const isSelected = filters.tags.includes(tc.tag);
            return (
              <Badge
                key={tc.tag}
                variant={isSelected ? "default" : "outline"}
                className="cursor-pointer gap-1 px-2 py-0.5 text-xs font-normal"
                onClick={() => {
                  toggleArrayFilter("tags", tc.tag);
                }}
              >
                <span>#{tc.tag}</span>
                <span className="text-[10px] opacity-70">({tc.count})</span>
              </Badge>
            );
          })}
        </div>
      </div>

      {/* Boolean and Exam Title Filters */}
      <div className="flex flex-col gap-3">
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={filters.has_figure === true}
            onChange={(e) => {
              onChange({
                ...filters,
                has_figure: e.target.checked ? true : null,
              });
            }}
            className="accent-primary size-3.5 rounded-xs"
          />
          <span className="text-foreground text-xs font-medium">
            {t("bank.filters.hasFigure")}
          </span>
        </label>

        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={filters.has_answer === true}
            onChange={(e) => {
              onChange({
                ...filters,
                has_answer: e.target.checked ? true : null,
              });
            }}
            className="accent-primary size-3.5 rounded-xs"
          />
          <span className="text-foreground text-xs font-medium">
            {t("bank.filters.hasAnswer")}
          </span>
        </label>

        <div className="flex flex-col gap-1.5 pt-1">
          <Label className="text-muted-foreground text-xs">
            {t("bank.filters.examTitle")}
          </Label>
          <Input
            placeholder={t("bank.filters.examTitlePlaceholder")}
            value={filters.exam_title ?? ""}
            onChange={(e) => {
              onChange({
                ...filters,
                exam_title: e.target.value.trim() ? e.target.value : null,
              });
            }}
            className="h-8 text-xs"
          />
        </div>
      </div>
    </div>
  );
}

export function BankFilters(props: BankFiltersProps) {
  const { t } = useTranslation();
  const filterDescId = useId();

  return (
    <>
      {/* Desktop Sidebar */}
      <aside
        className={cn(
          "bg-card hidden w-64 shrink-0 flex-col rounded-lg border p-4 shadow-2xs lg:flex",
          props.className,
        )}
      >
        <BankFiltersContent {...props} />
      </aside>

      {/* Mobile Sheet Trigger */}
      <div className="lg:hidden">
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm" className="gap-2">
              <Filter className="size-4" />
              <span>{t("bank.filters.openFilters")}</span>
            </Button>
          </SheetTrigger>
          <SheetContent
            side="start"
            className="w-80 overflow-y-auto p-6"
            aria-describedby={filterDescId}
          >
            <SheetHeader className="sr-only">
              <SheetTitle>{t("bank.filters.title")}</SheetTitle>
              <SheetDescription id={filterDescId}>
                {t("bank.filters.title")}
              </SheetDescription>
            </SheetHeader>
            <BankFiltersContent {...props} />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}

export function ActiveFilterChips({
  filters,
  facets,
  onChange,
  onClearAll,
}: {
  filters: FilterState;
  facets?: BankFacets | null;
  onChange: (next: FilterState) => void;
  onClearAll: () => void;
}) {
  const { t } = useTranslation();

  const chips: { label: string; onRemove: () => void }[] = [];

  // Chapters
  for (const cid of filters.chapter_ids) {
    const title = facets?.chapters.find((c) => c.id === cid)?.title ?? cid;
    chips.push({
      label: title,
      onRemove: () => {
        onChange({
          ...filters,
          chapter_ids: filters.chapter_ids.filter((id) => id !== cid),
        });
      },
    });
  }

  // Lessons
  for (const lid of filters.lesson_ids) {
    const title = facets?.lessons.find((l) => l.id === lid)?.title ?? lid;
    chips.push({
      label: title,
      onRemove: () => {
        onChange({
          ...filters,
          lesson_ids: filters.lesson_ids.filter((id) => id !== lid),
        });
      },
    });
  }

  // Types
  for (const typ of filters.types) {
    chips.push({
      label: t(`bank.question.types.${typ}`, { defaultValue: typ }),
      onRemove: () => {
        onChange({
          ...filters,
          types: filters.types.filter((t) => t !== typ),
        });
      },
    });
  }

  // Difficulty
  if (filters.difficulty_min !== null) {
    chips.push({
      label: `${t("bank.filters.difficulty")}: ${String(filters.difficulty_min)}`,
      onRemove: () => {
        onChange({
          ...filters,
          difficulty_min: null,
          difficulty_max: null,
        });
      },
    });
  }

  // Statuses
  for (const st of filters.statuses) {
    chips.push({
      label: t(`review.status.${st}`, { defaultValue: st }),
      onRemove: () => {
        onChange({
          ...filters,
          statuses: filters.statuses.filter((s) => s !== st),
        });
      },
    });
  }

  // Sources
  for (const sid of filters.source_ids) {
    const title = facets?.sources.find((s) => s.id === sid)?.title ?? sid;
    chips.push({
      label: title,
      onRemove: () => {
        onChange({
          ...filters,
          source_ids: filters.source_ids.filter((s) => s !== sid),
        });
      },
    });
  }

  // Tags
  for (const tag of filters.tags) {
    chips.push({
      label: `#${tag}`,
      onRemove: () => {
        onChange({
          ...filters,
          tags: filters.tags.filter((t) => t !== tag),
        });
      },
    });
  }

  // Has figure
  if (filters.has_figure) {
    chips.push({
      label: t("bank.filters.hasFigure"),
      onRemove: () => {
        onChange({ ...filters, has_figure: null });
      },
    });
  }

  // Has answer
  if (filters.has_answer) {
    chips.push({
      label: t("bank.filters.hasAnswer"),
      onRemove: () => {
        onChange({ ...filters, has_answer: null });
      },
    });
  }

  // Exam title
  if (filters.exam_title) {
    chips.push({
      label: `Exam: ${filters.exam_title}`,
      onRemove: () => {
        onChange({ ...filters, exam_title: null });
      },
    });
  }

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 py-1">
      {chips.map((chip, idx) => (
        <Badge
          key={idx}
          variant="secondary"
          className="gap-1 px-2 py-1 text-xs font-normal"
        >
          <span>{chip.label}</span>
          <button
            type="button"
            onClick={chip.onRemove}
            className="opacity-70 hover:opacity-100"
            aria-label="Remove filter"
          >
            <X className="size-3" />
          </button>
        </Badge>
      ))}
      <Button
        variant="link"
        size="sm"
        onClick={onClearAll}
        className="text-muted-foreground hover:text-foreground h-auto p-0 text-xs"
      >
        {t("bank.filters.clearAll")}
      </Button>
    </div>
  );
}
