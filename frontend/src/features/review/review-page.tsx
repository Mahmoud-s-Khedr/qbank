import { ClipboardCheck } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";

export function ReviewPage() {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("pages.review.title")}
      </h1>
      <EmptyState
        icon={ClipboardCheck}
        title={t("pages.review.emptyTitle")}
        description={t("pages.review.emptyDescription")}
      />
    </section>
  );
}
