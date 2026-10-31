import { AlertTriangle, ArrowLeft, Eye, EyeOff } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router";
import { useExam, useExamMutations, type ExamDetail } from "@/api/hooks/exams";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { AiTab } from "./ai-tab";
import { BankTab } from "./bank-tab";
import { BlueprintTab } from "./blueprint-tab";
import { ExamPane } from "./exam-pane";
import { ExamPreview } from "./exam-preview";
import { SettingsTab } from "./settings-tab";
import { Tabs } from "./tabs";
import { useErrorText } from "./use-error-text";
import { VersionsTab } from "./versions-tab";

const TAB_IDS = ["bank", "blueprint", "ai", "settings", "versions"] as const;
type TabId = (typeof TAB_IDS)[number];

function isTabId(value: string | null): value is TabId {
  return TAB_IDS.some((id) => id === value);
}

export function ExamBuilderPage() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const exam = useExam(id);

  if (exam.isPending) {
    return (
      <div className="flex flex-col gap-3" aria-busy="true">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }
  if (exam.isError) {
    return (
      <div role="alert" className="flex flex-col items-start gap-3">
        <p className="text-destructive">{t("exams.loadError")}</p>
        <Button asChild variant="outline">
          <Link to="/exams">{t("exams.builder.back")}</Link>
        </Button>
      </div>
    );
  }
  return <Builder exam={exam.data} />;
}

function Builder({ exam }: { exam: ExamDetail }) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const mutations = useExamMutations(exam.id);
  const [params, setParams] = useSearchParams();
  const requested = params.get("tab");
  const tab: TabId = isTabId(requested) ? requested : "bank";
  const [preview, setPreview] = useState(false);
  const [targetId, setTargetId] = useState(exam.sections[0]?.id ?? "");
  const [title, setTitle] = useState(exam.title);
  const [titleError, setTitleError] = useState("");

  useEffect(() => {
    setTitle(exam.title);
  }, [exam.title]);

  // Keep the target section valid when sections change.
  const target = exam.sections.some((s) => s.id === targetId)
    ? targetId
    : (exam.sections[0]?.id ?? "");

  const commitTitle = () => {
    const next = title.trim();
    if (!next || next === exam.title) {
      setTitle(exam.title);
      return;
    }
    mutations.rename.mutate(next, {
      onSuccess: () => {
        setTitleError("");
      },
      onError: (e) => {
        setTitle(exam.title);
        setTitleError(errorText(e));
      },
    });
  };

  const stale = exam.versions.some((v) => v.stale);

  return (
    <div className="flex flex-col gap-4">
      <div className="bg-background/95 sticky top-0 z-10 flex flex-col gap-2 border-b pb-3 backdrop-blur">
        <div className="flex flex-wrap items-center gap-3">
          <Button asChild variant="ghost" size="icon">
            <Link to="/exams" aria-label={t("exams.builder.back")}>
              <ArrowLeft className="rtl:rotate-180" aria-hidden="true" />
            </Link>
          </Button>
          <Input
            className="min-w-48 flex-1 text-lg font-bold"
            dir="auto"
            aria-label={t("exams.builder.examTitle")}
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
            }}
            onBlur={commitTitle}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
            }}
          />
          <Button
            type="button"
            variant={preview ? "default" : "outline"}
            aria-pressed={preview}
            onClick={() => {
              setPreview((v) => !v);
            }}
          >
            {preview ? (
              <EyeOff aria-hidden="true" />
            ) : (
              <Eye aria-hidden="true" />
            )}
            {t("exams.builder.preview")}
          </Button>
        </div>
        <dl className="text-muted-foreground flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
          <div className="flex gap-1">
            <dt>{t("exams.builder.questions")}:</dt>
            <dd className="text-foreground font-medium tabular-nums">
              {exam.question_count}
            </dd>
          </div>
          <div className="flex gap-1">
            <dt>{t("exams.builder.totalPoints")}:</dt>
            <dd className="text-foreground font-medium tabular-nums">
              {exam.total_points}
            </dd>
          </div>
          <div className="flex gap-1">
            <dt>{t("exams.builder.sections")}:</dt>
            <dd className="text-foreground font-medium tabular-nums">
              {exam.sections.length}
            </dd>
          </div>
          <div className="flex gap-1">
            <dt>{t("exams.builder.revision")}:</dt>
            <dd className="text-foreground font-medium tabular-nums">
              {exam.revision}
            </dd>
          </div>
          <Badge variant="outline">{t(`exams.status.${exam.status}`)}</Badge>
        </dl>
        <div role="status" aria-live="polite">
          {stale ? (
            <p className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-sm">
              <AlertTriangle className="size-4" aria-hidden="true" />
              {t("exams.builder.staleWarning")}
            </p>
          ) : null}
          {titleError ? (
            <p className="text-destructive text-sm">{titleError}</p>
          ) : null}
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <section aria-label={t("exams.builder.examPane")}>
          {preview ? (
            <ExamPreview exam={exam} />
          ) : (
            <ExamPane
              exam={exam}
              targetSectionId={target}
              onTarget={setTargetId}
              mutations={mutations}
            />
          )}
        </section>
        <section
          aria-label={t("exams.builder.toolsPane")}
          className="flex flex-col"
        >
          <Tabs
            idPrefix="exam-tabs"
            label={t("exams.builder.toolsPane")}
            value={tab}
            onChange={(next) => {
              setParams(
                (current) => {
                  const copy = new URLSearchParams(current);
                  copy.set("tab", next);
                  return copy;
                },
                { replace: true },
              );
            }}
            tabs={[
              {
                id: "bank",
                label: t("exams.tabs.bank"),
                panel: (
                  <BankTab
                    exam={exam}
                    targetSectionId={target}
                    mutations={mutations}
                  />
                ),
              },
              {
                id: "blueprint",
                label: t("exams.tabs.blueprint"),
                panel: (
                  <BlueprintTab
                    exam={exam}
                    targetSectionId={target}
                    mutations={mutations}
                  />
                ),
              },
              {
                id: "ai",
                label: t("exams.tabs.ai"),
                panel: <AiTab exam={exam} mutations={mutations} />,
              },
              {
                id: "settings",
                label: t("exams.tabs.settings"),
                panel: <SettingsTab exam={exam} mutations={mutations} />,
              },
              {
                id: "versions",
                label: t("exams.tabs.versions"),
                panel: <VersionsTab exam={exam} />,
              },
            ]}
          />
        </section>
      </div>
    </div>
  );
}
