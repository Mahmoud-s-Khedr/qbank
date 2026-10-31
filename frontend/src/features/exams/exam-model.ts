import { ApiError } from "@/api/client";
import type { ExamDetail, ItemOut, SectionOut } from "@/api/hooks/exams";

/** Consecutive items sharing a stimulus form one unit that moves/removes together. */
export interface Unit {
  stimulusId: string | null;
  items: ItemOut[];
}

export function groupUnits(items: readonly ItemOut[]): Unit[] {
  const units: Unit[] = [];
  for (const item of items) {
    const stimulusId = item.question.stimulus_id;
    const last = units.at(-1);
    if (stimulusId !== null && last?.stimulusId === stimulusId) {
      last.items.push(item);
    } else {
      units.push({ stimulusId, items: [item] });
    }
  }
  return units;
}

/** The flat id order after moving one unit by `delta` positions, or null if impossible. */
export function moveUnitOrder(
  items: readonly ItemOut[],
  unitIndex: number,
  delta: -1 | 1,
): string[] | null {
  const units = groupUnits(items);
  const target = unitIndex + delta;
  if (target < 0 || target >= units.length) return null;
  const next = [...units];
  const [moved] = next.splice(unitIndex, 1);
  if (!moved) return null;
  next.splice(target, 0, moved);
  return next.flatMap((u) => u.items.map((i) => i.id));
}

export function moveIdOrder(
  ids: readonly string[],
  index: number,
  delta: -1 | 1,
): string[] | null {
  const target = index + delta;
  if (target < 0 || target >= ids.length) return null;
  const next = [...ids];
  const [moved] = next.splice(index, 1);
  if (moved === undefined) return null;
  next.splice(target, 0, moved);
  return next;
}

const ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩";

export function formatDigits(value: number | string, digits: string): string {
  const text = String(value);
  if (digits !== "arabic") return text;
  return text.replace(/\d/g, (d) => ARABIC_INDIC.charAt(Number(d)));
}

/** Items in print order, optionally re-ordered inside each section by a version's question order. */
export function printSections(
  exam: ExamDetail,
  order?: readonly string[],
): SectionOut[] {
  if (!order?.length) return exam.sections;
  const rank = new Map(order.map((id, index) => [id, index] as const));
  return exam.sections.map((section) => ({
    ...section,
    items: [...section.items].sort(
      (a, b) =>
        (rank.get(a.question_id) ?? Number.MAX_SAFE_INTEGER) -
        (rank.get(b.question_id) ?? Number.MAX_SAFE_INTEGER),
    ),
  }));
}

export function errorCode(error: unknown): string | undefined {
  return error instanceof ApiError ? error.code : undefined;
}

export function errorStatus(error: unknown): number | undefined {
  return error instanceof ApiError ? error.status : undefined;
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function choiceParts(choice: Record<string, unknown>): {
  label: string;
  content: string;
} {
  const label = typeof choice.label === "string" ? choice.label : "";
  const content = typeof choice.content === "string" ? choice.content : "";
  return { label, content };
}

export function formatDate(iso: string, lang: string): string {
  const time = Date.parse(iso);
  if (Number.isNaN(time)) return iso;
  return new Intl.DateTimeFormat(lang.startsWith("ar") ? "ar" : "en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(time);
}
