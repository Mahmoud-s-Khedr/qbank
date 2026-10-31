import { Plus, RefreshCw, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useBankStats,
  useBlueprintPreview,
  useExamMutations,
  useSubjectTree,
  type Blueprint,
  type BlueprintResult,
  type BlueprintRow,
  type ExamDetail,
} from "@/api/hooks/exams";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/features/review/dialogs";
import { QUESTION_TYPES } from "./bank-tab";
import { QuestionList } from "./question-list";
import { useQuestionsById } from "./use-questions";
import { useErrorText } from "./use-error-text";

interface RowDraft {
  key: number;
  chapterIds: string[];
  lessonIds: string[];
  types: string[];
  difficultyMin: string;
  difficultyMax: string;
  count: string;
  points: string;
  sectionId: string;
}

let nextKey = 1;
function newRow(sectionId: string): RowDraft {
  return {
    key: nextKey++,
    chapterIds: [],
    lessonIds: [],
    types: [],
    difficultyMin: "",
    difficultyMax: "",
    count: "5",
    points: "1",
    sectionId,
  };
}

function toRow(draft: RowDraft): BlueprintRow {
  return {
    chapter_ids: draft.chapterIds,
    lesson_ids: draft.lessonIds,
    types: draft.types,
    difficulty_min: draft.difficultyMin ? Number(draft.difficultyMin) : null,
    difficulty_max: draft.difficultyMax ? Number(draft.difficultyMax) : null,
    count: Math.max(1, Math.floor(Number(draft.count) || 1)),
    points: Math.max(0, Number(draft.points) || 0),
    section_id: draft.sectionId || null,
  };
}

const FIELD = "border-input bg-background rounded-md border px-2 text-sm";

function selected(select: HTMLSelectElement): string[] {
  return Array.from(select.selectedOptions, (o) => o.value);
}

