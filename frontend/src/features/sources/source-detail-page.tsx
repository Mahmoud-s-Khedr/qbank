import {
  AlertTriangle,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  PauseCircle,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router";
import { useMe } from "@/api/hooks/auth";
import {
  getPageImageUrl,
  type PageOut,
  useDeleteSource,
  useResumeSource,
  useSourceDetail,
  useSourceEvents,
  useSourcePages,
} from "@/api/hooks/sources";
import { useSubjects } from "@/api/hooks/subjects";
import { PageCanvas } from "@/components/page-canvas/PageCanvas";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  PageKindChip,
  PageStatusBadge,
  SourceStatusBadge,
} from "@/features/sources/status-badge";
import { getDirection } from "@/i18n";
import { formatCostUsd } from "@/lib/format";
import { cn } from "@/lib/utils";
import { cumulativeStageCount } from "./progress";

export const PAGE_GRID_WINDOW_SIZE = 200;

const STAGE_KEYS = ["rendered", "extracted", "validated", "failed"] as const;

interface PageCardProps {
  sourceId: string;
  page: PageOut;
  onSelect: (pageNumber: number) => void;
}

function PageThumbnailCard({ sourceId, page, onSelect }: PageCardProps) {
  const { t } = useTranslation();
  const [loaded, setLoaded] = useState(false);
  const [errored, setErrored] = useState(false);

  const imageUrl = getPageImageUrl(sourceId, page.page_number, "display");
  const showImage = page.status !== "pending" && !errored;

  const badgeNode = <PageStatusBadge status={page.status} />;

  return (
    <div
      data-testid={`page-card-${String(page.page_number)}`}
      className="border-border bg-card hover:border-primary/60 flex flex-col overflow-hidden rounded-lg border shadow-xs transition-colors"
    >
      <button
        type="button"
        onClick={() => {
          onSelect(page.page_number);
        }}
        aria-label={t("sources.detail.pageNumber", {
          number: page.page_number,
        })}
        className="focus-visible:ring-ring/50 bg-muted/30 relative aspect-[3/4] w-full overflow-hidden text-start outline-none focus-visible:ring-[3px]"
      >
        {!loaded ? (
          <Skeleton
            data-testid={`page-skeleton-${String(page.page_number)}`}
            className="absolute inset-0 h-full w-full rounded-none"
          />
        ) : null}
        {showImage ? (
          <img
            src={imageUrl}
            alt={t("sources.detail.pageNumber", { number: page.page_number })}
            loading="lazy"
            onLoad={() => {
              setLoaded(true);
            }}
            onError={() => {
              setErrored(true);
              setLoaded(true);
            }}
            className={cn(
              "h-full w-full object-contain transition-opacity duration-200",
              loaded ? "opacity-100" : "opacity-0",
            )}
          />
        ) : null}
      </button>

      <div className="flex flex-col gap-2 p-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold">
            {t("sources.detail.pageNumber", { number: page.page_number })}
          </span>
          {page.page_kind ? <PageKindChip kind={page.page_kind} /> : null}
        </div>

        <div className="flex items-center justify-between gap-2">
          {page.status === "failed" && page.error ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  title={page.error}
                  data-testid={`page-error-trigger-${String(page.page_number)}`}
                  className="inline-flex cursor-help items-center gap-1 bg-transparent p-0"
                >
                  {badgeNode}
                  <AlertTriangle
                    className="text-destructive size-3.5 shrink-0"
                    aria-hidden="true"
                  />
                </button>
              </TooltipTrigger>
              <TooltipContent
                data-testid={`page-error-tooltip-${String(page.page_number)}`}
              >
                {page.error}
              </TooltipContent>
            </Tooltip>
          ) : (
            badgeNode
          )}
        </div>
      </div>
    </div>
  );
}

