import {
  CheckCircle2,
  Check,
  ImagePlus,
  Merge,
  RotateCcw,
  Save,
  Scissors,
  Trash2,
  Undo2,
  Wand2,
  X,
} from "lucide-react";
import { type RefObject, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type IssueOut,
  type QuestionOut,
  type StimulusOut,
  useQuestionHistory,
} from "@/api/hooks/review";
import { QmdEditor } from "@/components/qmd/QmdEditor";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatRelativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ChoicesEditor } from "./choices-editor";
import { SeverityIcon } from "./dialogs";
import {
  assetIdsOf,
  type Draft,
  QUESTION_TYPES,
  isQuestionType,
  suggestedFix,
} from "./review-model";
import { StatusChip } from "./status-chip";

export interface EditorPaneProps {
  question: QuestionOut;
  draft: Draft;
  onDraftChange: (draft: Draft) => void;
  dirty: boolean;
  busy: boolean;
  stemRef: RefObject<HTMLTextAreaElement | null>;
  resolveAsset: (id: string) => string | undefined;
  stimulus: StimulusOut | undefined;
  tagSuggestions: readonly string[];
  hasNextQuestion: boolean;
  onSave: () => void;
  onAutosave: () => void;
  onApprove: () => void;
  onReject: () => void;
  onReopen: () => void;
  onResolveIssue: (issue: IssueOut, resolved: boolean) => void;
  onApplyFix: (issue: IssueOut) => void;
  onSplitStem: () => void;
  onSplitChoice: (index: number) => void;
  onMerge: () => void;
  onAddFigure: () => void;
  onRemoveFigure: (assetId: string) => void;
  onEditStimulus: () => void;
}

