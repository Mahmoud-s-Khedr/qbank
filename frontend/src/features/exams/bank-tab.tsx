import { Check, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  useBankSearch,
  useExamMutations,
  useSubjectTree,
  type ExamDetail,
} from "@/api/hooks/exams";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useErrorText } from "./use-error-text";

export const QUESTION_TYPES = [
  "mcq_single",
  "mcq_multi",
  "true_false",
  "fill_blank",
  "short_answer",
  "essay",
  "matching",
  "ordering",
] as const;

const SELECT_CLASS =
  "border-input bg-background h-9 rounded-md border px-2 text-sm";

export function BankTab({
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
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [chapterId, setChapterId] = useState("");
  const [lessonId, setLessonId] = useState("");
  const [type, setType] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(query.trim());
    }, 300);
    return () => {
      clearTimeout(timer);
    };
  }, [query]);

  const tree = useSubjectTree(exam.subject_id);
  const search = useBankSearch({
    q: debounced,
    subjectId: exam.subject_id,
    chapterId,
    lessonId,
    type,
    difficulty,
  });

  const inExam = new Set(
    exam.sections.flatMap((s) => s.items.map((i) => i.question_id)),
  );
  const chapters = tree.data?.chapters ?? [];
  const lessons = chapterId
    ? (chapters.find((c) => c.id === chapterId)?.lessons ?? [])
    : [];
  const target = exam.sections.find((s) => s.id === targetSectionId);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-muted-foreground text-sm">
        {t("exams.bank.addingTo", { title: target?.title ?? "" })}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <Input
          className="col-span-2"
          type="search"
          aria-label={t("exams.bank.search")}
          placeholder={t("exams.bank.search")}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
        />
        <select
          className={SELECT_CLASS}
          aria-label={t("exams.bank.chapter")}
          value={chapterId}
          onChange={(event) => {
            setChapterId(event.target.value);
            setLessonId("");
          }}
        >
          <option value="">{t("exams.bank.allChapters")}</option>
          {chapters.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <select
          className={SELECT_CLASS}
          aria-label={t("exams.bank.lesson")}
          value={lessonId}
          disabled={!chapterId}
          onChange={(event) => {
            setLessonId(event.target.value);
          }}
        >
          <option value="">{t("exams.bank.allLessons")}</option>
          {lessons.map((l) => (
            <option key={l.id} value={l.id}>
              {l.title}
            </option>
          ))}
        </select>
        <select
          className={SELECT_CLASS}
          aria-label={t("exams.bank.type")}
          value={type}
          onChange={(event) => {
            setType(event.target.value);
          }}
        >
          <option value="">{t("exams.bank.allTypes")}</option>
          {QUESTION_TYPES.map((value) => (
            <option key={value} value={value}>
              {t(`review.types.${value}`)}
            </option>
          ))}
        </select>
        <select
          className={SELECT_CLASS}
          aria-label={t("exams.bank.difficulty")}
          value={difficulty}
          onChange={(event) => {
            setDifficulty(event.target.value);
          }}
        >
          <option value="">{t("exams.bank.anyDifficulty")}</option>
          {[1, 2, 3, 4, 5].map((n) => (
            <option key={n} value={n}>
              {t("exams.builder.difficulty", { n })}
            </option>
          ))}
        </select>
      </div>
      <p className="text-muted-foreground text-xs">
        {t("exams.bank.approvedOnly")}
      </p>
      <div role="alert">
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
      </div>
      <div aria-live="polite">
        {search.isPending ? (
          <p className="text-muted-foreground text-sm">{t("exams.loading")}</p>
        ) : search.isError ? (
          <p className="text-destructive text-sm">{t("exams.loadError")}</p>
        ) : search.data.items.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            {t("exams.bank.noResults")}
          </p>
        ) : (
          <p className="sr-only">
            {t("exams.bank.resultCount", { count: search.data.total })}
          </p>
        )}
      </div>
      <ul className="flex flex-col gap-2">
        {search.data?.items.map((question) => {
          const added = inExam.has(question.id);
          return (
            <li
              key={question.id}
              className="flex items-start gap-2 rounded-md border p-2"
            >
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <p dir="auto" className="line-clamp-3 text-sm">
                  {question.stem_preview}
                </p>
                <div className="flex flex-wrap gap-1 text-xs">
                  <Badge variant="secondary">
                    {t(`review.types.${question.type}`)}
                  </Badge>
                  {question.difficulty !== null ? (
                    <Badge variant="outline">
                      {t("exams.builder.difficulty", {
                        n: question.difficulty,
                      })}
                    </Badge>
                  ) : null}
                  {question.chapter_title ? (
                    <Badge variant="outline">{question.chapter_title}</Badge>
                  ) : null}
                  {question.stimulus_id ? (
                    <Badge variant="info">{t("exams.builder.stimulus")}</Badge>
                  ) : null}
                </div>
              </div>
              {added ? (
                <Badge variant="success">
                  <Check className="size-3" aria-hidden="true" />
                  {t("exams.bank.inExam")}
                </Badge>
              ) : (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={mutations.addItems.isPending}
                  aria-label={t("exams.bank.addAria", {
                    stem: question.stem_preview.slice(0, 40),
                  })}
                  onClick={() => {
                    setError("");
                    mutations.addItems.mutate(
                      {
                        question_ids: [question.id],
                        points: 1,
                        section_id: targetSectionId,
                      },
                      {
                        onError: (e) => {
                          setError(errorText(e));
                        },
                      },
                    );
                  }}
                >
                  <Plus aria-hidden="true" />
                  {t("exams.bank.add")}
                </Button>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