export function SourceDetailPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { id = "", pageNumber: routePageParam } = useParams<{
    id: string;
    pageNumber?: string;
  }>();

  const { data: user } = useMe();
  const { data: source, isPending: isSourceLoading } = useSourceDetail(id);
  const { data: pagesData } = useSourcePages(id);
  const { data: subjectsData } = useSubjects();
  const deleteMutation = useDeleteSource();
  const resumeMutation = useResumeSource();

  useSourceEvents(id, source?.status);

  const canWrite = user?.role !== "teacher";

  const pages = useMemo(
    () => (Array.isArray(pagesData) ? pagesData : []),
    [pagesData],
  );

  const subjectName = useMemo(() => {
    if (!source) {
      return "—";
    }
    const items = Array.isArray(subjectsData?.items) ? subjectsData.items : [];
    const found = items.find((s) => s.id === source.subject_id);
    return found?.name ?? t("sources.table.unknownSubject");
  }, [source, subjectsData, t]);

  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [windowStart, setWindowStart] = useState(0);
  const [viewerPageNumber, setViewerPageNumber] = useState<number | null>(
    () => {
      if (!routePageParam) {
        return null;
      }
      const parsed = Number.parseInt(routePageParam, 10);
      return Number.isNaN(parsed) ? null : parsed;
    },
  );

  useEffect(() => {
    if (routePageParam !== undefined) {
      const parsed = Number.parseInt(routePageParam, 10);
      if (!Number.isNaN(parsed)) {
        setViewerPageNumber(parsed);
      }
    }
  }, [routePageParam]);

  const totalPages = useMemo(() => {
    if (source?.page_count && source.page_count > 0) {
      return source.page_count;
    }
    if (pages.length > 0) {
      return pages.length;
    }
    if (source?.page_counts) {
      const sum = Object.values(source.page_counts).reduce(
        (acc, val) => acc + (typeof val === "number" ? val : 0),
        0,
      );
      return sum;
    }
    return 0;
  }, [pages.length, source]);

  const activePage = useMemo(() => {
    if (viewerPageNumber === null) {
      return null;
    }
    return (
      pages.find((p) => p.page_number === viewerPageNumber) ?? {
        id: `page-${String(viewerPageNumber)}`,
        page_number: viewerPageNumber,
        status: "rendered" as const,
        page_kind: null,
        width_px: 800,
        height_px: 1130,
        dpi: 150,
        error: null,
        created_at: "",
        updated_at: "",
      }
    );
  }, [pages, viewerPageNumber]);

  const orderedPageNumbers = useMemo(() => {
    if (pages.length > 0) {
      return pages.map((p) => p.page_number);
    }
    if (totalPages > 0) {
      return Array.from({ length: totalPages }, (_, idx) => idx + 1);
    }
    return [];
  }, [pages, totalPages]);

  const currentViewerIndex =
    viewerPageNumber !== null
      ? orderedPageNumbers.indexOf(viewerPageNumber)
      : -1;

  const hasPrevPage = currentViewerIndex > 0;
  const hasNextPage =
    currentViewerIndex !== -1 &&
    currentViewerIndex < orderedPageNumbers.length - 1;

  const goToPrevPage = useCallback(() => {
    if (currentViewerIndex > 0) {
      const prevNum = orderedPageNumbers[currentViewerIndex - 1];
      if (prevNum !== undefined) {
        setViewerPageNumber(prevNum);
      }
    }
  }, [currentViewerIndex, orderedPageNumbers]);

  const goToNextPage = useCallback(() => {
    if (
      currentViewerIndex !== -1 &&
      currentViewerIndex < orderedPageNumbers.length - 1
    ) {
      const nextNum = orderedPageNumbers[currentViewerIndex + 1];
      if (nextNum !== undefined) {
        setViewerPageNumber(nextNum);
      }
    }
  }, [currentViewerIndex, orderedPageNumbers]);

  useEffect(() => {
    if (viewerPageNumber === null) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }

      const isRtl =
        getDirection(i18n.language) === "rtl" ||
        document.documentElement.dir === "rtl";

      if (event.key === "ArrowLeft") {
        event.preventDefault();
        if (isRtl) {
          goToNextPage();
        } else {
          goToPrevPage();
        }
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        if (isRtl) {
          goToPrevPage();
        } else {
          goToNextPage();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [goToNextPage, goToPrevPage, i18n.language, viewerPageNumber]);

  const handleConfirmDelete = async () => {
    if (!id) {
      return;
    }
    await deleteMutation.mutateAsync(id);
    setIsDeleteDialogOpen(false);
    await navigate("/sources", { replace: true });
  };

  const isWindowed = pages.length > PAGE_GRID_WINDOW_SIZE;
  const visiblePages = useMemo(() => {
    if (!isWindowed) {
      return pages;
    }
    return pages.slice(windowStart, windowStart + PAGE_GRID_WINDOW_SIZE);
  }, [isWindowed, pages, windowStart]);

  if (isSourceLoading) {
    return (
      <section className="flex flex-col gap-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-36 w-full" />
        <Skeleton className="h-64 w-full" />
      </section>
    );
  }

  if (!source) {
    return null;
  }

  const pageCounts = source.page_counts;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <Link
            to="/sources"
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-xs font-medium"
          >
            <ArrowLeft className="size-3.5 rtl:rotate-180" aria-hidden="true" />
            <span>{t("sources.detail.backToSources")}</span>
          </Link>

          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {source.title}
            </h1>
            <SourceStatusBadge status={source.status} />
          </div>

          <div className="text-muted-foreground flex flex-wrap items-center gap-4 text-sm">
            <span>
              <strong className="text-foreground font-medium">
                {t("sources.detail.subject")}:
              </strong>{" "}
              {subjectName}
            </span>
            {source.grade ? (
              <span>
                <strong className="text-foreground font-medium">
                  {t("sources.detail.grade")}:
                </strong>{" "}
                {source.grade}
              </span>
            ) : null}
            <span>
              <strong className="text-foreground font-medium">
                {t("sources.detail.stage")}:
              </strong>{" "}
              <span data-testid="source-stage">
                {source.stage ?? t("sources.detail.noStage")}
              </span>
            </span>
            <span>
              <strong className="text-foreground font-medium">
                {t("sources.detail.cost")}:
              </strong>{" "}
              <span
                dir="ltr"
                data-testid="source-cost"
                className="font-mono tabular-nums"
              >
                {formatCostUsd(source.cost_usd)}
              </span>
            </span>
          </div>
        </div>

        {canWrite ? (
          <Button
            type="button"
            variant="destructive"
            size="sm"
            data-testid="delete-source-button"
            onClick={() => {
              setIsDeleteDialogOpen(true);
            }}
          >
            <Trash2 className="size-4" aria-hidden="true" />
            <span>{t("sources.detail.delete")}</span>
          </Button>
        ) : null}
      </div>

      {source.status === "paused" ? (
        <div
          role="alert"
          data-testid="source-paused-banner"
          className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-amber-800 dark:text-amber-200"
        >
          <PauseCircle className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
          <div className="flex flex-col gap-1">
            <p className="font-semibold">{t("sources.detail.pausedTitle")}</p>
            <p className="text-sm">
              {source.error ?? t("sources.detail.pausedDefaultReason")}
            </p>
          </div>
          {canWrite ? (
            <Button
              variant="outline"
              size="sm"
              className="ms-auto"
              disabled={resumeMutation.isPending}
              onClick={() => {
                resumeMutation.mutate(source.id);
              }}
            >
              {t("sources.detail.resume")}
            </Button>
          ) : null}
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t("sources.detail.progressTitle")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div
            aria-live="polite"
            data-testid="source-progress-section"
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          >
            {STAGE_KEYS.map((stageKey) => {
              const count = cumulativeStageCount(pageCounts, stageKey);
              const denominator = Math.max(totalPages, count, 1);
              const pct =
                totalPages > 0
                  ? Math.min(100, Math.round((count / denominator) * 100))
                  : count > 0
                    ? 100
                    : 0;
              const stageLabel = t(`sources.detail.stages.${stageKey}`);

              return (
                <div
                  key={stageKey}
                  data-testid={`stage-progress-${stageKey}`}
                  className="flex flex-col gap-1.5"
                >
                  <div className="flex items-center justify-between text-xs font-medium">
                    <span>{stageLabel}</span>
                    <span
                      dir="ltr"
                      data-testid={`stage-count-${stageKey}`}
                      className="font-mono tabular-nums"
                    >
                      {`${String(count)} / ${String(totalPages)}`}
                    </span>
                  </div>
                  <div
                    role="progressbar"
                    aria-label={stageLabel}
                    aria-valuenow={count}
                    aria-valuemin={0}
                    aria-valuemax={Math.max(totalPages, count)}
                    className="bg-muted h-2 w-full overflow-hidden rounded-full"
                  >
                    <div
                      className={cn(
                        "h-full transition-all duration-300",
                        stageKey === "failed"
                          ? "bg-destructive"
                          : stageKey === "validated"
                            ? "bg-emerald-600"
                            : "bg-primary",
                      )}
                      style={{ width: `${String(pct)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">
            {t("sources.detail.pagesTitle", { count: pages.length })}
          </h2>

          {isWindowed ? (
            <div
              data-testid="page-grid-window-controls"
              className="flex items-center gap-2 text-xs"
            >
              <span className="text-muted-foreground">
                {t("sources.detail.windowRange", {
                  start: windowStart + 1,
                  end: Math.min(
                    windowStart + PAGE_GRID_WINDOW_SIZE,
                    pages.length,
                  ),
                  total: pages.length,
                })}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={windowStart === 0}
                onClick={() => {
                  setWindowStart((prev) =>
                    Math.max(0, prev - PAGE_GRID_WINDOW_SIZE),
                  );
                }}
              >
                {t("sources.detail.prevRange")}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={windowStart + PAGE_GRID_WINDOW_SIZE >= pages.length}
                onClick={() => {
                  setWindowStart((prev) =>
                    Math.min(
                      Math.max(0, pages.length - PAGE_GRID_WINDOW_SIZE),
                      prev + PAGE_GRID_WINDOW_SIZE,
                    ),
                  );
                }}
              >
                {t("sources.detail.nextRange")}
              </Button>
            </div>
          ) : null}
        </div>

        {pages.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            {t("sources.detail.emptyPages")}
          </p>
        ) : (
          <div
            data-testid="page-grid"
            className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6"
          >
            {visiblePages.map((page) => (
              <PageThumbnailCard
                key={page.id}
                sourceId={id}
                page={page}
                onSelect={(pageNum) => {
                  setViewerPageNumber(pageNum);
                }}
              />
            ))}
          </div>
        )}
      </div>

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent data-testid="delete-confirm-dialog">
          <DialogHeader>
            <DialogTitle>{t("sources.detail.deleteConfirmTitle")}</DialogTitle>
            <DialogDescription>
              {t("sources.detail.deleteConfirmDescription", {
                title: source.title,
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={deleteMutation.isPending}
              onClick={() => {
                setIsDeleteDialogOpen(false);
              }}
            >
              {t("sources.detail.cancel")}
            </Button>
            <Button
              type="button"
              variant="destructive"
              disabled={deleteMutation.isPending}
              data-testid="confirm-delete-source"
              onClick={() => {
                void handleConfirmDelete();
              }}
            >
              {deleteMutation.isPending
                ? t("sources.detail.deleting")
                : t("sources.detail.deleteConfirmButton")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet
        open={activePage !== null}
        onOpenChange={(open) => {
          if (!open) {
            setViewerPageNumber(null);
          }
        }}
      >
        <SheetContent
          side="end"
          data-testid="page-viewer-sheet"
          className="w-full sm:max-w-3xl"
        >
          {activePage ? (
            <>
              <SheetHeader className="border-border flex flex-row items-center justify-between border-b pe-10">
                <div>
                  <SheetTitle data-testid="page-viewer-title">
                    {t("sources.detail.viewerTitle", {
                      number: activePage.page_number,
                      total:
                        orderedPageNumbers.length > 0
                          ? orderedPageNumbers.length
                          : totalPages,
                    })}
                  </SheetTitle>
                  <SheetDescription className="sr-only">
                    {t("sources.detail.pageNumber", {
                      number: activePage.page_number,
                    })}
                  </SheetDescription>
                </div>

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!hasPrevPage}
                    aria-label={t("sources.detail.prevPage")}
                    data-testid="viewer-prev-page"
                    onClick={goToPrevPage}
                  >
                    <ChevronLeft
                      className="size-4 rtl:rotate-180"
                      aria-hidden="true"
                    />
                    <span>{t("sources.detail.prevPage")}</span>
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!hasNextPage}
                    aria-label={t("sources.detail.nextPage")}
                    data-testid="viewer-next-page"
                    onClick={goToNextPage}
                  >
                    <span>{t("sources.detail.nextPage")}</span>
                    <ChevronRight
                      className="size-4 rtl:rotate-180"
                      aria-hidden="true"
                    />
                  </Button>
                </div>
              </SheetHeader>

              <div className="flex flex-1 overflow-hidden p-4">
                <PageCanvas
                  src={getPageImageUrl(id, activePage.page_number, "display")}
                  width={activePage.width_px ?? 800}
                  height={activePage.height_px ?? 1130}
                  regions={[]}
                  mode="view"
                  className="h-full w-full flex-1"
                />
              </div>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </section>
  );
}
