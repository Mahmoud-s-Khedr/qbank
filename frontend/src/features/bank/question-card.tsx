import {
  AlertCircle,
  AlertTriangle,
  BookOpen,
  FolderTree,
  ImageIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BankQuestionOut } from "@/api/hooks/bank";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DifficultyDots } from "@/features/bank/difficulty-dots";
import { StatusChip } from "@/features/review/status-chip";
import { cn } from "@/lib/utils";

export interface QuestionCardProps {
  question: BankQuestionOut;
  selected: boolean;
  onToggleSelect: (shiftKey: boolean) => void;
  onClick: () => void;
  showStatus?: boolean;
}

export function QuestionCard({
  question,
  selected,
  onToggleSelect,
  onClick,
  showStatus = true,
}: QuestionCardProps) {
  const { t } = useTranslation();

  const errorsCount = question.issues_count.error;
  const warningsCount = question.issues_count.warning;
  const hasIssues = errorsCount > 0 || warningsCount > 0;

  return (
    <Card
      role="article"
      tabIndex={0}
      data-testid={`question-card-${question.id}`}
      aria-labelledby={`card-heading-${question.id}`}
      onClick={onClick}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick();
        }
      }}
      className={cn(
        "group hover:border-primary/50 focus-visible:ring-ring relative flex cursor-pointer flex-col gap-3 rounded-lg border p-4 transition-all hover:shadow-sm focus-visible:ring-2 focus-visible:outline-none",
        selected && "border-primary bg-primary/5 shadow-xs",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={selected}
            aria-label={t("review.bulk.select", {
              label: question.number_label,
            })}
            className="border-muted-foreground/40 text-primary accent-primary focus:ring-ring size-4 rounded-xs"
            onClick={(event) => {
              event.stopPropagation();
              onToggleSelect(event.shiftKey);
            }}
            onChange={() => {
              // handled in onClick for shiftKey detection
            }}
          />
          <h3
            id={`card-heading-${question.id}`}
            className="text-foreground text-base font-semibold tracking-tight"
          >
            {question.number_label}
          </h3>
          <Badge variant="outline" className="text-xs">
            {t(`bank.question.types.${question.type}`, {
              defaultValue: question.type,
            })}
          </Badge>
          <DifficultyDots difficulty={question.difficulty} />
        </div>

        <div className="flex items-center gap-2">
          {question.has_figure && (
            <Badge
              variant="secondary"
              className="px-1.5 py-0.5 text-xs"
              title={t("bank.question.hasFigure")}
            >
              <ImageIcon className="size-3.5" aria-hidden="true" />
              <span className="sr-only">{t("bank.question.hasFigure")}</span>
            </Badge>
          )}

          {hasIssues && (
            <Badge
              variant={errorsCount > 0 ? "destructive" : "warning"}
              className="gap-1 px-1.5 py-0.5 text-xs"
              title={t("bank.question.issues", {
                count: errorsCount + warningsCount,
              })}
            >
              {errorsCount > 0 ? (
                <AlertCircle className="size-3.5" aria-hidden="true" />
              ) : (
                <AlertTriangle className="size-3.5" aria-hidden="true" />
              )}
              <span>{errorsCount + warningsCount}</span>
            </Badge>
          )}

          {showStatus && <StatusChip status={question.status} />}
        </div>
      </div>

      <div className="text-foreground/90 line-clamp-3 text-sm">
        <QmdRenderer source={question.stem_preview} inline lang="ar" />
      </div>

      <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-2 pt-1 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          {(Boolean(question.chapter_title) ||
            Boolean(question.lesson_title)) && (
            <div className="flex items-center gap-1 font-medium">
              <FolderTree className="size-3.5 shrink-0" aria-hidden="true" />
              <span>
                {[question.chapter_title, question.lesson_title]
                  .filter(Boolean)
                  .join(" / ")}
              </span>
            </div>
          )}

          {question.source_title && (
            <div className="flex items-center gap-1">
              <BookOpen className="size-3.5 shrink-0" aria-hidden="true" />
              <span>
                {question.source_page !== null
                  ? t("bank.question.sourcePage", {
                      source: question.source_title,
                      page: question.source_page,
                    })
                  : question.source_title}
              </span>
            </div>
          )}
        </div>

        {question.tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            {question.tags.slice(0, 4).map((tag) => (
              <span
                key={tag}
                className="bg-muted text-muted-foreground rounded-sm px-1.5 py-0.5 text-[11px] font-normal"
              >
                #{tag}
              </span>
            ))}
            {question.tags.length > 4 && (
              <span className="text-muted-foreground text-[11px]">
                +{question.tags.length - 4}
              </span>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
