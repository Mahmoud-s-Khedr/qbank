import { useTranslation } from "react-i18next";
import { useAnswerKey, type ExamDetail } from "@/api/hooks/exams";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { choiceParts, formatDigits, printSections } from "./exam-model";
import { groupUnits } from "./exam-model";

/** Read-only approximation of the printed exam, in print order (version A order if versions exist). */
export function ExamPreview({ exam }: { exam: ExamDetail }) {
  const { t } = useTranslation();
  const firstVersion = exam.versions[0]?.label;
  const key = useAnswerKey(exam.id, firstVersion);
  const order = key.data?.items.map((entry) => entry.question_id);
  const sections = printSections(exam, order);
  const settings = exam.settings;
  const header = settings.header;
  const digits = settings.layout?.digits ?? "arabic";
  const lang = settings.language;
  const columns = settings.layout?.columns ?? 1;
  const perRow = settings.layout?.choices_per_row ?? "auto";
  const examTitle = header?.exam_title.trim() ? header.exam_title : exam.title;
  const numbers = new Map<string, number>();
  for (const section of sections) {
    for (const item of section.items) numbers.set(item.id, numbers.size + 1);
  }

  return (
    <article
      dir={lang === "ar" ? "rtl" : "ltr"}
      lang={lang}
      aria-label={t("exams.preview.label")}
      data-testid="exam-preview"
      className="bg-card font-content mx-auto flex max-w-3xl flex-col gap-4 rounded-lg border p-6"
      style={{ fontSize: `${String(settings.layout?.font_size_pt ?? 12)}pt` }}
    >
      {firstVersion ? (
        <p className="text-muted-foreground text-xs">
          {t("exams.preview.versionOrder", { label: firstVersion })}
        </p>
      ) : null}
      <header className="flex flex-col items-center gap-1 text-center">
        {header?.school_name ? (
          <p className="font-bold">{header.school_name}</p>
        ) : null}
        <h2 className="text-lg font-bold">{examTitle}</h2>
        <p className="text-sm">
          {[header?.subject_label, header?.grade, header?.date]
            .filter(Boolean)
            .join(" — ")}
        </p>
        {header?.duration_minutes ? (
          <p className="text-sm">
            {t("exams.preview.duration", {
              minutes: formatDigits(header.duration_minutes, digits),
            })}
          </p>
        ) : null}
        {header?.instructions ? (
          <p className="text-sm italic">{header.instructions}</p>
        ) : null}
      </header>

      {sections.map((section) => (
        <section key={section.id} className="flex flex-col gap-3">
          <h3 className="border-b pb-1 font-semibold">{section.title}</h3>
          {section.instructions ? (
            <p className="text-sm italic">{section.instructions}</p>
          ) : null}
          <ol
            className="gap-3"
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${String(columns)}, minmax(0, 1fr))`,
            }}
          >
            {groupUnits(section.items).map((unit) => (
              <li
                key={unit.items[0]?.id}
                className={`flex flex-col gap-2 ${unit.items.length > 1 ? "col-span-full" : ""}`}
              >
                {unit.stimulusId !== null && unit.items[0]?.stimulus ? (
                  <div className="rounded border p-2 text-sm">
                    <QmdRenderer source={unit.items[0].stimulus.content} />
                  </div>
                ) : null}
                {unit.items.map((item) => {
                  const choices = item.question.choices.map(choiceParts);
                  return (
                    <div key={item.id} className="flex gap-2">
                      <span className="font-semibold tabular-nums">
                        {formatDigits(numbers.get(item.id) ?? 0, digits)}.
                      </span>
                      <div className="min-w-0 flex-1">
                        <QmdRenderer source={item.question.stem} />
                        {choices.length > 0 ? (
                          <ul
                            className="mt-1 gap-1 text-sm"
                            style={{
                              display: "grid",
                              gridTemplateColumns: `repeat(${String(
                                perRow === "auto"
                                  ? choices.length > 4
                                    ? 1
                                    : 2
                                  : perRow,
                              )}, minmax(0, 1fr))`,
                            }}
                          >
                            {choices.map((choice) => (
                              <li key={choice.label} className="flex gap-1">
                                <span>{choice.label}</span>
                                <QmdRenderer source={choice.content} inline />
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                      <span className="text-muted-foreground text-xs">
                        ({formatDigits(item.points, digits)})
                      </span>
                    </div>
                  );
                })}
              </li>
            ))}
          </ol>
        </section>
      ))}
    </article>
  );
}
