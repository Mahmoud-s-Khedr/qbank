import { Check, CircleDashed, Eye, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";

const CONFIG = {
  draft: { icon: CircleDashed, variant: "secondary" },
  needs_review: { icon: Eye, variant: "warning" },
  approved: { icon: Check, variant: "success" },
  rejected: { icon: X, variant: "destructive" },
} as const;

export function StatusChip({ status }: { status: string }) {
  const { t } = useTranslation();
  const config =
    status in CONFIG ? CONFIG[status as keyof typeof CONFIG] : undefined;
  const Icon = config?.icon ?? CircleDashed;
  return (
    <Badge
      variant={config?.variant ?? "outline"}
      className="shrink-0 px-2 py-0 text-[11px]"
    >
      <Icon className="size-3" aria-hidden="true" />
      {config ? t(`review.status.${status}`) : status}
    </Badge>
  );
}
