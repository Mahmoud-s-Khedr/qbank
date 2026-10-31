import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";

export function SourcesPage() {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("pages.sources.title")}
      </h1>
      <EmptyState
        icon={BookOpen}
        title={t("pages.sources.emptyTitle")}
        description={t("pages.sources.emptyDescription")}
      />
    </section>
  );
}
