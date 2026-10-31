import { Loader2, Sparkles } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useCompose,
  useExamMutations,
  useProposals,
  type ExamDetail,
  type ExamProposal,
} from "@/api/hooks/exams";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatCostUsd } from "@/lib/format";
import { errorCode, errorStatus } from "./exam-model";
import { QuestionList } from "./question-list";
import { useQuestionsById } from "./use-questions";
import { useErrorText } from "./use-error-text";

const EXAMPLES = ["ar1", "ar2", "en1", "en2"] as const;

export function AiTab({
  exam,
  mutations,
}: {
  exam: ExamDetail;
  mutations: ReturnType<typeof useExamMutations>;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const compose = useCompose(exam.id);
  const proposals = useProposals(exam.id);
  const [prompt, setPrompt] = useState("");
  const [language, setLanguage] = useState<"ar" | "en">(exam.settings.language);
  const [proposal, setProposal] = useState<ExamProposal | null>(null);
  const [removed, setRemoved] = useState<Set<string>>(new Set());
  const [failure, setFailure] = useState<"budget" | "failed" | "other" | null>(
    null,
  );
  const [message, setMessage] = useState("");
  const [done, setDone] = useState("");

  const ids = proposal?.selection.flat() ?? [];
  const questions = useQuestionsById(ids);

  const submit = () => {
    const text = prompt.trim();
    if (!text) return;
    setFailure(null);
    setMessage("");
    setDone("");
    compose.mutate(
      { prompt: text, language },
      {
        onSuccess: (data) => {
          setProposal(data);
          setRemoved(new Set());
        },
        onError: (e) => {
          const status = errorStatus(e);
          if (status === 402 && errorCode(e) === "budget_exceeded") {
            setFailure("budget");
          } else if (status === 502) {
            setFailure("failed");
          } else {
            setFailure("other");
            setMessage(errorText(e));
          }
        },
      },
    );
  };

  const rows = proposal
    ? proposal.blueprint.sections.flatMap((section) =>
        section.rows.map((row) => ({ section: section.title, row })),
      )
    : [];

  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <label className="flex flex-col gap-1 text-sm font-medium">
          {t("exams.ai.promptLabel")}
          <textarea
            dir="auto"
            rows={4}
            maxLength={4000}
            className="border-input bg-background rounded-md border p-2 text-sm font-normal"
            placeholder={t("exams.ai.promptPlaceholder")}
            value={prompt}
            onChange={(event) => {
              setPrompt(event.target.value);
            }}
          />
        </label>
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-muted-foreground text-xs">
            {t("exams.ai.examples")}
          </span>
          {EXAMPLES.map((key) => (
            <Button
              key={key}
              type="button"
              size="sm"
              variant="outline"
              onClick={() => {
                setPrompt(t(`exams.ai.example_${key}`));
              }}
            >
              {t(`exams.ai.example_${key}`)}
            </Button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-sm">
            {t("exams.ai.language")}
            <select
              className="border-input bg-background h-9 rounded-md border px-2"
              value={language}
              onChange={(event) => {
                setLanguage(event.target.value === "en" ? "en" : "ar");
              }}
            >
              <option value="ar">{t("exams.settings.langAr")}</option>
              <option value="en">{t("exams.settings.langEn")}</option>
            </select>
          </label>
          <Button type="submit" disabled={compose.isPending || !prompt.trim()}>
            {compose.isPending ? (
              <Loader2 className="animate-spin" aria-hidden="true" />
            ) : (
              <Sparkles aria-hidden="true" />
            )}
            {t("exams.ai.compose")}
          </Button>
        </div>
      </form>

      <div role="status" aria-live="polite">
        {compose.isPending ? (
          <p className="text-muted-foreground text-sm">
            {t("exams.ai.loading")}
          </p>
        ) : null}
        {done ? (
          <p className="text-sm text-emerald-700 dark:text-emerald-300">
            {done}
          </p>
        ) : null}
      </div>
      <div role="alert">
        {failure === "budget" ? (
          <p className="border-destructive/40 bg-destructive/10 rounded-md border p-3 text-sm">
            {t("exams.ai.budgetExceeded")}
          </p>
        ) : null}
        {failure === "failed" ? (
          <div className="border-destructive/40 bg-destructive/10 flex flex-wrap items-center gap-2 rounded-md border p-3 text-sm">
            <span>{t("exams.ai.composeFailed")}</span>
            <Button type="button" size="sm" onClick={submit}>
              {t("exams.ai.retry")}
            </Button>
          </div>
        ) : null}
        {failure === "other" ? (
          <p className="text-destructive text-sm">{message}</p>
        ) : null}
      </div>

      {proposal ? (
        <section
          aria-label={t("exams.ai.proposal")}
          className="flex flex-col gap-3 rounded-lg border p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{t("exams.ai.proposal")}</h3>
            <Badge variant="outline">
              {t("exams.ai.cost", { cost: formatCostUsd(proposal.cost_usd) })}
            </Badge>
          </div>
          {proposal.rationale ? (
            <p dir="auto" className="text-sm">
              <strong>{t("exams.ai.rationale")}: </strong>
              {proposal.rationale}
            </p>
          ) : null}
          {proposal.warnings.length > 0 ? (
            <ul
              className="list-disc rounded-md border border-amber-500/40 bg-amber-500/10 p-3 ps-8 text-sm"
              aria-label={t("exams.ai.warnings")}
            >
              {proposal.warnings.map((w) => (
                <li key={w} dir="auto">
                  {w}
                </li>
              ))}
            </ul>
          ) : null}
          {proposal.blueprint.notes ? (
            <p dir="auto" className="text-muted-foreground text-sm">
              {proposal.blueprint.notes}
            </p>
          ) : null}
          {rows.map(({ section, row }, index) => {
            const selection = (proposal.selection[index] ?? []).filter(
              (id) => !removed.has(id),
            );
            return (
              <div
                key={`${section}-${String(index)}`}
                className="flex flex-col gap-2"
              >
                <h4 className="text-sm font-semibold">
                  {section} — {t("exams.blueprint.row", { n: index + 1 })}
                </h4>
                <p className="text-muted-foreground text-xs">
                  {t("exams.ai.rowPlan", {
                    count: row.count,
                    points: row.points,
                    types: (row.types ?? [])
                      .map((type) => t(`review.types.${type}`))
                      .join(", "),
                  })}
                </p>
                <QuestionList
                  ids={selection}
                  questions={questions}
                  onRemove={(id) => {
                    setRemoved((current) => new Set(current).add(id));
                  }}
                />
              </div>
            );
          })}
          <div className="flex gap-2">
            <Button
              type="button"
              disabled={mutations.applyProposal.isPending}
              onClick={() => {
                mutations.applyProposal.mutate(
                  {
                    id: proposal.proposal_id,
                    edits: { remove_question_ids: [...removed] },
                  },
                  {
                    onSuccess: () => {
                      setProposal(null);
                      setDone(t("exams.ai.applied"));
                    },
                    onError: (e) => {
                      setFailure("other");
                      setMessage(errorText(e));
                    },
                  },
                );
              }}
            >
              {t("exams.ai.apply")}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={mutations.discardProposal.isPending}
              onClick={() => {
                mutations.discardProposal.mutate(proposal.proposal_id, {
                  onSuccess: () => {
                    setProposal(null);
                    setDone(t("exams.ai.discarded"));
                  },
                  onError: (e) => {
                    setFailure("other");
                    setMessage(errorText(e));
                  },
                });
              }}
            >
              {t("exams.ai.discard")}
            </Button>
          </div>
        </section>
      ) : null}

      <section
        aria-label={t("exams.ai.history")}
        className="flex flex-col gap-2"
      >
        <h3 className="text-sm font-semibold">{t("exams.ai.history")}</h3>
        {proposals.data && proposals.data.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {proposals.data.map((p) => (
              <li
                key={p.proposal_id}
                className="flex flex-wrap items-center gap-2 rounded-md border p-2 text-sm"
              >
                <Badge
                  variant={
                    p.status === "applied"
                      ? "success"
                      : p.status === "pending"
                        ? "info"
                        : "secondary"
                  }
                >
                  {t(`exams.ai.status_${p.status}`, { defaultValue: p.status })}
                </Badge>
                <span dir="auto" className="min-w-0 flex-1 truncate">
                  {p.rationale
                    ? p.rationale
                    : (p.blueprint.title ?? p.proposal_id)}
                </span>
                <span className="text-muted-foreground text-xs">
                  {formatCostUsd(p.cost_usd)}
                </span>
                {p.status === "pending" ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setProposal(p);
                      setRemoved(new Set());
                      setDone("");
                    }}
                  >
                    {t("exams.ai.open")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">
            {t("exams.ai.noHistory")}
          </p>
        )}
      </section>
    </div>
  );
}
