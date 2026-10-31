import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { apiClient, extractApiError } from "@/api/client";
import type { components } from "@/api/schema";
type Kind = NonNullable<components["schemas"]["ExportsIn"]["kinds"]>[number];
const kinds: Kind[] = [
  "pdf",
  "answer_key_pdf",
  "bubble_sheet_pdf",
  "docx",
  "answer_key_docx",
];
export function ExamExportsPanel({ examId }: { examId: string }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [count, setCount] = useState(1);
  const [shuffle, setShuffle] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [chosen, setChosen] = useState<Kind[]>(["pdf"]);
  const [error, setError] = useState("");
  const exam = useQuery({
    queryKey: ["exam", examId],
    queryFn: async () => {
      const r = await apiClient.GET("/api/v1/exams/{id}", {
        params: { path: { id: examId } },
      });
      if (!r.data) throw extractApiError(r.response.status, r.error);
      return r.data;
    },
  });
  const exports = useQuery({
    queryKey: ["exports", examId],
    queryFn: async () => {
      const r = await apiClient.GET("/api/v1/exams/{id}/exports", {
        params: { path: { id: examId } },
      });
      if (!r.data) throw extractApiError(r.response.status, r.error);
      return r.data;
    },
    refetchInterval: (q) =>
      q.state.data?.some((x) => x.status === "pending") ? 2000 : false,
  });
  const refresh = async () =>
    qc.invalidateQueries({ queryKey: ["exports", examId] });
  const request = async (versions: string[], selectedKinds: Kind[]) => {
    const r = await apiClient.POST("/api/v1/exams/{id}/exports", {
      params: { path: { id: examId } },
      body: { versions, kinds: selectedKinds },
    });
    if (!r.response.ok)
      setError(extractApiError(r.response.status, r.error).message);
    else {
      setError("");
      await refresh();
    }
  };
  if (!exam.data)
    return <p>{exam.isError ? t("exports.error") : t("admin.loading")}</p>;
  const items = exam.data.sections.flatMap((s) => s.items);
  const allMcq =
    items.length > 0 &&
    items.every((i) => ["mcq_single", "mcq_multi"].includes(i.question.type));
  return (
    <section className="space-y-4 [&_button]:rounded [&_button]:border [&_button]:px-3 [&_button]:py-1 [&_fieldset]:space-y-2 [&_fieldset]:border [&_fieldset]:p-3 [&_input]:me-2 [&_label]:block">
      <h1>{t("exports.title")}</h1>
      {exam.data.versions.length === 0 ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void (async () => {
              const r = await apiClient.POST("/api/v1/exams/{id}/versions", {
                params: { path: { id: examId } },
                body: {
                  count,
                  shuffle_questions: shuffle,
                  shuffle_choices: shuffle,
                  keep_first_as_original: false,
                },
              });
              if (!r.response.ok)
                setError(extractApiError(r.response.status, r.error).message);
              else await qc.invalidateQueries({ queryKey: ["exam", examId] });
            })();
          }}
        >
          <label>
            {t("exports.count")}
            <input
              type="number"
              min="1"
              max="10"
              value={count}
              onChange={(e) => {
                setCount(Number(e.target.value));
              }}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={shuffle}
              onChange={(e) => {
                setShuffle(e.target.checked);
              }}
            />
            {t("exports.shuffle")}
          </label>
          <button>{t("exports.generateVersions")}</button>
        </form>
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void request(selected, chosen);
          }}
        >
          <fieldset>
            <legend>{t("exports.versions")}</legend>
            {exam.data.versions.map((v) => (
              <label key={v.id}>
                <input
                  type="checkbox"
                  checked={selected.includes(v.label)}
                  onChange={(e) => {
                    setSelected(
                      e.target.checked
                        ? [...selected, v.label]
                        : selected.filter((x) => x !== v.label),
                    );
                  }}
                />
                {v.label}
              </label>
            ))}
          </fieldset>
          <fieldset>
            <legend>{t("exports.kinds")}</legend>
            {kinds
              .filter((k) => k !== "bubble_sheet_pdf" || allMcq)
              .map((k) => (
                <label key={k}>
                  <input
                    type="checkbox"
                    checked={chosen.includes(k)}
                    onChange={(e) => {
                      setChosen(
                        e.target.checked
                          ? [...chosen, k]
                          : chosen.filter((x) => x !== k),
                      );
                    }}
                  />
                  {t(`exports.${k}`)}
                </label>
              ))}
          </fieldset>
          <button disabled={!selected.length || !chosen.length}>
            {t("exports.generate")}
          </button>
        </form>
      )}
      {error && <p role="alert">{error}</p>}
      <ul>
        {exports.data?.map((x) => (
          <li key={x.id} className="border p-2">
            <span>
              {x.version_label} — {t(`exports.${x.kind}`)} —{" "}
              {t(`exports.${x.status}`)} — {x.size_bytes ?? "—"}{" "}
              {t("exports.bytes")} — {new Date(x.created_at).toLocaleString()}
            </span>
            {x.stale && (
              <>
                <strong>{t("exports.stale")}</strong>
                <button
                  type="button"
                  onClick={() => {
                    void request([x.version_label], [x.kind]);
                  }}
                >
                  {t("exports.regenerate")}
                </button>
              </>
            )}
            {x.error && <p role="alert">{x.error}</p>}
            {x.status === "ready" && (
              <a href={`/api/v1/exports/${x.id}/download`}>
                {t("exports.download")}
              </a>
            )}
            <button
              type="button"
              onClick={() => {
                void (async () => {
                  const r = await apiClient.DELETE("/api/v1/exports/{id}", {
                    params: { path: { id: x.id } },
                  });
                  if (!r.response.ok)
                    setError(
                      extractApiError(r.response.status, r.error).message,
                    );
                  else await refresh();
                })();
              }}
            >
              {t("admin.delete")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
export function ExamExportsPage() {
  const { id } = useParams();
  return id ? <ExamExportsPanel examId={id} /> : null;
}
