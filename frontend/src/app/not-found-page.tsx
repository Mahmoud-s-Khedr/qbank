import { FileQuestion } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold tracking-tight">
        {t("pages.notFound.code")} — {t("pages.notFound.title")}
      </h1>
      <EmptyState
        icon={FileQuestion}
        title={t("pages.notFound.title")}
        description={t("pages.notFound.description")}
      >
        <Button asChild>
          <Link to="/sources">{t("pages.notFound.backHome")}</Link>
        </Button>
      </EmptyState>
    </section>
  );
}
