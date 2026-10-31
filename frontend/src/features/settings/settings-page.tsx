import { Settings } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";

export function SettingsPage() {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("pages.settings.title")}
      </h1>
      <EmptyState
        icon={Settings}
        title={t("pages.settings.emptyTitle")}
        description={t("pages.settings.emptyDescription")}
      />
    </section>
  );
}
