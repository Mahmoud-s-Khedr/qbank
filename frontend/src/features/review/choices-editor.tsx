import { ArrowDown, ArrowUp, Plus, Scissors, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type ChoiceDraft, nextChoiceKey } from "./review-model";

const AR_LABELS = ["أ", "ب", "ج", "د", "هـ", "و"];
const EN_LABELS = ["A", "B", "C", "D", "E", "F"];

export function ChoicesEditor({
  choices,
  onChange,
  lang,
  resolveAsset,
  onSplitAt,
  disabled = false,
}: {
  choices: readonly ChoiceDraft[];
  onChange: (choices: ChoiceDraft[]) => void;
  lang: "ar" | "en";
  resolveAsset?: ((id: string) => string | undefined) | undefined;
  onSplitAt?: ((index: number) => void) | undefined;
  disabled?: boolean;
}) {
  const { t } = useTranslation();

  const update = (index: number, patch: Partial<ChoiceDraft>) => {
    onChange(choices.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  };
  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= choices.length) return;
    const next = [...choices];
    const [item] = next.splice(index, 1);
    if (item) next.splice(target, 0, item);
    onChange(next);
  };
  const add = () => {
    const labels = lang === "ar" ? AR_LABELS : EN_LABELS;
    onChange([
      ...choices,
      {
        key: nextChoiceKey(),
        label: labels[choices.length] ?? "",
        content: "",
        is_correct: false,
        pinned: false,
      },
    ]);
  };

  return (
    <div className="flex flex-col gap-2" data-testid="choices-editor">
      <ul className="flex flex-col gap-2">
        {choices.map((choice, index) => (
          <li
            key={choice.key}
            data-testid={`choice-row-${String(index)}`}
            className="border-border flex flex-col gap-2 rounded-md border p-2"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Input
                className="w-16"
                aria-label={t("review.choices.label", { n: index + 1 })}
                value={choice.label}
                disabled={disabled}
                onChange={(event) => {
                  update(index, { label: event.target.value });
                }}
              />
              <label className="flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={choice.is_correct}
                  disabled={disabled}
                  onChange={(event) => {
                    update(index, { is_correct: event.target.checked });
                  }}
                />
                {t("review.choices.correct")}
              </label>
              <label className="flex items-center gap-1 text-xs">
                <input
                  type="checkbox"
                  checked={choice.pinned}
                  disabled={disabled}
                  onChange={(event) => {
                    update(index, { pinned: event.target.checked });
                  }}
                />
                {t("review.choices.pinned")}
              </label>
              <span className="ms-auto flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  disabled={disabled || index === 0}
                  aria-label={t("review.choices.moveUp", { n: index + 1 })}
                  onClick={() => {
                    move(index, -1);
                  }}
                >
                  <ArrowUp aria-hidden="true" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  disabled={disabled || index === choices.length - 1}
                  aria-label={t("review.choices.moveDown", { n: index + 1 })}
                  onClick={() => {
                    move(index, 1);
                  }}
                >
                  <ArrowDown aria-hidden="true" />
                </Button>
                {onSplitAt ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7"
                    disabled={disabled || index === 0}
                    aria-label={t("review.choices.splitBefore", {
                      n: index + 1,
                    })}
                    onClick={() => {
                      onSplitAt(index);
                    }}
                  >
                    <Scissors aria-hidden="true" />
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-7"
                  disabled={disabled}
                  aria-label={t("review.choices.remove", { n: index + 1 })}
                  onClick={() => {
                    onChange(choices.filter((_, i) => i !== index));
                  }}
                >
                  <Trash2 aria-hidden="true" />
                </Button>
              </span>
            </div>
            <textarea
              rows={2}
              aria-label={t("review.choices.content", { n: index + 1 })}
              className="border-input bg-background w-full rounded-md border p-2 text-sm"
              value={choice.content}
              disabled={disabled}
              dir="auto"
              onChange={(event) => {
                update(index, { content: event.target.value });
              }}
            />
            {choice.content ? (
              <QmdRenderer
                source={choice.content}
                lang={lang}
                inline
                resolveAsset={resolveAsset}
                className="text-muted-foreground text-sm"
              />
            ) : null}
          </li>
        ))}
      </ul>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        disabled={disabled}
        onClick={add}
      >
        <Plus aria-hidden="true" />
        {t("review.choices.add")}
      </Button>
    </div>
  );
}
