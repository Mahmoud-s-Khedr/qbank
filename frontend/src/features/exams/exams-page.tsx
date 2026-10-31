import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";

export function ExamsPage() {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("pages.exams.title")}
      </h1>
      <EmptyState
        icon={FileText}
        title={t("pages.exams.emptyTitle")}
        description={t("pages.exams.emptyDescription")}
      />
    </section>
  );
}
