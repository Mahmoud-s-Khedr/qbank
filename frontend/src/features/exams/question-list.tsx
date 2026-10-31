import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { QuestionOut } from "@/api/hooks/review";
import { assetImageUrl } from "@/api/hooks/review";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

/** Selected questions with a QMD preview, and an optional remove button per question. */
export function QuestionList({
  ids,
  questions,
  onRemove,
}: {
  ids: readonly string[];
  questions: Map<string, QuestionOut>;
  onRemove?: ((id: string) => void) | undefined;
}) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-col gap-2">
      {ids.map((id) => {
        const question = questions.get(id);
        return (
          <li key={id} className="flex items-start gap-2 rounded-md border p-2">
            <div className="flex min-w-0 flex-1 flex-col gap-1 text-sm">
              {question ? (
                <>
                  <QmdRenderer
                    source={question.stem}
                    resolveAsset={assetImageUrl}
                  />
                  <div className="flex gap-1 text-xs">
                    <Badge variant="secondary">
                      {t(`review.types.${question.type}`)}
                    </Badge>
                    {question.difficulty !== null ? (
                      <Badge variant="outline">
                        {t("exams.builder.difficulty", {
                          n: question.difficulty,
                        })}
                      </Badge>
                    ) : null}
                  </div>
                </>
              ) : (
                <span className="text-muted-foreground">
                  {t("exams.loading")}
                </span>
              )}
            </div>
            {onRemove ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={t("exams.ai.removeQuestion", {
                  stem: question?.stem.slice(0, 40) ?? id,
                })}
                onClick={() => {
                  onRemove(id);
                }}
              >
                <X aria-hidden="true" />
                {t("exams.builder.remove")}
              </Button>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
