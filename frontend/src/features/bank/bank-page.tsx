import {
  AlertTriangle,
  FolderTree,
  Library,
  Loader2,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router";
import { useMe } from "@/api/hooks/auth";
import {
  type BankSearchParams,
  type BankSort,
  useBankSearch,
  useBankStats,
} from "@/api/hooks/bank";
import { useSubjects } from "@/api/hooks/subjects";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ActiveFilterChips,
  BankFilters,
  type FilterState,
} from "@/features/bank/bank-filters";
import { BulkToolbar } from "@/features/bank/bulk-toolbar";
import { QuestionCard } from "@/features/bank/question-card";
import { QuestionDrawer } from "@/features/bank/question-drawer";

const STORAGE_KEY_SUBJECT = "qbank_selected_subject_id";

export function BankPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: user } = useMe();
  const canEdit = user?.role !== "teacher";

  const { data: subjectsData, isLoading: subjectsLoading } = useSubjects();
  const subjects = useMemo(
    () => (Array.isArray(subjectsData?.items) ? subjectsData.items : []),
    [subjectsData],
  );

  // Subject selection: URL param > localStorage > first available subject
  const urlSubjectId = searchParams.get("subject_id");
  const [subjectId, setSubjectId] = useState<string>(() => {
    if (urlSubjectId) return urlSubjectId;
    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(STORAGE_KEY_SUBJECT);
      if (stored) return stored;
    }
    return "";
  });

  useEffect(() => {
    if (urlSubjectId && urlSubjectId !== subjectId) {
      setSubjectId(urlSubjectId);
    } else if (!subjectId && subjects.length > 0) {
      const firstId = subjects[0]?.id ?? "";
      setSubjectId(firstId);
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY_SUBJECT, firstId);
      }
    }
  }, [urlSubjectId, subjects, subjectId]);

  const handleSubjectChange = (newSubjectId: string) => {
    setSubjectId(newSubjectId);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY_SUBJECT, newSubjectId);
    }
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      if (newSubjectId) {
        next.set("subject_id", newSubjectId);
      } else {
        next.delete("subject_id");
      }
      return next;
    });
  };

  // Search query with 250ms debounce
  const urlQuery = searchParams.get("q") ?? "";
  const [searchInput, setSearchInput] = useState(urlQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(urlQuery);

  useEffect(() => {
    setSearchInput(urlQuery);
    setDebouncedQuery(urlQuery);
  }, [urlQuery]);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedQuery(searchInput);
      setSearchParams((prev) => {
        const next = new URLSearchParams(prev);
        if (searchInput.trim()) {
          next.set("q", searchInput.trim());
        } else {
          next.delete("q");
        }
        return next;
      });
    }, 250);

    return () => {
      clearTimeout(handler);
    };
  }, [searchInput, setSearchParams]);

  // Sort
  const urlSort = searchParams.get("sort") as BankSort | null;
  const sort: BankSort = urlSort ?? (debouncedQuery ? "relevance" : "newest");

  const handleSortChange = (newSort: BankSort) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("sort", newSort);
      return next;
    });
  };

  // Filters from URL
  const filters: FilterState = useMemo(
    () => ({
      chapter_ids: searchParams.getAll("chapter_id"),
      lesson_ids: searchParams.getAll("lesson_id"),
      types: searchParams.getAll("type"),
      difficulty_min: searchParams.get("difficulty_min")
        ? Number(searchParams.get("difficulty_min"))
        : null,
      difficulty_max: searchParams.get("difficulty_max")
        ? Number(searchParams.get("difficulty_max"))
        : null,
      statuses: searchParams.getAll("status"),
      source_ids: searchParams.getAll("source_id"),
      tags: searchParams.getAll("tag"),
      has_figure: searchParams.has("has_figure")
        ? searchParams.get("has_figure") === "true"
        : null,
      has_answer: searchParams.has("has_answer")
        ? searchParams.get("has_answer") === "true"
        : null,
      exam_title: searchParams.get("exam_title"),
    }),
    [searchParams],
  );

  const handleFiltersChange = (next: FilterState) => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams();
      const prevQ = prev.get("q");
      if (prevQ !== null) sp.set("q", prevQ);
      const prevSub = prev.get("subject_id");
      if (prevSub !== null) sp.set("subject_id", prevSub);
      const prevSort = prev.get("sort");
      if (prevSort !== null) sp.set("sort", prevSort);

      for (const cid of next.chapter_ids) sp.append("chapter_id", cid);
      for (const lid of next.lesson_ids) sp.append("lesson_id", lid);
      for (const typ of next.types) sp.append("type", typ);
      if (next.difficulty_min !== null) {
        sp.set("difficulty_min", String(next.difficulty_min));
      }
      if (next.difficulty_max !== null) {
        sp.set("difficulty_max", String(next.difficulty_max));
      }
      for (const st of next.statuses) sp.append("status", st);
      for (const sid of next.source_ids) sp.append("source_id", sid);
      for (const tag of next.tags) sp.append("tag", tag);
      if (next.has_figure !== null) {
        sp.set("has_figure", String(next.has_figure));
      }
      if (next.has_answer !== null) {
        sp.set("has_answer", String(next.has_answer));
      }
      if (next.exam_title) {
        sp.set("exam_title", next.exam_title);
      }

      return sp;
    });
  };

  const handleClearFilters = () => {
    setSearchParams((prev) => {
      const sp = new URLSearchParams();
      const prevQ = prev.get("q");
      if (prevQ !== null) sp.set("q", prevQ);
      const prevSub = prev.get("subject_id");
      if (prevSub !== null) sp.set("subject_id", prevSub);
      const prevSort = prev.get("sort");
      if (prevSort !== null) sp.set("sort", prevSort);
      return sp;
    });
  };

  // Build API search parameters
  const searchApiParams: BankSearchParams = useMemo(
    () => ({
      q: debouncedQuery || null,
      subject_id: subjectId || null,
      chapter_ids: filters.chapter_ids.length > 0 ? filters.chapter_ids : null,
      lesson_ids: filters.lesson_ids.length > 0 ? filters.lesson_ids : null,
      types: filters.types.length > 0 ? filters.types : null,
      difficulty_min: filters.difficulty_min,
      difficulty_max: filters.difficulty_max,
      statuses:
        canEdit && filters.statuses.length > 0 ? filters.statuses : null,
      source_ids: filters.source_ids.length > 0 ? filters.source_ids : null,
      tags: filters.tags.length > 0 ? filters.tags : null,
      has_figure: filters.has_figure,
      has_answer: filters.has_answer,
      exam_title: filters.exam_title,
      sort,
      facets: true,
      limit: 20,
    }),
    [debouncedQuery, subjectId, filters, canEdit, sort],
  );

  // Queries
  const statsQuery = useBankStats(subjectId);
  const searchQuery = useBankSearch(searchApiParams);

  const allItems = useMemo(
    () =>
      searchQuery.data
        ? searchQuery.data.pages.flatMap((page) =>
            Array.isArray(page.items) ? page.items : [],
          )
        : [],
    [searchQuery.data],
  );

  const facets = searchQuery.data?.pages[0]?.facets ?? null;
  const matchMode = searchQuery.data?.pages[0]?.match_mode;
  const totalCount = searchQuery.data?.pages[0]?.total ?? 0;

  // Selection & Shift-range click
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const lastCheckedIndexRef = useRef<number | null>(null);

  const handleToggleSelect = useCallback(
    (index: number, shiftKey: boolean) => {
      const item = allItems[index];
      if (!item) return;

      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (shiftKey && lastCheckedIndexRef.current !== null) {
          const from = Math.min(lastCheckedIndexRef.current, index);
          const to = Math.max(lastCheckedIndexRef.current, index);
          for (let i = from; i <= to; i += 1) {
            const itm = allItems[i];
            if (itm) next.add(itm.id);
          }
        } else if (next.has(item.id)) {
          next.delete(item.id);
        } else {
          next.add(item.id);
        }
        return next;
      });

      lastCheckedIndexRef.current = index;
    },
    [allItems],
  );

  const allSelectedOnPage =
    allItems.length > 0 && allItems.every((item) => selectedIds.has(item.id));

  const handleToggleSelectAll = () => {
    if (allSelectedOnPage) {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const item of allItems) next.delete(item.id);
        return next;
      });
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const item of allItems) next.add(item.id);
        return next;
      });
    }
  };

  const handleClearSelection = () => {
    setSelectedIds(new Set());
    lastCheckedIndexRef.current = null;
  };

  // Detail drawer
  const [drawerQuestionId, setDrawerQuestionId] = useState<string | null>(null);

  const hasActiveFilters =
    filters.chapter_ids.length > 0 ||
    filters.lesson_ids.length > 0 ||
    filters.types.length > 0 ||
    filters.statuses.length > 0 ||
    filters.source_ids.length > 0 ||
    filters.tags.length > 0 ||
    filters.difficulty_min !== null ||
    filters.difficulty_max !== null ||
    filters.has_figure !== null ||
    filters.has_answer !== null ||
    Boolean(filters.exam_title);

  return (
    <section className="flex flex-col gap-6">
      {/* Top Header & Subnav */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {t("pages.bank.title")}
          </h1>
          <p className="text-muted-foreground text-xs">
            {totalCount > 0
              ? t("bank.search.totalResults", { count: totalCount })
              : ""}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Subject selector */}
          <div className="flex items-center gap-2">
            <label
              htmlFor="bank-subject-select"
              className="text-muted-foreground text-xs font-medium"
            >
              {t("bank.search.subjectSelect")}:
            </label>
            <select
              id="bank-subject-select"
              data-testid="bank-subject-select"
              value={subjectId}
              onChange={(e) => {
                handleSubjectChange(e.target.value);
              }}
              className="border-input bg-background focus-visible:ring-ring h-9 rounded-md border px-3 py-1 text-xs shadow-xs focus-visible:ring-1 focus-visible:outline-none"
            >
              {subjectsLoading && <option>Loading...</option>}
              {subjects.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {sub.name}
                </option>
              ))}
            </select>
          </div>

          {/* Link to Taxonomy Manager */}
          <Button variant="outline" size="sm" asChild>
            <Link
              to="/bank/taxonomy"
              className="flex items-center gap-1.5 text-xs"
            >
              <FolderTree className="size-3.5" />
              <span>{t("bank.nav.taxonomy")}</span>
            </Link>
          </Button>
        </div>
      </div>

      {/* Stats Header from /bank/stats */}
      {statsQuery.data && (
        <div
          data-testid="bank-stats-bar"
          className="bg-card flex flex-wrap items-center gap-4 rounded-lg border p-3 text-xs shadow-2xs"
        >
          <span className="text-foreground font-semibold">
            {t("bank.stats.total", { count: statsQuery.data.total })}
          </span>
          <span className="text-muted-foreground">·</span>
          {Object.keys(statsQuery.data.by_status).length > 0 && (
            <div className="flex flex-wrap items-center gap-3">
              {statsQuery.data.by_status.approved !== undefined && (
                <span className="text-emerald-600 dark:text-emerald-400">
                  {t("bank.stats.approved", {
                    count: statsQuery.data.by_status.approved,
                  })}
                </span>
              )}
              {statsQuery.data.by_status.draft !== undefined && (
                <span className="text-muted-foreground">
                  {t("bank.stats.draft", {
                    count: statsQuery.data.by_status.draft,
                  })}
                </span>
              )}
              {statsQuery.data.by_status.needs_review !== undefined && (
                <span className="text-amber-600 dark:text-amber-400">
                  {t("bank.stats.needsReview", {
                    count: statsQuery.data.by_status.needs_review,
                  })}
                </span>
              )}
              {statsQuery.data.by_status.rejected !== undefined && (
                <span className="text-destructive">
                  {t("bank.stats.rejected", {
                    count: statsQuery.data.by_status.rejected,
                  })}
                </span>
              )}
            </div>
          )}
          {Object.keys(statsQuery.data.by_type).length > 0 && (
            <>
              <span className="text-muted-foreground">·</span>
              <div className="text-muted-foreground flex flex-wrap items-center gap-2">
                {Object.entries(statsQuery.data.by_type).map(([k, v]) => (
                  <Badge
                    key={k}
                    variant="outline"
                    className="text-[11px] font-normal"
                  >
                    {t(`bank.question.types.${k}`, { defaultValue: k })}: {v}
                  </Badge>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Search box & Sort */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative min-w-64 flex-1">
          <Search className="text-muted-foreground absolute start-3 top-2.5 size-4" />
          <Input
            data-testid="bank-search-input"
            placeholder={t("bank.search.placeholder")}
            value={searchInput}
            onChange={(e) => {
              setSearchInput(e.target.value);
            }}
            className="ps-9"
          />
        </div>

        <div className="flex items-center gap-2">
          <label
            htmlFor="bank-sort-select"
            className="text-muted-foreground text-xs font-medium"
          >
            {t("bank.search.sort.label")}:
          </label>
          <select
            id="bank-sort-select"
            data-testid="bank-sort-select"
            value={sort}
            onChange={(e) => {
              handleSortChange(e.target.value as BankSort);
            }}
            className="border-input bg-background focus-visible:ring-ring h-9 rounded-md border px-3 py-1 text-xs shadow-xs focus-visible:ring-1 focus-visible:outline-none"
          >
            {debouncedQuery && (
              <option value="relevance">
                {t("bank.search.sort.relevance")}
              </option>
            )}
            <option value="newest">{t("bank.search.sort.newest")}</option>
            <option value="difficulty">
              {t("bank.search.sort.difficulty")}
            </option>
            <option value="source_order">
              {t("bank.search.sort.sourceOrder")}
            </option>
          </select>
        </div>
      </div>

      {/* Fuzzy match notice */}
      {matchMode === "fuzzy" && (
        <div
          role="alert"
          data-testid="fuzzy-match-notice"
          className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs font-medium text-amber-900 dark:text-amber-200"
        >
          <AlertTriangle className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <span>{t("bank.search.fuzzyNotice")}</span>
        </div>
      )}

      {/* Bulk Toolbar */}
      <BulkToolbar
        selectedIds={selectedIds}
        allSelected={allSelectedOnPage}
        onToggleSelectAll={handleToggleSelectAll}
        onClearSelection={handleClearSelection}
        subjectId={subjectId}
        canEdit={canEdit}
      />

      {/* Active filters chips */}
      <ActiveFilterChips
        filters={filters}
        facets={facets}
        onChange={handleFiltersChange}
        onClearAll={handleClearFilters}
      />

      {/* Main Content: Sidebar + Cards List */}
      <div className="flex items-start gap-6">
        {/* Filters Sidebar */}
        <BankFilters
          facets={facets}
          filters={filters}
          onChange={handleFiltersChange}
          onClearAll={handleClearFilters}
          subjectId={subjectId}
          canEditStatus={canEdit}
        />

        {/* Results List */}
        <div className="flex flex-1 flex-col gap-4">
          {searchQuery.isLoading ? (
            <div className="text-muted-foreground flex flex-col items-center justify-center p-12">
              <Loader2 className="size-8 animate-spin" />
              <p className="mt-2 text-sm">{t("bank.search.loading")}</p>
            </div>
          ) : allItems.length === 0 ? (
            <EmptyState
              icon={Library}
              title={
                debouncedQuery || hasActiveFilters
                  ? t("bank.search.noResults")
                  : t("pages.bank.emptyTitle")
              }
              description={
                debouncedQuery || hasActiveFilters
                  ? ""
                  : t("pages.bank.emptyDescription")
              }
            />
          ) : (
            <div
              role="feed"
              aria-busy={searchQuery.isFetching}
              className="flex flex-col gap-3"
            >
              {allItems.map((item, index) => (
                <QuestionCard
                  key={item.id}
                  question={item}
                  selected={selectedIds.has(item.id)}
                  onToggleSelect={(shiftKey) => {
                    handleToggleSelect(index, shiftKey);
                  }}
                  onClick={() => {
                    setDrawerQuestionId(item.id);
                  }}
                  showStatus={canEdit}
                />
              ))}

              {/* Load More Button */}
              {searchQuery.hasNextPage && (
                <div className="flex justify-center pt-4">
                  <Button
                    data-testid="load-more-btn"
                    variant="outline"
                    onClick={() => void searchQuery.fetchNextPage()}
                    disabled={searchQuery.isFetchingNextPage}
                    className="w-full sm:w-auto"
                  >
                    {searchQuery.isFetchingNextPage ? (
                      <>
                        <Loader2 className="me-2 size-4 animate-spin" />
                        <span>{t("bank.search.loading")}</span>
                      </>
                    ) : (
                      <span>{t("bank.search.loadMore")}</span>
                    )}
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Detail Drawer */}
      <QuestionDrawer
        questionId={drawerQuestionId}
        open={drawerQuestionId !== null}
        onOpenChange={(open) => {
          if (!open) setDrawerQuestionId(null);
        }}
        canEdit={canEdit}
      />
    </section>
  );
}
