import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  PauseCircle,
  Upload,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { PageKind, PageStatus, SourceStatus } from "@/api/hooks/sources";
import { Badge, type BadgeProps } from "@/components/ui/badge";

const SOURCE_STATUS_VARIANTS: Record<SourceStatus, BadgeProps["variant"]> = {
  uploaded: "secondary",
  rendering: "info",
  extracting: "info",
  validating: "info",
  ready: "success",
  failed: "destructive",
  paused: "warning",
};

export function SourceStatusBadge({ status }: { status: SourceStatus }) {
  const { t } = useTranslation();
  const variant = SOURCE_STATUS_VARIANTS[status];

  const renderIcon = () => {
    switch (status) {
      case "uploaded":
        return <Upload className="size-3.5 shrink-0" aria-hidden="true" />;
      case "rendering":
      case "extracting":
      case "validating":
        return (
          <Loader2
            className="size-3.5 shrink-0 animate-spin"
            aria-hidden="true"
          />
        );
      case "ready":
        return (
          <CheckCircle2 className="size-3.5 shrink-0" aria-hidden="true" />
        );
      case "failed":
        return <AlertCircle className="size-3.5 shrink-0" aria-hidden="true" />;
      case "paused":
        return <PauseCircle className="size-3.5 shrink-0" aria-hidden="true" />;
    }
  };

  return (
    <Badge
      variant={variant}
      data-testid="source-status-badge"
      data-status={status}
    >
      {renderIcon()}
      <span>{t(`sources.status.${status}`)}</span>
    </Badge>
  );
}

const PAGE_STATUS_VARIANTS: Record<PageStatus, BadgeProps["variant"]> = {
  pending: "secondary",
  rendered: "info",
  extracted: "info",
  validated: "success",
  failed: "destructive",
};

export function PageStatusBadge({ status }: { status: PageStatus }) {
  const { t } = useTranslation();
  const variant = PAGE_STATUS_VARIANTS[status];

  const renderIcon = () => {
    switch (status) {
      case "pending":
        return <Clock className="size-3 shrink-0" aria-hidden="true" />;
      case "rendered":
      case "extracted":
        return <Loader2 className="size-3 shrink-0" aria-hidden="true" />;
      case "validated":
        return <CheckCircle2 className="size-3 shrink-0" aria-hidden="true" />;
      case "failed":
        return <AlertCircle className="size-3 shrink-0" aria-hidden="true" />;
    }
  };

  return (
    <Badge
      variant={variant}
      data-testid="page-status-badge"
      data-status={status}
    >
      {renderIcon()}
      <span>{t(`sources.detail.pageStatus.${status}`)}</span>
    </Badge>
  );
}

export function PageKindChip({ kind }: { kind: PageKind }) {
  const { t } = useTranslation();
  return (
    <Badge variant="outline" data-testid="page-kind-chip" data-kind={kind}>
      {t(`sources.detail.pageKind.${kind}`)}
    </Badge>
  );
}
