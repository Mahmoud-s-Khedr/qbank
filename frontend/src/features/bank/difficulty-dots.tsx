import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";

export function DifficultyDots({
  difficulty,
  className,
}: {
  difficulty: number | null | undefined;
  className?: string;
}) {
  const { t } = useTranslation();
  const level = Math.max(1, Math.min(5, difficulty ?? 1));

  return (
    <div
      className={cn("flex items-center gap-1", className)}
      title={t("bank.question.difficultyLevel", { level })}
      aria-label={t("bank.question.difficultyLevel", { level })}
    >
      {[1, 2, 3, 4, 5].map((dot) => (
        <span
          key={dot}
          className={cn(
            "size-2 rounded-full transition-colors",
            dot <= level ? "bg-amber-500" : "bg-muted-foreground/30",
          )}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
