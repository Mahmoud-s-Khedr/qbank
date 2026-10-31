import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { setAppLanguage, type SupportedLanguage } from "@/i18n";

export function LanguageSwitch() {
  const { t, i18n } = useTranslation();
  const currentLang: SupportedLanguage = i18n.language.startsWith("en")
    ? "en"
    : "ar";

  return (
    <div
      role="group"
      aria-label={t("language.label")}
      className="border-input bg-muted/40 inline-flex items-center rounded-md border p-0.5"
    >
      <Button
        type="button"
        variant={currentLang === "ar" ? "secondary" : "ghost"}
        size="sm"
        lang="ar"
        aria-pressed={currentLang === "ar"}
        onClick={() => {
          void setAppLanguage("ar");
        }}
        className="h-7 px-2.5 text-xs"
      >
        {t("language.ar")}
      </Button>
      <Button
        type="button"
        variant={currentLang === "en" ? "secondary" : "ghost"}
        size="sm"
        lang="en"
        aria-pressed={currentLang === "en"}
        onClick={() => {
          void setAppLanguage("en");
        }}
        className="h-7 px-2.5 text-xs"
      >
        {t("language.en")}
      </Button>
    </div>
  );
}
