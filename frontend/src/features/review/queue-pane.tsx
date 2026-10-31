import { CheckCheck, FileText, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type {
  QueueFilters,
  QueueItem,
  QueueSeverityFilter,
  QueueSort,
  QueueStatusFilter,
  ReviewQueue,
} from "@/api/hooks/review";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { SeverityIcon } from "./dialogs";
import { StatusChip } from "./status-chip";

export const QUEUE_ROW_HEIGHT = 56;
const OVERSCAN = 6;
const FALLBACK_VIEWPORT = 560;

const STATUS_OPTIONS: readonly QueueStatusFilter[] = [
  "",
  "draft",
  "needs_review",
  "approved",
  "rejected",
];
const SEVERITY_OPTIONS: readonly QueueSeverityFilter[] = [
  "",
  "error",
  "warning",
];
const SORT_OPTIONS: readonly QueueSort[] = ["page", "severity", "confidence"];

export function QueuePane({
  queue,
  isLoading,
  isError,
  filters,
  onFiltersChange,
  selectedId,
  onSelect,
  checked,
  onCheckedChange,
  onBulkApprove,
  onBulkReject,
  onBulkMetadata,
  listRef,
}: {
  queue: ReviewQueue | undefined;
  isLoading: boolean;
  isError: boolean;
  filters: QueueFilters;
  onFiltersChange: (filters: QueueFilters) => void;
  selectedId: string | undefined;
  onSelect: (id: string) => void;
  checked: ReadonlySet<string>;
  onCheckedChange: (checked: Set<string>) => void;
  onBulkApprove: () => void;
  onBulkReject: () => void;
  onBulkMetadata: () => void;
  listRef: React.RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  const items = queue?.items ?? [];
  const [scrollTop, setScrollTop] = useState(0);
  const lastCheckedRef = useRef<number | null>(null);

  const measured = listRef.current?.clientHeight ?? 0;
  const viewport = measured > 0 ? measured : FALLBACK_VIEWPORT;
  const first = Math.max(
    0,
    Math.floor(scrollTop / QUEUE_ROW_HEIGHT) - OVERSCAN,
  );
  const last = Math.min(
    items.length,
    Math.ceil((scrollTop + viewport) / QUEUE_ROW_HEIGHT) + OVERSCAN,
  );
  const visible = items.slice(first, last);

  const selectedIndex = items.findIndex((item) => item.id === selectedId);
  useEffect(() => {
    const el = listRef.current;
    if (!el || selectedIndex < 0) return;
    const top = selectedIndex * QUEUE_ROW_HEIGHT;
    const height = el.clientHeight || FALLBACK_VIEWPORT;
    if (top < el.scrollTop) {
      el.scrollTop = top;
    } else if (top + QUEUE_ROW_HEIGHT > el.scrollTop + height) {
      el.scrollTop = top + QUEUE_ROW_HEIGHT - height;
    }
  }, [selectedIndex, listRef]);

  const toggle = (index: number, shiftKey: boolean) => {
    const next = new Set(checked);
    const item = items[index];
    if (!item) return;
    if (shiftKey && lastCheckedRef.current !== null) {
      const [from, to] = [lastCheckedRef.current, index].sort((a, b) => a - b);
      for (let i = from ?? 0; i <= (to ?? 0); i += 1) {
        const id = items[i]?.id;
        if (id) next.add(id);
      }
    } else if (next.has(item.id)) {
      next.delete(item.id);
    } else {
      next.add(item.id);
    }
    lastCheckedRef.current = index;
    onCheckedChange(next);
  };

  const totals = queue?.totals;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <div className="flex flex-col gap-2 px-2 pt-2">
        <div
          className="flex flex-wrap items-center gap-2 text-xs"
          data-testid="queue-totals"
        >
          <span className="font-semibold">
            {t("review.queue.total", { count: totals?.count ?? 0 })}
          </span>
          <span className="inline-flex items-center gap-1">
            <SeverityIcon severity="error" />
            <span className="sr-only">{t("review.severity.error")}</span>
            {totals?.by_severity.error ?? 0}
          </span>
          <span className="inline-flex items-center gap-1">
            <SeverityIcon severity="warning" />
            <span className="sr-only">{t("review.severity.warning")}</span>
            {totals?.by_severity.warning ?? 0}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-1">
          <label className="flex flex-col text-[11px]">
            {t("review.queue.status")}
            <select
              className="border-input bg-background h-8 rounded-md border px-1 text-xs"
              value={filters.status}
              onChange={(event) => {
                onFiltersChange({
                  ...filters,
                  status: event.target.value as QueueStatusFilter,
                });
              }}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s === "" ? t("review.queue.all") : t(`review.status.${s}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-[11px]">
            {t("review.queue.severity")}
            <select
              className="border-input bg-background h-8 rounded-md border px-1 text-xs"
              value={filters.severity}
              onChange={(event) => {
                onFiltersChange({
                  ...filters,
                  severity: event.target.value as QueueSeverityFilter,
                });
              }}
            >
              {SEVERITY_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s === "" ? t("review.queue.all") : t(`review.severity.${s}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col text-[11px]">
            {t("review.queue.sort")}
            <select
              className="border-input bg-background h-8 rounded-md border px-1 text-xs"
              value={filters.sort}
              onChange={(event) => {
                onFiltersChange({
                  ...filters,
                  sort: event.target.value as QueueSort,
                });
              }}
            >
              {SORT_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {t(`review.queue.sortBy.${s}`)}
                </option>
              ))}
            </select>
          </label>
        </div>
        {checked.size > 0 ? (
          <div
            className="bg-muted flex flex-wrap items-center gap-1 rounded-md p-1"
            data-testid="bulk-bar"
          >
            <span className="px-1 text-xs font-medium">
              {t("review.bulk.selected", { count: checked.size })}
            </span>
            <Button type="button" size="sm" onClick={onBulkApprove}>
              <CheckCheck aria-hidden="true" />
              {t("review.actions.approve")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onBulkReject}
            >
              {t("review.actions.reject")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onBulkMetadata}
            >
              {t("review.bulk.metadata")}
            </Button>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-8"
              aria-label={t("review.bulk.clear")}
              onClick={() => {
                onCheckedChange(new Set());
              }}
            >
              <X aria-hidden="true" />
            </Button>
          </div>
        ) : null}
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-2 px-2">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : isError ? (
        <p role="alert" className="text-destructive px-2 text-sm">
          {t("review.queue.error")}
        </p>
      ) : items.length === 0 ? (
        <p className="text-muted-foreground px-2 text-sm">
          {t("review.queue.empty")}
        </p>
      ) : (
        <div
          ref={listRef}
          role="listbox"
          aria-label={t("review.queue.label")}
          aria-multiselectable="false"
          data-testid="queue-list"
          className="min-h-0 flex-1 overflow-auto"
          onScroll={(event) => {
            setScrollTop(event.currentTarget.scrollTop);
          }}
        >
          <div
            role="presentation"
            className="relative"
            style={{ height: items.length * QUEUE_ROW_HEIGHT }}
          >
            {visible.map((item, offset) => {
              const index = first + offset;
              return (
                <QueueRow
                  key={item.id}
                  item={item}
                  index={index}
                  selected={item.id === selectedId}
                  checked={checked.has(item.id)}
                  onSelect={onSelect}
                  onToggle={toggle}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function QueueRow({
  item,
  index,
  selected,
  checked,
  onSelect,
  onToggle,
}: {
  item: QueueItem;
  index: number;
  selected: boolean;
  checked: boolean;
  onSelect: (id: string) => void;
  onToggle: (index: number, shiftKey: boolean) => void;
}) {
  const { t } = useTranslation();
  const errors = item.issues.error ?? 0;
  const warnings = item.issues.warning ?? 0;
  return (
    <div
      role="presentation"
      className={cn(
        "border-border absolute inset-x-0 flex items-center gap-2 border-b px-2",
        selected && "bg-accent",
      )}
      style={{ top: index * QUEUE_ROW_HEIGHT, height: QUEUE_ROW_HEIGHT }}
    >
      <input
        type="checkbox"
        checked={checked}
        aria-label={t("review.bulk.select", { label: item.number_label })}
        onChange={() => {
          // The toggle runs from onClick so Shift-click ranges can see the key.
        }}
        onClick={(event) => {
          onToggle(index, event.shiftKey);
        }}
      />
      <div
        role="option"
        id={`queue-option-${item.id}`}
        aria-selected={selected}
        tabIndex={selected ? 0 : -1}
        data-testid={`queue-item-${item.id}`}
        className="focus-visible:ring-ring/50 flex min-w-0 flex-1 cursor-pointer flex-col gap-1 rounded-md py-1 outline-none focus-visible:ring-[3px]"
        onClick={() => {
          onSelect(item.id);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect(item.id);
          }
        }}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-sm font-semibold">
            {item.number_label || t("review.queue.noLabel")}
          </span>
          <StatusChip status={item.status} />
        </div>
        <div className="text-muted-foreground flex items-center gap-3 text-xs">
          <span className="inline-flex items-center gap-1">
            <FileText className="size-3.5" aria-hidden="true" />
            {t("review.queue.page", { page: item.page ?? "—" })}
          </span>
          <span
            className="inline-flex items-center gap-1"
            title={t("review.severity.error")}
          >
            <SeverityIcon severity="error" />
            <span className="sr-only">{t("review.severity.error")}</span>
            {errors}
          </span>
          <span
            className="inline-flex items-center gap-1"
            title={t("review.severity.warning")}
          >
            <SeverityIcon severity="warning" />
            <span className="sr-only">{t("review.severity.warning")}</span>
            {warnings}
          </span>
          <Badge variant="outline" className="px-1.5 py-0 text-[10px]">
            {Math.round(item.confidence * 100)}%
          </Badge>
        </div>
      </div>
    </div>
  );
}
