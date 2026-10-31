import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAnswerKey, type ExamDetail } from "@/api/hooks/exams";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Badge } from "@/components/ui/badge";
import { ExamExportsPanel } from "@/features/exports/exam-exports-panel";
import { formatDigits } from "./exam-model";

export function VersionsTab({ exam }: { exam: ExamDetail }) {
  const { t } = useTranslation();
  const [chosen, setChosen] = useState("");
  const label =
    exam.versions.find((v) => v.label === chosen)?.label ??
    exam.versions[0]?.label;
  const key = useAnswerKey(exam.id, label);
  const stems = new Map(
    exam.sections.flatMap((s) =>
      s.items.map((i) => [i.question_id, i.question.stem] as const),
    ),
  );
  const digits = exam.settings.layout?.digits ?? "arabic";

  return (
    <div className="flex flex-col gap-6">
      {/* T23: ExamExportsPanel (generate versions, request exports, downloads) */}
      <ExamExportsPanel examId={exam.id} />

      {exam.versions.length > 0 ? (
        <section
          aria-label={t("exams.versions.answerKey")}
          className="flex flex-col gap-3"
        >
          <h3 className="font-semibold">{t("exams.versions.answerKey")}</h3>
          <ul className="flex flex-wrap gap-2">
            {exam.versions.map((v) => (
              <li key={v.id} className="flex items-center gap-1 text-sm">
                <span className="font-medium">{v.label}</span>
                {v.stale ? (
                  <Badge variant="warning">{t("exams.versions.stale")}</Badge>
                ) : null}
              </li>
            ))}
          </ul>
          <label className="flex items-center gap-2 text-sm">
            {t("exams.versions.choose")}
            <select
              className="border-input bg-background h-9 rounded-md border px-2"
              value={label}
              onChange={(event) => {
                setChosen(event.target.value);
              }}
            >
              {exam.versions.map((v) => (
                <option key={v.id} value={v.label}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
          <div aria-live="polite">
            {key.isPending ? (
              <p className="text-muted-foreground text-sm">
                {t("exams.loading")}
              </p>
            ) : key.isError ? (
              <p className="text-destructive text-sm">{t("exams.loadError")}</p>
            ) : (
              <>
                {key.data.warnings.length > 0 ? (
                  <ul className="mb-2 list-disc rounded-md border border-amber-500/40 bg-amber-500/10 p-3 ps-8 text-sm">
                    {key.data.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <caption className="sr-only">
                      {t("exams.versions.answerKeyFor", {
                        label: key.data.label,
                      })}
                    </caption>
                    <thead>
                      <tr className="text-start">
                        <th scope="col" className="p-2 text-start">
                          {t("exams.versions.number")}
                        </th>
                        <th scope="col" className="p-2 text-start">
                          {t("exams.versions.question")}
                        </th>
                        <th scope="col" className="p-2 text-start">
                          {t("exams.versions.answer")}
                        </th>
                        <th scope="col" className="p-2 text-start">
                          {t("exams.builder.points")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {key.data.items.map((entry) => (
                        <tr
                          key={entry.question_id}
                          className="border-t align-top"
                        >
                          <td className="p-2 tabular-nums">
                            {formatDigits(entry.number, digits)}
                          </td>
                          <td className="max-w-64 p-2">
                            <span dir="auto" className="line-clamp-2">
                              {stems.get(entry.question_id) ?? ""}
                            </span>
                          </td>
                          <td className="p-2">
                            {entry.correct?.length ? (
                              <bdi>{entry.correct.join("، ")}</bdi>
                            ) : entry.answer_text ? (
                              <QmdRenderer source={entry.answer_text} inline />
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="p-2 tabular-nums">{entry.points}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
