import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import {
  type DraftQuestion,
  type QuestionOut,
  useCreateQuestion,
  usePatchQuestion,
} from "@/api/hooks/review";
import type { Box } from "@/components/page-canvas/PageCanvas";
import { QmdEditor } from "@/components/qmd/QmdEditor";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ChoicesEditor } from "./choices-editor";
import {
  type ChoiceDraft,
  isQuestionType,
  nextChoiceKey,
  QUESTION_TYPES,
} from "./review-model";

export function MissedQuestionDialog({
  draft,
  box,
  pageId,
  subjectId,
  lang,
  onCreated,
  onClose,
}: {
  draft: DraftQuestion;
  box: Box;
  pageId: string;
  subjectId: string;
  lang: "ar" | "en";
  onCreated: (question: QuestionOut) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [numberLabel, setNumberLabel] = useState(draft.number_label);
  const [type, setType] = useState(draft.type);
  const [stem, setStem] = useState(draft.stem);
  const [answer, setAnswer] = useState(
    draft.answer?.text ?? draft.answer?.labels.join(", ") ?? "",
  );
  const [choices, setChoices] = useState<ChoiceDraft[]>(() =>
    draft.choices.map((c) => ({
      key: nextChoiceKey(),
      label: c.label,
      content: c.content,
      is_correct: draft.answer?.labels.includes(c.label) ?? false,
      pinned: false,
    })),
  );
  const create = useCreateQuestion();
  const patch = usePatchQuestion();

  const save = async () => {
    try {
      const created = await create.mutateAsync({
        subject_id: subjectId,
        type,
        stem,
        number_label: numberLabel,
        ...(answer ? { answer } : {}),
        choices: choices.map((c) => ({
          label: c.label,
          content: c.content,
          is_correct: c.is_correct,
          pinned: c.pinned,
        })),
      });
      // POST /questions has no `regions` field, so the page box is attached right after.
      const withRegion = await patch.mutateAsync({
        id: created.id,
        patch: {
          version: created.version,
          regions: [{ page: pageId, box }],
        },
      });
      toast.success(t("review.missed.created"));
      onCreated(withRegion);
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : t("review.missed.failed"),
      );
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent
        className="max-h-[90vh] max-w-2xl overflow-auto"
        data-testid="missed-dialog"
      >
        <DialogHeader>
          <DialogTitle>{t("review.missed.title")}</DialogTitle>
          <DialogDescription>
            {t("review.missed.description")}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1">
              <Label htmlFor="missed-number">
                {t("review.fields.number_label")}
              </Label>
              <Input
                id="missed-number"
                value={numberLabel}
                onChange={(event) => {
                  setNumberLabel(event.target.value);
                }}
              />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="missed-type">{t("review.fields.type")}</Label>
              <select
                id="missed-type"
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={type}
                onChange={(event) => {
                  if (isQuestionType(event.target.value))
                    setType(event.target.value);
                }}
              >
                {QUESTION_TYPES.map((qt) => (
                  <option key={qt} value={qt}>
                    {t(`review.types.${qt}`)}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <QmdEditor
            id="missed-stem"
            label={t("review.fields.stem")}
            value={stem}
            lang={lang}
            onChange={setStem}
          />
          <ChoicesEditor choices={choices} lang={lang} onChange={setChoices} />
          <div className="flex flex-col gap-1">
            <Label htmlFor="missed-answer">{t("review.fields.answer")}</Label>
            <Input
              id="missed-answer"
              dir="auto"
              value={answer}
              onChange={(event) => {
                setAnswer(event.target.value);
              }}
            />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("review.common.cancel")}
          </Button>
          <Button
            type="button"
            disabled={create.isPending || patch.isPending || stem.trim() === ""}
            onClick={() => {
              void save();
            }}
          >
            {t("review.missed.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
