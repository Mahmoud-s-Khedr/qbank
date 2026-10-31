import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "@/i18n/ar.json";
import en from "@/i18n/en.json";

export type SupportedLanguage = "ar" | "en";

export const LANGUAGE_STORAGE_KEY = "qbank_lang";

export function isSupportedLanguage(
  value: string | null | undefined,
): value is SupportedLanguage {
  return value === "ar" || value === "en";
}

export function getDirection(lang: string): "rtl" | "ltr" {
  return lang.startsWith("ar") ? "rtl" : "ltr";
}

function getInitialLanguage(): SupportedLanguage {
  if (typeof window === "undefined") {
    return "ar";
  }
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isSupportedLanguage(stored)) {
      return stored;
    }
  } catch {
    // Ignore storage access errors
  }
  return "ar";
}

export function applyLanguageToDocument(lang: SupportedLanguage): void {
  if (typeof document === "undefined") {
    return;
  }
  const dir = getDirection(lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = dir;
}

const initialLanguage = getInitialLanguage();
applyLanguageToDocument(initialLanguage);

void i18n.use(initReactI18next).init({
  resources: {
    ar: { translation: ar },
    en: { translation: en },
  },
  lng: initialLanguage,
  fallbackLng: "ar",
  interpolation: {
    escapeValue: false,
  },
});

i18n.on("languageChanged", (lng: string) => {
  const normalized: SupportedLanguage = lng.startsWith("en") ? "en" : "ar";
  applyLanguageToDocument(normalized);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, normalized);
    } catch {
      // Ignore storage write errors
    }
  }
});

export async function setAppLanguage(lang: SupportedLanguage): Promise<void> {
  await i18n.changeLanguage(lang);
}

export default i18n;
