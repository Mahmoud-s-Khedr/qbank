import { useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useMe } from "@/api/hooks/auth";
import {
  type SourceDetail,
  type SourceOut,
  type SourceStatus,
  sourceDetailQueryKey,
  useSources,
} from "@/api/hooks/sources";
import { useSubjects } from "@/api/hooks/subjects";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { SourceStatusBadge } from "@/features/sources/status-badge";
import { UploadSourceDialog } from "@/features/sources/upload-source-dialog";
import { formatCostUsd, formatRelativeTime } from "@/lib/format";

const SOURCE_STATUSES: readonly SourceStatus[] = [
  "uploaded",
  "rendering",
  "extracting",
  "validating",
  "ready",
  "failed",
  "paused",
];

function formatSourcePages(
  source: SourceOut,
  cachedDetail?: SourceDetail,
): string {
  const inlineCounts = (
    source as SourceOut & { page_counts?: Record<string, number> | undefined }
  ).page_counts;
  const counts = inlineCounts ?? cachedDetail?.page_counts;

  if (counts) {
    const rendered =
      (counts.rendered ?? 0) +
      (counts.extracted ?? 0) +
      (counts.validated ?? 0);
    const failed = counts.failed ?? 0;
    const total =
      source.page_count ??
      counts.total ??
      (counts.pending ?? 0) + rendered + failed;
    return `${String(rendered)} / ${String(failed)} / ${String(total)}`;
  }

  const total = source.page_count ?? 0;
  const rendered = source.status === "ready" ? total : 0;
  return `${String(rendered)} / 0 / ${String(total)}`;
}

export function SourcesPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { data: user } = useMe();
  const { data: subjectsData } = useSubjects();

  const [subjectFilter, setSubjectFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<SourceStatus | "">("");
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  const canWrite = user?.role !== "teacher";

  const subjects = useMemo(
    () => (Array.isArray(subjectsData?.items) ? subjectsData.items : []),
    [subjectsData],
  );

  const subjectNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const subj of subjects) {
      map.set(subj.id, subj.name);
    }
    return map;
  }, [subjects]);

  const sourcesQuery = useSources({
    subjectId: subjectFilter || undefined,
    status: statusFilter || undefined,
  });

  const items = useMemo(() => {
    if (!sourcesQuery.data?.pages) {
      return [];
    }
    const list: SourceOut[] = [];
    for (const page of sourcesQuery.data.pages) {
      if (Array.isArray(page.items)) {
        list.push(...page.items);
      }
    }
    return list;
  }, [sourcesQuery.data]);

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold tracking-tight">
          {t("pages.sources.title")}
        </h1>

        {canWrite ? (
          <Button
            type="button"
            data-testid="upload-workbook-button"
            onClick={() => {
              setIsUploadOpen(true);
            }}
          >
            <Plus className="size-4" aria-hidden="true" />
            <span>{t("sources.uploadWorkbook")}</span>
          </Button>
        ) : null}
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <div className="flex min-w-44 flex-col gap-1.5">
          <Label htmlFor="filter-subject">{t("sources.filters.subject")}</Label>
          <select
            id="filter-subject"
            data-testid="filter-subject"
            value={subjectFilter}
            onChange={(event) => {
              setSubjectFilter(event.target.value);
            }}
            className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
          >
            <option value="">{t("sources.filters.allSubjects")}</option>
            {subjects.map((subj) => (
              <option key={subj.id} value={subj.id}>
                {subj.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex min-w-44 flex-col gap-1.5">
          <Label htmlFor="filter-status">{t("sources.filters.status")}</Label>
          <select
            id="filter-status"
            data-testid="filter-status"
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value as SourceStatus | "");
            }}
            className="border-input bg-background focus-visible:border-ring focus-visible:ring-ring/50 flex h-9 w-full rounded-md border px-3 py-1 text-sm shadow-xs outline-none focus-visible:ring-[3px]"
          >
            <option value="">{t("sources.filters.allStatuses")}</option>
            {SOURCE_STATUSES.map((st) => (
              <option key={st} value={st}>
                {t(`sources.status.${st}`)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {items.length === 0 ? (
        <EmptyState
          icon={BookOpen}
          title={t("pages.sources.emptyTitle")}
          description={t("pages.sources.emptyDescription")}
        >
          {canWrite ? (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setIsUploadOpen(true);
              }}
            >
              <Plus className="size-4" aria-hidden="true" />
              <span>{t("sources.uploadWorkbook")}</span>
            </Button>
          ) : null}
        </EmptyState>
      ) : (
        <div className="border-border bg-card overflow-x-auto rounded-lg border">
          <table className="w-full border-collapse text-start text-sm">
            <thead>
              <tr className="border-border bg-muted/40 border-b">
                <th className="px-4 py-3 text-start font-medium">
                  {t("sources.table.title")}
                </th>
                <th className="px-4 py-3 text-start font-medium">
                  {t("sources.table.subject")}
                </th>
                <th className="px-4 py-3 text-start font-medium">
                  {t("sources.table.status")}
                </th>
                <th className="px-4 py-3 text-start font-medium">
                  {t("sources.table.pages")}
                </th>
                <th className="px-4 py-3 text-start font-medium">
                  {t("sources.table.cost")}
                </th>
                <th className="px-4 py-3 text-start font-medium">
                  {t("sources.table.created")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {items.map((source) => {
                const cachedDetail = queryClient.getQueryData<SourceDetail>(
                  sourceDetailQueryKey(source.id),
                );
                const subjectName =
                  subjectNameById.get(source.subject_id) ??
                  t("sources.table.unknownSubject");

                return (
                  <tr
                    key={source.id}
                    data-testid={`source-row-${source.id}`}
                    className="hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium">
                      <Link
                        to={`/sources/${source.id}`}
                        className="text-primary hover:underline focus-visible:underline focus-visible:outline-none"
                      >
                        {source.title}
                      </Link>
                      {source.grade ? (
                        <span className="text-muted-foreground ms-2 text-xs">
                          ({source.grade})
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">{subjectName}</td>
                    <td className="px-4 py-3">
                      <SourceStatusBadge status={source.status} />
                    </td>
                    <td className="px-4 py-3">
                      <span dir="ltr" className="font-mono tabular-nums">
                        {formatSourcePages(source, cachedDetail)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span dir="ltr" className="font-mono tabular-nums">
                        {formatCostUsd(source.cost_usd)}
                      </span>
                    </td>
                    <td className="text-muted-foreground px-4 py-3">
                      <time dateTime={source.created_at}>
                        {formatRelativeTime(source.created_at, i18n.language)}
                      </time>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {sourcesQuery.hasNextPage ? (
        <div className="flex justify-center">
          <Button
            type="button"
            variant="outline"
            data-testid="sources-load-more"
            disabled={sourcesQuery.isFetchingNextPage}
            onClick={() => {
              void sourcesQuery.fetchNextPage();
            }}
          >
            {sourcesQuery.isFetchingNextPage
              ? t("sources.loadingMore")
              : t("sources.loadMore")}
          </Button>
        </div>
      ) : null}

      {canWrite ? (
        <UploadSourceDialog
          open={isUploadOpen}
          onOpenChange={setIsUploadOpen}
        />
      ) : null}
    </section>
  );
}
