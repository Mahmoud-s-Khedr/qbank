import { Archive, Copy, FileText, Plus } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { useMe } from "@/api/hooks/auth";
import {
  useArchiveExam,
  useCreateExam,
  useDuplicateExam,
  useExamList,
  useTemplates,
  type ExamStatus,
} from "@/api/hooks/exams";
import { useSubjects } from "@/api/hooks/subjects";
import { EmptyState } from "@/components/empty-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { formatRelativeTime } from "@/lib/format";
import { useErrorText } from "./use-error-text";

const STATUSES: readonly (ExamStatus | "")[] = [
  "",
  "draft",
  "final",
  "archived",
];

export function ExamsPage() {
  const { t, i18n } = useTranslation();
  const errorText = useErrorText();
  const navigate = useNavigate();
  const me = useMe();
  const isAdmin = me.data?.role === "admin";
  const [status, setStatus] = useState<ExamStatus | "">("");
  const [mineOnly, setMineOnly] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const list = useExamList(status);
  const subjects = useSubjects();
  const duplicate = useDuplicateExam();
  const archive = useArchiveExam();

  const subjectName = (id: string) =>
    subjects.data?.items.find((s) => s.id === id)?.name ??
    t("exams.list.unknownSubject");

  const items = (list.data?.items ?? []).filter(
    (exam) => !isAdmin || !mineOnly || exam.owner_id === me.data?.id,
  );

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">
          {t("pages.exams.title")}
        </h1>
        <Button
          type="button"
          onClick={() => {
            setCreating(true);
          }}
        >
          <Plus aria-hidden="true" />
          {t("exams.list.create")}
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          {t("exams.list.statusFilter")}
          <select
            className="border-input bg-background h-9 rounded-md border px-2"
            value={status}
            onChange={(event) => {
              const value = event.target.value;
              setStatus(
                value === "draft" || value === "final" || value === "archived"
                  ? value
                  : "",
              );
            }}
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value
                  ? t(`exams.status.${value}`)
                  : t("exams.list.allStatuses")}
              </option>
            ))}
          </select>
        </label>
        {isAdmin ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={mineOnly}
              onChange={(event) => {
                setMineOnly(event.target.checked);
              }}
            />
            {t("exams.list.mineOnly")}
          </label>
        ) : null}
      </div>

      <div role="alert">
        {error ? <p className="text-destructive text-sm">{error}</p> : null}
      </div>

      {list.isPending ? (
        <p className="text-muted-foreground" aria-live="polite">
          {t("exams.loading")}
        </p>
      ) : list.isError ? (
        <p role="alert" className="text-destructive">
          {t("exams.loadError")}
        </p>
      ) : items.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={t("pages.exams.emptyTitle")}
          description={t("pages.exams.emptyDescription")}
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                {(
                  [
                    "title",
                    "subject",
                    "status",
                    "questions",
                    "points",
                    "versions",
                    "updated",
                    "actions",
                  ] as const
                ).map((column) => (
                  <th key={column} scope="col" className="p-3 text-start">
                    {t(`exams.list.${column}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {items.map((exam) => (
                <tr key={exam.id} className="border-t">
                  <td className="p-3 font-medium">
                    <Link
                      className="text-primary hover:underline"
                      to={`/exams/${exam.id}`}
                    >
                      {exam.title}
                    </Link>
                  </td>
                  <td className="p-3">{subjectName(exam.subject_id)}</td>
                  <td className="p-3">
                    <Badge
                      variant={
                        exam.status === "final"
                          ? "success"
                          : exam.status === "archived"
                            ? "secondary"
                            : "info"
                      }
                    >
                      {t(`exams.status.${exam.status}`)}
                    </Badge>
                  </td>
                  <td className="p-3 tabular-nums">{exam.question_count}</td>
                  <td className="p-3 tabular-nums">{exam.total_points}</td>
                  <td className="p-3">
                    <span className="inline-flex items-center gap-2">
                      <span className="tabular-nums">
                        {exam.versions_count}
                      </span>
                      {exam.has_stale_versions ? (
                        <Badge variant="warning">
                          {t("exams.versions.stale")}
                        </Badge>
                      ) : null}
                    </span>
                  </td>
                  <td className="p-3">
                    {formatRelativeTime(exam.updated_at, i18n.language)}
                  </td>
                  <td className="p-3">
                    <div className="flex gap-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={duplicate.isPending}
                        aria-label={t("exams.list.duplicateAria", {
                          title: exam.title,
                        })}
                        onClick={() => {
                          setError("");
                          duplicate.mutate(exam.id, {
                            onError: (e) => {
                              setError(errorText(e));
                            },
                          });
                        }}
                      >
                        <Copy aria-hidden="true" />
                        {t("exams.list.duplicate")}
                      </Button>
                      {exam.status !== "archived" ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          disabled={archive.isPending}
                          aria-label={t("exams.list.archiveAria", {
                            title: exam.title,
                          })}
                          onClick={() => {
                            setError("");
                            archive.mutate(exam.id, {
                              onError: (e) => {
                                setError(errorText(e));
                              },
                            });
                          }}
                        >
                          <Archive aria-hidden="true" />
                          {t("exams.list.archive")}
                        </Button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <CreateExamDialog
        open={creating}
        onClose={() => {
          setCreating(false);
        }}
        onCreated={(id) => {
          void navigate(`/exams/${id}`);
        }}
      />
    </section>
  );
}

function CreateExamDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const subjects = useSubjects();
  const templates = useTemplates();
  const create = useCreateExam();
  const [subjectId, setSubjectId] = useState("");
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [error, setError] = useState("");

  const subjectList = subjects.data?.items ?? [];
  const chosenSubject = subjectId ? subjectId : (subjectList[0]?.id ?? "");

  const submit = () => {
    const subject = subjectList.find((s) => s.id === chosenSubject);
    const template = templates.data?.items.find((tpl) => tpl.id === templateId);
    if (!subject || !title.trim()) return;
    setError("");
    create.mutate(
      {
        subject_id: subject.id,
        title: title.trim(),
        settings: {
          language: subject.language,
          ...(template
            ? { template_id: template.id, header: template.header }
            : {}),
        },
      },
      {
        onSuccess: (exam) => {
          setTitle("");
          onCreated(exam.id);
        },
        onError: (e) => {
          setError(errorText(e));
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("exams.list.createTitle")}</DialogTitle>
          <DialogDescription>
            {t("exams.list.createDescription")}
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <label className="flex flex-col gap-1 text-sm">
            {t("exams.list.subject")}
            <select
              className="border-input bg-background h-9 rounded-md border px-2"
              value={chosenSubject}
              onChange={(event) => {
                setSubjectId(event.target.value);
              }}
            >
              {subjectList.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("exams.list.examTitle")}
            <Input
              dir="auto"
              required
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
              }}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            {t("exams.list.template")}
            <select
              className="border-input bg-background h-9 rounded-md border px-2"
              value={templateId}
              onChange={(event) => {
                setTemplateId(event.target.value);
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
          <div role="alert">
            {error ? <p className="text-destructive text-sm">{error}</p> : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("review.common.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={create.isPending || !title.trim() || !chosenSubject}
            >
              {t("exams.list.createSubmit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
