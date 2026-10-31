import { useTranslation } from "react-i18next";
import { errorCode, errorMessage } from "./exam-model";

/** Turns an API error into a localized sentence (by problem `code`), else the server message. */
export function useErrorText(): (error: unknown) => string {
  const { t, i18n } = useTranslation();
  return (error) => {
    const code = errorCode(error);
    if (code && i18n.exists(`exams.errors.${code}`)) {
      return t(`exams.errors.${code}`);
    }
    return errorMessage(error);
  };
}
