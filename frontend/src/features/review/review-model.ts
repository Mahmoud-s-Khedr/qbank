import type {
  Box,
  Region,
  RegionStatus,
} from "@/components/page-canvas/PageCanvas";
import type {
  IssueOut,
  QuestionOut,
  QuestionPatch,
  QuestionType,
  StimulusOut,
} from "@/api/hooks/review";

export const QUESTION_TYPES: readonly QuestionType[] = [
  "mcq_single",
  "mcq_multi",
  "true_false",
  "fill_blank",
  "short_answer",
  "essay",
  "matching",
  "ordering",
];

/**
 * The backend exposes no models endpoint yet, so this mirrors `llm_allowed_models`
 * (docs/MODELS.md). The empty value means "the source's own model".
 */
export const REEXTRACT_MODELS: readonly string[] = [
  "google/gemini-3.8-flash",
  "qwen/qwen3.8-flash",
  "openai/gpt-6-luna",
  "anthropic/claude-haiku-5.5",
  "nvidia/nemotron-3.5-super-vl:free",
];

export interface ChoiceDraft {
  key: string;
  label: string;
  content: string;
  is_correct: boolean;
  pinned: boolean;
}

export interface Draft {
  number_label: string;
  type: QuestionType;
  stem: string;
  choices: ChoiceDraft[];
  answer: string;
  explanation: string;
  difficulty: number | null;
  tags: string[];
}

let choiceCounter = 0;
export function nextChoiceKey(): string {
  choiceCounter += 1;
  return `choice-${String(choiceCounter)}`;
}

export function isQuestionType(value: string): value is QuestionType {
  return (QUESTION_TYPES as readonly string[]).includes(value);
}

export function parseChoices(
  raw: readonly Record<string, unknown>[],
): ChoiceDraft[] {
  return raw.map((item) => ({
    key: nextChoiceKey(),
    label: typeof item.label === "string" ? item.label : "",
    content: typeof item.content === "string" ? item.content : "",
    is_correct: item.is_correct === true,
    pinned: item.pinned === true,
  }));
}

export function draftFromQuestion(question: QuestionOut): Draft {
  return {
    number_label: question.number_label,
    type: isQuestionType(question.type) ? question.type : "short_answer",
    stem: question.stem,
    choices: parseChoices(question.choices),
    answer: question.answer ?? "",
    explanation: question.explanation ?? "",
    difficulty: question.difficulty,
    tags: question.tags,
  };
}

function choicesSignature(choices: readonly ChoiceDraft[]): string {
  return JSON.stringify(
    choices.map((c) => [c.label, c.content, c.is_correct, c.pinned]),
  );
}

/** The fields that differ from the saved question, or null when nothing changed. */
export function buildPatch(
  question: QuestionOut,
  draft: Draft,
  version: number = question.version,
): QuestionPatch | null {
  const base = draftFromQuestion(question);
  const patch: QuestionPatch = { version };
  let changed = false;
  if (draft.number_label !== base.number_label) {
    patch.number_label = draft.number_label;
    changed = true;
  }
  if (draft.type !== base.type) {
    patch.type = draft.type;
    changed = true;
  }
  if (draft.stem !== base.stem) {
    patch.stem = draft.stem;
    changed = true;
  }
  if (choicesSignature(draft.choices) !== choicesSignature(base.choices)) {
    patch.choices = draft.choices.map((c) => ({
      label: c.label,
      content: c.content,
      is_correct: c.is_correct,
      pinned: c.pinned,
    }));
    changed = true;
  }
  if (draft.answer !== base.answer) {
    patch.answer = draft.answer === "" ? null : draft.answer;
    changed = true;
  }
  if (draft.explanation !== base.explanation) {
    patch.explanation = draft.explanation === "" ? null : draft.explanation;
    changed = true;
  }
  if (draft.difficulty !== base.difficulty) {
    patch.difficulty = draft.difficulty;
    changed = true;
  }
  if (JSON.stringify(draft.tags) !== JSON.stringify(base.tags)) {
    patch.tags = draft.tags;
    changed = true;
  }
  return changed ? patch : null;
}

export const DRAFT_FIELD_KEYS = [
  "number_label",
  "type",
  "stem",
  "choices",
  "answer",
  "explanation",
  "difficulty",
  "tags",
] as const;
export type DraftFieldKey = (typeof DRAFT_FIELD_KEYS)[number];

/** The fields where the user's draft differs from the server's current question. */
export function conflictingFields(
  current: QuestionOut,
  draft: Draft,
): { field: DraftFieldKey; mine: string; theirs: string }[] {
  const theirs = draftFromQuestion(current);
  const show = (d: Draft, key: DraftFieldKey): string => {
    switch (key) {
      case "choices":
        return d.choices.map((c) => `${c.label}) ${c.content}`).join("\n");
      case "tags":
        return d.tags.join(", ");
      case "difficulty":
        return d.difficulty === null ? "" : String(d.difficulty);
      default:
        return d[key];
    }
  };
  return DRAFT_FIELD_KEYS.flatMap((field) => {
    const mine = show(draft, field);
    const other = show(theirs, field);
    const same =
      field === "choices"
        ? choicesSignature(draft.choices) === choicesSignature(theirs.choices)
        : mine === other;
    return same ? [] : [{ field, mine, theirs: other }];
  });
}

export function unresolvedIssues(issues: readonly IssueOut[]): IssueOut[] {
  return issues.filter((issue) => issue.resolved_at === null);
}

