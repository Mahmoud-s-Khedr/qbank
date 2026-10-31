import { useQueries } from "@tanstack/react-query";
import { ClipboardCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { fetchReviewQueue, queueKey } from "@/api/hooks/review";
import { useSources } from "@/api/hooks/sources";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const NEEDS_REVIEW = {
  status: "needs_review",
  severity: "",
  sort: "page",
} as const;

/** The Review nav item: sources that still have questions waiting for review. */
export function ReviewPage() {
  const { t } = useTranslation();
  const sources = useSources({});
  const list = (sources.data?.pages ?? []).flatMap((page) =>
    Array.isArray(page.items) ? page.items : [],
  );
  const queues = useQueries({
    queries: list.map((source) => ({
      queryKey: queueKey(source.id, NEEDS_REVIEW),
      queryFn: () => fetchReviewQueue(source.id, NEEDS_REVIEW),
    })),
  });
  const rows = list.flatMap((source, i) => {
    const count = queues[i]?.data?.totals.count ?? 0;
    return count > 0
      ? [
          {
            source,
            count,
            errors: queues[i]?.data?.totals.by_severity.error ?? 0,
          },
        ]
      : [];
  });
  const loading = sources.isLoading || queues.some((q) => q.isLoading);

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("pages.review.title")}
      </h1>
      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={ClipboardCheck}
          title={t("pages.review.emptyTitle")}
          description={t("pages.review.emptyDescription")}
        />
      ) : (
        <ul className="flex flex-col gap-3" data-testid="review-sources">
          {rows.map(({ source, count, errors }) => (
            <li
              key={source.id}
              className="border-border bg-card flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4"
            >
              <div className="flex flex-col gap-1">
                <span className="font-semibold">{source.title}</span>
                <span className="text-muted-foreground text-sm">
                  {t("review.list.pending", { count })} ·{" "}
                  {t("review.list.errors", { count: errors })}
                </span>
              </div>
              <Button asChild>
                <Link to={`/sources/${source.id}/review`}>
                  {t("review.list.open")}
                </Link>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
