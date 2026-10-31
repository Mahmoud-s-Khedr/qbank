import { Library } from "lucide-react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "@/components/empty-state";

export function BankPage() {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("pages.bank.title")}
      </h1>
      <EmptyState
        icon={Library}
        title={t("pages.bank.emptyTitle")}
        description={t("pages.bank.emptyDescription")}
      />
    </section>
  );
}
