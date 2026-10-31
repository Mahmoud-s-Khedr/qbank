import { Calendar, CheckCircle2, Clock, ExternalLink, Tag } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useQuestion, useQuestionHistory } from "@/api/hooks/bank";
import { assetImageUrl, useSourceStimuli } from "@/api/hooks/review";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { DifficultyDots } from "@/features/bank/difficulty-dots";
import { StatusChip } from "@/features/review/status-chip";
import { formatRelativeTime } from "@/lib/format";

export interface QuestionDrawerProps {
  questionId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  canEdit: boolean;
}

export function QuestionDrawer({
  questionId,
  open,
  onOpenChange,
  canEdit,
}: QuestionDrawerProps) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "ar" ? "ar" : "en";

  const questionQuery = useQuestion(open ? questionId : null);
  const question = questionQuery.data;

  const stimuliQuery = useSourceStimuli(question?.source_id ?? "");
  const stimulus = question?.stimulus_id
    ? stimuliQuery.data?.find((s) => s.id === question.stimulus_id)
    : undefined;

  const historyQuery = useQuestionHistory(canEdit && open ? questionId : null);
  const historyEvents = historyQuery.data ?? [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="end"
        className="w-full overflow-y-auto sm:max-w-xl md:max-w-2xl"
        data-testid="question-detail-drawer"
      >
        <SheetHeader>
          <div className="flex flex-wrap items-center justify-between gap-2 pe-6">
            <SheetTitle className="text-xl font-bold">
              {question ? question.number_label : t("bank.drawer.title")}
            </SheetTitle>
            {question && (
              <div className="flex items-center gap-2">
                <Badge variant="outline">
                  {t(`bank.question.types.${question.type}`, {
                    defaultValue: question.type,
                  })}
                </Badge>
                <DifficultyDots difficulty={question.difficulty} />
                <StatusChip status={question.status} />
              </div>
            )}
          </div>
          <SheetDescription className="sr-only">
            {t("bank.drawer.title")}
          </SheetDescription>
        </SheetHeader>

        {questionQuery.isLoading ? (
          <div className="flex flex-col gap-4 p-4">
            <Skeleton className="h-6 w-1/3" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : question ? (
          <div className="flex flex-col gap-6 p-4 pt-0">
            {canEdit && question.source_id && (
              <div className="flex justify-end">
                <Button variant="outline" size="sm" asChild>
                  <Link
                    to={`/sources/${question.source_id}/review?question=${question.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1.5"
                  >
                    <span>{t("bank.drawer.openInReview")}</span>
                    <ExternalLink className="size-3.5" aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            )}

            {stimulus && (
              <section
                aria-label={t("bank.drawer.stimulus")}
                className="bg-muted/30 rounded-lg border p-4"
              >
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                    {t("bank.drawer.stimulus")} · {stimulus.kind}
                  </span>
                </div>
                <QmdRenderer
                  source={stimulus.content}
                  lang={lang}
                  resolveAsset={assetImageUrl}
                  className="text-sm"
                />
              </section>
            )}

            <section
              aria-label={t("bank.drawer.stem")}
              className="flex flex-col gap-2"
            >
              <h4 className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                {t("bank.drawer.stem")}
              </h4>
              <div className="text-foreground text-base leading-relaxed">
                <QmdRenderer
                  source={question.stem}
                  lang={lang}
                  resolveAsset={assetImageUrl}
                />
              </div>
            </section>

            {question.choices.length > 0 && (
              <section
                aria-label={t("bank.drawer.choices")}
                className="flex flex-col gap-3"
              >
                <h4 className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                  {t("bank.drawer.choices")}
                </h4>
                <div className="grid gap-2">
                  {question.choices.map((choiceRaw, idx) => {
                    const choice = choiceRaw as {
                      label?: string;
                      content?: string;
                      is_correct?: boolean;
                    };
                    const isCorrect =
                      choice.is_correct === true ||
                      (question.answer && choice.label === question.answer);
                    return (
                      <div
                        key={idx}
                        className={`flex items-start gap-3 rounded-md border p-3 text-sm transition-colors ${
                          isCorrect
                            ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-950 dark:text-emerald-100"
                            : "border-border bg-card"
                        }`}
                      >
                        <span className="bg-muted flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold">
                          {choice.label ?? String.fromCharCode(65 + idx)}
                        </span>
                        <div className="flex-1">
                          <QmdRenderer
                            source={choice.content ?? ""}
                            inline
                            lang={lang}
                            resolveAsset={assetImageUrl}
                          />
                        </div>
                        {isCorrect && (
                          <Badge
                            variant="success"
                            className="shrink-0 gap-1 px-1.5 py-0.5 text-xs font-medium"
                          >
                            <CheckCircle2
                              className="size-3"
                              aria-hidden="true"
                            />
                            <span>{t("bank.drawer.correct")}</span>
                          </Badge>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {(Boolean(question.answer) || Boolean(question.explanation)) && (
              <section className="bg-muted/20 flex flex-col gap-3 rounded-lg border p-4">
                {question.answer && (
                  <div>
                    <h4 className="text-muted-foreground mb-1 text-xs font-semibold tracking-wider uppercase">
                      {t("bank.drawer.answer")}
                    </h4>
                    <div className="text-sm">
                      <QmdRenderer
                        source={question.answer}
                        lang={lang}
                        resolveAsset={assetImageUrl}
                      />
                    </div>
                  </div>
                )}
                {question.explanation && (
                  <div>
                    <h4 className="text-muted-foreground mb-1 text-xs font-semibold tracking-wider uppercase">
                      {t("bank.drawer.explanation")}
                    </h4>
                    <div className="text-muted-foreground text-sm">
                      <QmdRenderer
                        source={question.explanation}
                        lang={lang}
                        resolveAsset={assetImageUrl}
                      />
                    </div>
                  </div>
                )}
              </section>
            )}

            <Separator />

            <section
              aria-label={t("bank.drawer.metadata")}
              className="flex flex-col gap-3"
            >
              <h4 className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                {t("bank.drawer.metadata")}
              </h4>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground text-xs">
                    {t("bank.drawer.created")}
                  </span>
                  <div className="flex items-center gap-1.5 pt-0.5 font-medium">
                    <Calendar className="text-muted-foreground size-3.5" />
                    <span>{formatRelativeTime(question.created_at, lang)}</span>
                  </div>
                </div>
                <div>
                  <span className="text-muted-foreground text-xs">
                    {t("bank.drawer.updated")}
                  </span>
                  <div className="flex items-center gap-1.5 pt-0.5 font-medium">
                    <Clock className="text-muted-foreground size-3.5" />
                    <span>{formatRelativeTime(question.updated_at, lang)}</span>
                  </div>
                </div>
              </div>

              {question.tags.length > 0 && (
                <div className="pt-2">
                  <span className="text-muted-foreground text-xs">
                    {t("bank.filters.tags")}
                  </span>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {question.tags.map((tag) => (
                      <Badge
                        key={tag}
                        variant="secondary"
                        className="gap-1 px-2 py-0.5 text-xs font-normal"
                      >
                        <Tag className="size-3" aria-hidden="true" />
                        <span>{tag}</span>
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </section>

            {canEdit && (
              <>
                <Separator />
                <section
                  aria-label={t("bank.drawer.history")}
                  className="flex flex-col gap-3"
                >
                  <h4 className="text-muted-foreground text-xs font-semibold tracking-wider uppercase">
                    {t("bank.drawer.history")}
                  </h4>
                  {historyEvents.length === 0 ? (
                    <p className="text-muted-foreground text-sm">
                      {t("bank.drawer.noHistory")}
                    </p>
                  ) : (
                    <div className="divide-border divide-y rounded-md border">
                      {historyEvents.map((evt) => (
                        <div
                          key={evt.id}
                          className="flex flex-col gap-1 p-3 text-xs"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-foreground font-semibold">
                              {evt.action}
                            </span>
                            <span className="text-muted-foreground">
                              {formatRelativeTime(evt.created_at, lang)}
                            </span>
                          </div>
                          {evt.user_id && (
                            <span className="text-muted-foreground">
                              User: {evt.user_id}
                            </span>
                          )}
                          {Object.keys(evt.diff).length > 0 && (
                            <pre className="bg-muted text-muted-foreground mt-1 overflow-x-auto rounded p-1 text-[11px]">
                              {JSON.stringify(evt.diff, null, 2)}
                            </pre>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              </>
            )}
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
