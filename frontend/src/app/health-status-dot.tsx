import { useTranslation } from "react-i18next";
import { useHealth } from "@/api/hooks/health";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export type HealthIndicatorState =
  "ok" | "db-down" | "unreachable" | "checking";

export function HealthStatusDot() {
  const { t } = useTranslation();
  const { data, isError, isPending } = useHealth();

  let statusState: HealthIndicatorState = "checking";
  let dotColorClass = "bg-muted-foreground";
  let statusText = t("health.checking");

  if (isError) {
    statusState = "unreachable";
    dotColorClass = "bg-red-500";
    statusText = t("health.unreachable");
  } else if (data?.db === "down") {
    statusState = "db-down";
    dotColorClass = "bg-amber-500";
    statusText = t("health.dbDown");
  } else if (data?.db === "ok") {
    statusState = "ok";
    dotColorClass = "bg-green-500";
    statusText = t("health.ok");
  } else if (!isPending) {
    statusState = "unreachable";
    dotColorClass = "bg-red-500";
    statusText = t("health.unreachable");
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={statusText}
          data-testid="health-status-dot"
          data-status={statusState}
          className="focus-visible:ring-ring/50 inline-flex size-8 items-center justify-center rounded-md outline-none focus-visible:ring-[3px]"
        >
          <span
            aria-hidden="true"
            className={cn("inline-block size-2.5 rounded-full", dotColorClass)}
          />
          <span role="status" className="sr-only">
            {statusText}
          </span>
        </button>
      </TooltipTrigger>
      <TooltipContent>{statusText}</TooltipContent>
    </Tooltip>
  );
}
