import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useExamMutations,
  useTemplates,
  type ExamDetail,
  type ExamHeader,
  type ExamLayout,
  type ExamSettings,
} from "@/api/hooks/exams";
import { Input } from "@/components/ui/input";
import { useErrorText } from "./use-error-text";

export const SETTINGS_DEBOUNCE_MS = 500;

const SELECT = "border-input bg-background h-9 rounded-md border px-2 text-sm";

const EMPTY_HEADER: ExamHeader = {
  school_name: "",
  exam_title: "",
  subject_label: "",
  grade: "",
  date: "",
  duration_minutes: null,
  instructions: "",
};
const DEFAULT_LAYOUT: ExamLayout = {
  columns: 1,
  font_size_pt: 12,
  digits: "arabic",
  answer_space_lines: 4,
  choices_per_row: "auto",
};

export function SettingsTab({
  exam,
  mutations,
}: {
  exam: ExamDetail;
  mutations: ReturnType<typeof useExamMutations>;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const templates = useTemplates();
  const [draft, setDraft] = useState<ExamSettings>(exam.settings);
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const pending = useRef<ExamSettings | null>(null);

  const flush = () => {
    clearTimeout(timer.current);
    const settings = pending.current;
    if (!settings) return;
    pending.current = null;
    setStatus("saving");
    mutations.saveSettings.mutate(settings, {
      onSuccess: () => {
        setStatus("saved");
        setError("");
      },
      onError: (e) => {
        setStatus("error");
        setError(errorText(e));
      },
    });
  };
  const flushRef = useRef(flush);
  flushRef.current = flush;
  useEffect(
    () => () => {
      flushRef.current();
    },
    [],
  );

  const change = (next: ExamSettings) => {
    setDraft(next);
    pending.current = next;
    setStatus("idle");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      flushRef.current();
    }, SETTINGS_DEBOUNCE_MS);
  };

  const header = draft.header ?? EMPTY_HEADER;
  const layout = draft.layout ?? DEFAULT_LAYOUT;
  const setHeader = (patch: Partial<ExamHeader>) => {
    change({ ...draft, header: { ...header, ...patch } });
  };
  const setLayout = (patch: Partial<ExamLayout>) => {
    change({ ...draft, layout: { ...layout, ...patch } });
  };

  const textField = (
    field: Exclude<keyof ExamHeader, "duration_minutes" | "instructions">,
    label: string,
  ) => (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <Input
        dir="auto"
        value={header[field]}
        onChange={(event) => {
          setHeader({ [field]: event.target.value });
        }}
      />
    </label>
  );

  return (
    <div className="flex flex-col gap-5">
      <div role="status" aria-live="polite" className="min-h-5 text-xs">
        {status === "saving" ? t("exams.settings.saving") : null}
        {status === "saved" ? t("exams.settings.saved") : null}
      </div>
      <div role="alert">
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
      </div>

      <fieldset className="flex flex-col gap-3 rounded-lg border p-3">
        <legend className="px-1 text-sm font-semibold">
          {t("exams.settings.header")}
        </legend>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.template")}
          <select
            className={SELECT}
            value={draft.template_id ?? ""}
            onChange={(event) => {
              const chosen = templates.data?.items.find(
                (tpl) => tpl.id === event.target.value,
              );
              change(
                chosen
                  ? { ...draft, template_id: chosen.id, header: chosen.header }
                  : { ...draft, template_id: null },
              );
            }}
          >
            <option value="">{t("exams.settings.noTemplate")}</option>
            {templates.data?.items.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {tpl.name}
              </option>
            ))}
          </select>
        </label>
        {textField("school_name", t("exams.settings.schoolName"))}
        {textField("exam_title", t("exams.settings.examTitle"))}
        {textField("subject_label", t("exams.settings.subjectLabel"))}
        {textField("grade", t("exams.settings.grade"))}
        {textField("date", t("exams.settings.date"))}
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.duration")}
          <Input
            type="number"
            min="1"
            max="1000"
            value={header.duration_minutes ?? ""}
            onChange={(event) => {
              setHeader({
                duration_minutes: event.target.value
                  ? Number(event.target.value)
                  : null,
              });
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.instructions")}
          <textarea
            dir="auto"
            rows={3}
            className="border-input bg-background rounded-md border p-2 text-sm"
            value={header.instructions}
            onChange={(event) => {
              setHeader({ instructions: event.target.value });
            }}
          />
        </label>
      </fieldset>

      <fieldset className="grid grid-cols-2 gap-3 rounded-lg border p-3">
        <legend className="px-1 text-sm font-semibold">
          {t("exams.settings.layout")}
        </legend>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.columns")}
          <select
            className={SELECT}
            value={layout.columns}
            onChange={(event) => {
              setLayout({ columns: event.target.value === "2" ? 2 : 1 });
            }}
          >
            <option value="1">1</option>
            <option value="2">2</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.fontSize")}
          <Input
            type="number"
            min="10"
            max="16"
            value={layout.font_size_pt}
            onChange={(event) => {
              setLayout({ font_size_pt: Number(event.target.value) });
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.digits")}
          <select
            className={SELECT}
            value={layout.digits}
            onChange={(event) => {
              setLayout({
                digits: event.target.value === "western" ? "western" : "arabic",
              });
            }}
          >
            <option value="arabic">{t("exams.settings.digitsArabic")}</option>
            <option value="western">{t("exams.settings.digitsWestern")}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.answerLines")}
          <Input
            type="number"
            min="0"
            max="20"
            value={layout.answer_space_lines}
            onChange={(event) => {
              setLayout({ answer_space_lines: Number(event.target.value) });
            }}
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.choicesPerRow")}
          <select
            className={SELECT}
            value={String(layout.choices_per_row)}
            onChange={(event) => {
              const v = event.target.value;
              setLayout({
                choices_per_row:
                  v === "1" ? 1 : v === "2" ? 2 : v === "4" ? 4 : "auto",
              });
            }}
          >
            <option value="auto">{t("exams.settings.auto")}</option>
            <option value="1">1</option>
            <option value="2">2</option>
            <option value="4">4</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("exams.settings.language")}
          <select
            className={SELECT}
            value={draft.language}
            onChange={(event) => {
              change({
                ...draft,
                language: event.target.value === "en" ? "en" : "ar",
              });
            }}
          >
            <option value="ar">{t("exams.settings.langAr")}</option>
            <option value="en">{t("exams.settings.langEn")}</option>
          </select>
        </label>
      </fieldset>
    </div>
  );
}