export function BlueprintTab({
  exam,
  targetSectionId,
  mutations,
}: {
  exam: ExamDetail;
  targetSectionId: string;
  mutations: ReturnType<typeof useExamMutations>;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const tree = useSubjectTree(exam.subject_id);
  const stats = useBankStats(exam.subject_id);
  const preview = useBlueprintPreview(exam.id);
  const [rows, setRows] = useState<RowDraft[]>(() => [newRow(targetSectionId)]);
  const [seed, setSeed] = useState<number | null>(null);
  const [result, setResult] = useState<BlueprintResult | null>(null);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [applied, setApplied] = useState(false);

  const chapters = tree.data?.chapters ?? [];
  const questions = useQuestionsById(
    result?.rows.flatMap((r) => r.selected) ?? [],
  );

  const update = (key: number, patch: Partial<RowDraft>) => {
    setRows((current) =>
      current.map((r) => (r.key === key ? { ...r, ...patch } : r)),
    );
    setResult(null);
    setApplied(false);
  };

  const blueprint = (useSeed: number | null): Blueprint => ({
    rows: rows.map(toRow),
    exclude_used_in_my_exams: false,
    seed: useSeed,
  });

  const available = (row: RowDraft): number | null => {
    const data = stats.data;
    if (!data) return null;
    const sum = (
      list: readonly { id: string; count: number }[],
      ids: string[],
    ) =>
      list.filter((x) => ids.includes(x.id)).reduce((n, x) => n + x.count, 0);
    if (row.lessonIds.length)
      return sum(data.approved_by_lesson, row.lessonIds);
    if (row.chapterIds.length)
      return sum(data.approved_by_chapter, row.chapterIds);
    return data.by_status.approved ?? 0;
  };

  const run = (useSeed: number | null) => {
    setError("");
    setApplied(false);
    preview.mutate(blueprint(useSeed), {
      onSuccess: (data) => {
        setResult(data);
        setSeed(data.seed);
      },
      onError: (e) => {
        setError(errorText(e));
      },
    });
  };

  const sectionTitle = (id: string) =>
    exam.sections.find((s) => s.id === id)?.title ?? "";

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">
        {t("exams.blueprint.intro")}
      </p>
      {rows.map((row, index) => {
        const lessons = chapters
          .filter(
            (c) => !row.chapterIds.length || row.chapterIds.includes(c.id),
          )
          .flatMap((c) => c.lessons);
        const avail = available(row);
        const rowResult = result?.rows[index];
        const n = index + 1;
        return (
          <fieldset
            key={row.key}
            className="flex flex-col gap-2 rounded-lg border p-3"
          >
            <legend className="px-1 text-sm font-semibold">
              {t("exams.blueprint.row", { n })}
            </legend>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex flex-col gap-1 text-xs">
                {t("exams.bank.chapter")}
                <select
                  multiple
                  className={`${FIELD} h-20`}
                  value={row.chapterIds}
                  onChange={(event) => {
                    update(row.key, {
                      chapterIds: selected(event.target),
                      lessonIds: [],
                    });
                  }}
                >
                  {chapters.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                {t("exams.bank.lesson")}
                <select
                  multiple
                  className={`${FIELD} h-20`}
                  value={row.lessonIds}
                  onChange={(event) => {
                    update(row.key, { lessonIds: selected(event.target) });
                  }}
                >
                  {lessons.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="col-span-2 flex flex-col gap-1 text-xs">
                {t("exams.bank.type")}
                <select
                  multiple
                  className={`${FIELD} h-24`}
                  value={row.types}
                  onChange={(event) => {
                    update(row.key, { types: selected(event.target) });
                  }}
                >
                  {QUESTION_TYPES.map((value) => (
                    <option key={value} value={value}>
                      {t(`review.types.${value}`)}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 text-xs">
                {t("exams.blueprint.difficultyMin")}
                <Input
                  type="number"
                  min="1"
                  max="5"
                  value={row.difficultyMin}
                  onChange={(event) => {
                    update(row.key, { difficultyMin: event.target.value });
                  }}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                {t("exams.blueprint.difficultyMax")}
                <Input
                  type="number"
                  min="1"
                  max="5"
                  value={row.difficultyMax}
                  onChange={(event) => {
                    update(row.key, { difficultyMax: event.target.value });
                  }}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                {t("exams.blueprint.count")}
                <Input
                  type="number"
                  min="1"
                  max="500"
                  value={row.count}
                  onChange={(event) => {
                    update(row.key, { count: event.target.value });
                  }}
                />
              </label>
              <label className="flex flex-col gap-1 text-xs">
                {t("exams.builder.points")}
                <Input
                  type="number"
                  min="0"
                  step="0.5"
                  value={row.points}
                  onChange={(event) => {
                    update(row.key, { points: event.target.value });
                  }}
                />
              </label>
              <label className="col-span-2 flex flex-col gap-1 text-xs">
                {t("exams.blueprint.section")}
                <select
                  className={`${FIELD} h-9`}
                  value={row.sectionId}
                  onChange={(event) => {
                    update(row.key, { sectionId: event.target.value });
                  }}
                >
                  {exam.sections.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {avail !== null ? (
              <p className="text-muted-foreground text-xs">
                {t("exams.blueprint.availableHint", { count: avail })}
              </p>
            ) : null}
            {rowResult ? (
              <div className="flex flex-col gap-2" aria-live="polite">
                <p
                  className={`text-sm ${rowResult.shortfall > 0 ? "text-destructive" : ""}`}
                >
                  {t("exams.blueprint.rowResult", {
                    selected: rowResult.selected.length,
                    requested: rowResult.requested,
                    shortfall: rowResult.shortfall,
                    available: rowResult.available,
                  })}
                </p>
                <QuestionList ids={rowResult.selected} questions={questions} />
              </div>
            ) : null}
            <div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={rows.length === 1}
                aria-label={t("exams.blueprint.removeRow", { n })}
                onClick={() => {
                  setRows((current) =>
                    current.filter((r) => r.key !== row.key),
                  );
                  setResult(null);
                }}
              >
                <Trash2 aria-hidden="true" />
                {t("exams.builder.remove")}
              </Button>
            </div>
          </fieldset>
        );
      })}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setRows((current) => [...current, newRow(targetSectionId)]);
          }}
        >
          <Plus aria-hidden="true" />
          {t("exams.blueprint.addRow")}
        </Button>
        <Button
          type="button"
          disabled={preview.isPending}
          onClick={() => {
            run(seed);
          }}
        >
          {preview.isPending
            ? t("exams.loading")
            : t("exams.blueprint.preview")}
        </Button>
        <Button
          type="button"
          variant="outline"
          disabled={preview.isPending}
          onClick={() => {
            run(Math.floor(Math.random() * 2_000_000_000));
          }}
        >
          <RefreshCw aria-hidden="true" />
          {t("exams.blueprint.reshuffle")}
        </Button>
        <Button
          type="button"
          variant="default"
          disabled={!result || mutations.applyBlueprint.isPending}
          onClick={() => {
            setConfirm(true);
          }}
        >
          {t("exams.blueprint.apply")}
        </Button>
      </div>
      <div role="alert">
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
      </div>
      <div role="status">
        {applied ? (
          <p className="text-sm text-emerald-700 dark:text-emerald-300">
            {t("exams.blueprint.applied")}
          </p>
        ) : null}
      </div>
      <ConfirmDialog
        open={confirm}
        title={t("exams.blueprint.confirmTitle")}
        description={t("exams.blueprint.confirmDescription", {
          section: sectionTitle(targetSectionId),
        })}
        confirmLabel={t("exams.blueprint.apply")}
        pending={mutations.applyBlueprint.isPending}
        onConfirm={() => {
          mutations.applyBlueprint.mutate(blueprint(seed), {
            onSuccess: () => {
              setApplied(true);
              setResult(null);
            },
            onError: (e) => {
              setError(errorText(e));
            },
            onSettled: () => {
              setConfirm(false);
            },
          });
        }}
        onClose={() => {
          setConfirm(false);
        }}
      />
    </div>
  );
}