export function EditorPane(props: EditorPaneProps) {
  const { t } = useTranslation();
  const { question, draft, onDraftChange } = props;
  const [tab, setTab] = useState<"edit" | "history">("edit");
  const lang = question.language;
  const set = (patch: Partial<Draft>) => {
    onDraftChange({ ...draft, ...patch });
  };
  const assetIds = assetIdsOf(question);
  const open =
    question.status === "draft" || question.status === "needs_review";

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-border flex flex-wrap items-center gap-2 border-b p-2">
        <h2 className="text-sm font-semibold" data-testid="editor-title">
          {question.number_label || t("review.queue.noLabel")}
        </h2>
        <StatusChip status={question.status} />
        <span className="text-muted-foreground text-xs">
          {t("review.editor.version", { version: question.version })}
        </span>
        {props.dirty ? (
          <Badge variant="info" data-testid="dirty-badge">
            {t("review.editor.unsaved")}
          </Badge>
        ) : null}
        <span className="ms-auto flex flex-wrap items-center gap-1">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!props.dirty || props.busy}
            onClick={props.onSave}
          >
            <Save aria-hidden="true" />
            {t("review.editor.save")}
          </Button>
          {open ? (
            <>
              <Button
                type="button"
                size="sm"
                disabled={props.busy}
                onClick={props.onApprove}
                data-testid="approve-button"
              >
                <Check aria-hidden="true" />
                {t("review.actions.approve")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={props.busy}
                onClick={props.onReject}
                data-testid="reject-button"
              >
                <X aria-hidden="true" />
                {t("review.actions.reject")}
              </Button>
            </>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={props.busy}
              onClick={props.onReopen}
            >
              <Undo2 aria-hidden="true" />
              {t("review.actions.reopen")}
            </Button>
          )}
        </span>
      </div>

      <div
        role="tablist"
        aria-label={t("review.editor.tabs")}
        className="border-border flex border-b"
      >
        {(["edit", "history"] as const).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`editor-tab-${id}`}
            aria-selected={tab === id}
            aria-controls={`editor-panel-${id}`}
            className={cn(
              "px-3 py-2 text-sm font-medium",
              tab === id
                ? "border-primary border-b-2"
                : "text-muted-foreground",
            )}
            onClick={() => {
              setTab(id);
            }}
          >
            {t(`review.editor.tab.${id}`)}
          </button>
        ))}
      </div>

      {tab === "history" ? (
        <div
          role="tabpanel"
          id="editor-panel-history"
          aria-labelledby="editor-tab-history"
          className="min-h-0 flex-1 overflow-auto p-2"
        >
          <HistoryPanel questionId={question.id} />
        </div>
      ) : (
        <div
          role="tabpanel"
          id="editor-panel-edit"
          aria-labelledby="editor-tab-edit"
          className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-2"
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) {
              props.onAutosave();
            }
          }}
        >
          <IssuesPanel
            issues={question.issues}
            onResolve={props.onResolveIssue}
            onApplyFix={props.onApplyFix}
          />

          {props.stimulus ? (
            <section
              aria-label={t("review.editor.stimulus")}
              className="border-border flex flex-col gap-2 rounded-md border p-2"
              data-testid="stimulus-panel"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="text-xs font-semibold">
                  {t("review.editor.stimulus")} · {props.stimulus.kind}
                </h3>
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  onClick={props.onEditStimulus}
                >
                  {t("review.editor.editStimulus")}
                </Button>
              </div>
              <QmdRenderer
                source={props.stimulus.content}
                lang={lang}
                resolveAsset={props.resolveAsset}
                className="max-h-40 overflow-auto text-sm"
              />
            </section>
          ) : null}

          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="editor-number">
                {t("review.fields.number_label")}
              </Label>
              <Input
                id="editor-number"
                value={draft.number_label}
                onChange={(event) => {
                  set({ number_label: event.target.value });
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="editor-type">{t("review.fields.type")}</Label>
              <select
                id="editor-type"
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={draft.type}
                onChange={(event) => {
                  if (isQuestionType(event.target.value)) {
                    set({ type: event.target.value });
                  }
                }}
              >
                {QUESTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {t(`review.types.${type}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <QmdEditor
              ref={props.stemRef}
              id="editor-stem"
              label={t("review.fields.stem")}
              value={draft.stem}
              lang={lang}
              resolveAsset={props.resolveAsset}
              rows={6}
              onChange={(stem) => {
                set({ stem });
              }}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={props.busy}
                onClick={props.onSplitStem}
              >
                <Scissors aria-hidden="true" />
                {t("review.editor.splitAtCursor")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={props.busy || !props.hasNextQuestion}
                onClick={props.onMerge}
              >
                <Merge aria-hidden="true" />
                {t("review.editor.mergeNext")}
              </Button>
            </div>
          </div>

          <section
            aria-label={t("review.fields.choices")}
            className="flex flex-col gap-2"
          >
            <h3 className="text-sm font-medium">
              {t("review.fields.choices")}
            </h3>
            <ChoicesEditor
              choices={draft.choices}
              lang={lang}
              resolveAsset={props.resolveAsset}
              onChange={(choices) => {
                set({ choices });
              }}
              onSplitAt={props.onSplitChoice}
            />
          </section>

          <div className="flex flex-col gap-1">
            <Label htmlFor="editor-answer">{t("review.fields.answer")}</Label>
            <Input
              id="editor-answer"
              dir="auto"
              value={draft.answer}
              onChange={(event) => {
                set({ answer: event.target.value });
              }}
            />
          </div>

          <QmdEditor
            id="editor-explanation"
            label={t("review.fields.explanation")}
            value={draft.explanation}
            lang={lang}
            resolveAsset={props.resolveAsset}
            rows={4}
            onChange={(explanation) => {
              set({ explanation });
            }}
          />

          <div className="flex flex-col gap-1">
            <Label htmlFor="editor-difficulty">
              {t("review.fields.difficulty")}
            </Label>
            <select
              id="editor-difficulty"
              className="border-input bg-background h-9 w-32 rounded-md border px-2 text-sm"
              value={draft.difficulty === null ? "" : String(draft.difficulty)}
              onChange={(event) => {
                set({
                  difficulty:
                    event.target.value === ""
                      ? null
                      : Number(event.target.value),
                });
              }}
            >
              <option value="">{t("review.editor.noDifficulty")}</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
            {question.difficulty_source || question.difficulty_reason ? (
              <p
                className="text-muted-foreground text-xs"
                data-testid="difficulty-reason"
              >
                {question.difficulty_source
                  ? t("review.editor.difficultySource", {
                      source: question.difficulty_source,
                    })
                  : null}
                {question.difficulty_reason
                  ? ` — ${question.difficulty_reason}`
                  : null}
              </p>
            ) : null}
          </div>

          <TagsField
            tags={draft.tags}
            suggestions={props.tagSuggestions}
            onChange={(tags) => {
              set({ tags });
            }}
          />

          <section
            aria-label={t("review.editor.figures")}
            className="flex flex-col gap-2"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium">
                {t("review.editor.figures")}
              </h3>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={props.busy}
                onClick={props.onAddFigure}
              >
                <ImagePlus aria-hidden="true" />
                {t("review.editor.addFigure")}
              </Button>
            </div>
            {assetIds.length === 0 ? (
              <p className="text-muted-foreground text-xs">
                {t("review.editor.noFigures")}
              </p>
            ) : (
              <ul className="flex flex-wrap gap-2">
                {assetIds.map((assetId) => (
                  <li
                    key={assetId}
                    className="border-border flex flex-col items-center gap-1 rounded-md border p-1"
                  >
                    <img
                      src={props.resolveAsset(assetId)}
                      alt={t("review.editor.figureAlt")}
                      data-testid={`figure-thumb-${assetId}`}
                      className="h-16 max-w-28 object-contain"
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        props.onRemoveFigure(assetId);
                      }}
                    >
                      <Trash2 aria-hidden="true" />
                      {t("review.editor.removeFigure")}
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function TagsField({
  tags,
  suggestions,
  onChange,
}: {
  tags: readonly string[];
  suggestions: readonly string[];
  onChange: (tags: string[]) => void;
}) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const commit = () => {
    const value = input.trim();
    if (value && !tags.includes(value)) onChange([...tags, value]);
    setInput("");
  };
  return (
    <div className="flex flex-col gap-1">
      <Label htmlFor="editor-tags">{t("review.fields.tags")}</Label>
      <div className="flex flex-wrap gap-1">
        {tags.map((tag) => (
          <Badge key={tag} variant="secondary" className="gap-1">
            {tag}
            <button
              type="button"
              aria-label={t("review.editor.removeTag", { tag })}
              onClick={() => {
                onChange(tags.filter((x) => x !== tag));
              }}
            >
              <X className="size-3" aria-hidden="true" />
            </button>
          </Badge>
        ))}
      </div>
      <Input
        id="editor-tags"
        list="editor-tag-suggestions"
        value={input}
        placeholder={t("review.editor.tagPlaceholder")}
        onChange={(event) => {
          setInput(event.target.value);
        }}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === ",") {
            event.preventDefault();
            commit();
          }
        }}
      />
      <datalist id="editor-tag-suggestions">
        {suggestions.map((tag) => (
          <option key={tag} value={tag} />
        ))}
      </datalist>
    </div>
  );
}

function IssuesPanel({
  issues,
  onResolve,
  onApplyFix,
}: {
  issues: readonly IssueOut[];
  onResolve: (issue: IssueOut, resolved: boolean) => void;
  onApplyFix: (issue: IssueOut) => void;
}) {
  const { t } = useTranslation();
  return (
    <section
      aria-label={t("review.issues.title")}
      className="border-border flex flex-col gap-2 rounded-md border p-2"
      data-testid="issues-panel"
    >
      <h3 className="text-sm font-medium">{t("review.issues.title")}</h3>
      {issues.length === 0 ? (
        <p className="text-muted-foreground flex items-center gap-1 text-xs">
          <CheckCircle2 className="size-4" aria-hidden="true" />
          {t("review.issues.none")}
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {issues.map((issue) => {
            const resolved = issue.resolved_at !== null;
            const fix = suggestedFix(issue);
            return (
              <li
                key={issue.id}
                data-testid={`issue-${issue.id}`}
                className={cn(
                  "flex flex-col gap-1 text-sm",
                  resolved && "text-muted-foreground line-through",
                )}
              >
                <div className="flex items-start gap-2">
                  <SeverityIcon severity={issue.severity} />
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">
                      {t(`review.severity.${issue.severity}`)}:{" "}
                    </span>
                    {issue.message}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1 ps-6">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      onResolve(issue, !resolved);
                    }}
                  >
                    {resolved ? (
                      <RotateCcw aria-hidden="true" />
                    ) : (
                      <Check aria-hidden="true" />
                    )}
                    {resolved
                      ? t("review.issues.unresolve")
                      : t("review.issues.resolve")}
                  </Button>
                  {fix && !resolved ? (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      title={fix.value}
                      onClick={() => {
                        onApplyFix(issue);
                      }}
                    >
                      <Wand2 aria-hidden="true" />
                      {t("review.issues.applyFix", {
                        field: t(`review.fields.${fix.field}`),
                      })}
                    </Button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function summarize(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "—";
  return JSON.stringify(value);
}

function HistoryPanel({ questionId }: { questionId: string }) {
  const { t, i18n } = useTranslation();
  const history = useQuestionHistory(questionId, true);
  if (history.isLoading) {
    return (
      <p className="text-muted-foreground text-sm">
        {t("review.common.loading")}
      </p>
    );
  }
  if (history.isError) {
    return (
      <p role="alert" className="text-destructive text-sm">
        {t("review.history.error")}
      </p>
    );
  }
  const events = history.data ?? [];
  if (events.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        {t("review.history.empty")}
      </p>
    );
  }
  return (
    <ol className="flex flex-col gap-3" data-testid="history-list">
      {events.map((event) => (
        <li
          key={event.id}
          className="border-border rounded-md border p-2 text-sm"
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium">{event.action}</span>
            <time
              className="text-muted-foreground text-xs"
              dateTime={event.created_at}
            >
              {formatRelativeTime(event.created_at, i18n.language)}
            </time>
          </div>
          <ul className="text-muted-foreground mt-1 text-xs">
            {Object.entries(event.diff).map(([field, change]) => {
              const record =
                typeof change === "object" && change !== null
                  ? (change as Record<string, unknown>)
                  : {};
              return (
                <li key={field} className="truncate">
                  <span className="font-medium">{field}</span>:{" "}
                  {summarize(record.before)} → {summarize(record.after)}
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}