export function issueCounts(issues: readonly IssueOut[]): {
  error: number;
  warning: number;
} {
  const open = unresolvedIssues(issues);
  return {
    error: open.filter((i) => i.severity === "error").length,
    warning: open.filter((i) => i.severity === "warning").length,
  };
}

export interface SuggestedFix {
  field: "stem" | "answer" | "type" | "explanation";
  value: string;
}

/** A verifier fix we can apply as a plain field replacement. */
export function suggestedFix(issue: IssueOut): SuggestedFix | null {
  const fix = issue.details.suggested_fix;
  const field = issue.details.field;
  if (
    typeof fix !== "string" ||
    fix.trim() === "" ||
    typeof field !== "string"
  ) {
    return null;
  }
  if (field === "stem" || field === "answer" || field === "explanation") {
    return { field, value: fix };
  }
  if (field === "type" && isQuestionType(fix.trim())) {
    return { field: "type", value: fix.trim() };
  }
  return null;
}

const ASSET_REF = /asset:([0-9a-fA-F-]{36})/g;

/** Asset ids referenced by the question text, in order of first appearance. */
export function assetIdsOf(question: QuestionOut): string[] {
  const text = [
    question.stem,
    question.explanation ?? "",
    ...question.choices.map((c) =>
      typeof c.content === "string" ? c.content : "",
    ),
  ].join("\n");
  return [
    ...new Set([...text.matchAll(ASSET_REF)].map((m) => m[1] ?? "")),
  ].filter(Boolean);
}

export function isBox(value: unknown): value is Box {
  return (
    Array.isArray(value) &&
    value.length === 4 &&
    value.every((n) => typeof n === "number")
  );
}

export interface PlacedRegion {
  page: string;
  box: Box;
}

export function parseRegions(
  raw: readonly Record<string, unknown>[],
): PlacedRegion[] {
  return raw.flatMap((r) =>
    typeof r.page === "string" && isBox(r.box)
      ? [{ page: r.page, box: r.box }]
      : [],
  );
}

/** Page ids a question or stimulus touches, in order. */
export function pageIdsOf(raw: readonly Record<string, unknown>[]): string[] {
  return [...new Set(parseRegions(raw).map((r) => r.page))];
}

export function regionStatus(
  status: string,
  issues: readonly IssueOut[],
): RegionStatus {
  if (status === "approved") return "approved";
  const counts = issueCounts(issues);
  if (counts.error > 0) return "error";
  if (counts.warning > 0) return "warning";
  return "ok";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The extraction stores boxes as [ymin, xmin, ymax, xmax] on a 0-1000 scale. */
export function extractionBox(value: unknown): Box | null {
  if (!isBox(value)) return null;
  const [ymin, xmin, ymax, xmax] = value.map((n) =>
    Math.max(0, Math.min(1000, n)),
  );
  if (
    ymin === undefined ||
    xmin === undefined ||
    ymax === undefined ||
    xmax === undefined
  ) {
    return null;
  }
  return [
    Math.min(xmin, xmax) / 1000,
    Math.min(ymin, ymax) / 1000,
    Math.max(xmin, xmax) / 1000,
    Math.max(ymin, ymax) / 1000,
  ];
}

export interface ExtractionView {
  headings: { text: string; box: Box }[];
  figuresByQuestion: Map<string, Box[]>;
}

export function parseExtraction(
  extraction: Record<string, unknown> | null | undefined,
): ExtractionView {
  const view: ExtractionView = { headings: [], figuresByQuestion: new Map() };
  if (!extraction) return view;
  const headings = extraction.headings;
  if (Array.isArray(headings)) {
    for (const h of headings as unknown[]) {
      if (!isRecord(h)) continue;
      const box = extractionBox(h.box_2d);
      if (box) {
        view.headings.push({
          text: typeof h.text === "string" ? h.text : "",
          box,
        });
      }
    }
  }
  const questions = extraction.questions;
  if (Array.isArray(questions)) {
    for (const q of questions as unknown[]) {
      if (!isRecord(q) || typeof q.number_label !== "string") continue;
      const figures = Array.isArray(q.figures) ? (q.figures as unknown[]) : [];
      const boxes = figures.flatMap((f) => {
        const box = isRecord(f) ? extractionBox(f.box_2d) : null;
        return box ? [box] : [];
      });
      view.figuresByQuestion.set(q.number_label, boxes);
    }
  }
  return view;
}

export function stimulusRegions(
  stimuli: readonly StimulusOut[],
  pageId: string,
): Region[] {
  return stimuli.flatMap((s) =>
    parseRegions(s.regions)
      .filter((r) => r.page === pageId)
      .map((r) => ({
        id: `s:${s.id}`,
        box: r.box,
        kind: "stimulus" as const,
        status: s.status === "approved" ? "approved" : "ok",
        label: s.kind,
      })),
  );
}

/** Item ids in a queue, ordered; picks where to go after the current one leaves. */
export function pickNextId(
  items: readonly { id: string; status: string }[],
  currentId: string,
): string | undefined {
  const index = items.findIndex((i) => i.id === currentId);
  if (index === -1) return items[0]?.id;
  const open = (status: string) =>
    status === "draft" || status === "needs_review";
  const after = items.slice(index + 1);
  return (
    after.find((i) => open(i.status))?.id ??
    after[0]?.id ??
    items
      .slice(0, index)
      .reverse()
      .find((i) => open(i.status))?.id ??
    items[index - 1]?.id
  );
}
