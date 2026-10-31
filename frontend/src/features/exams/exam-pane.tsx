import { ArrowDown, ArrowUp, Plus, Target, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/features/review/dialogs";
import {
  useExamMutations,
  type ExamDetail,
  type ItemOut,
  type SectionOut,
} from "@/api/hooks/exams";
import {
  errorCode,
  errorStatus,
  formatDigits,
  groupUnits,
  moveIdOrder,
  moveUnitOrder,
  type Unit,
} from "./exam-model";
import { useErrorText } from "./use-error-text";

type Mutations = ReturnType<typeof useExamMutations>;

export function ExamPane({
  exam,
  targetSectionId,
  onTarget,
  mutations,
}: {
  exam: ExamDetail;
  targetSectionId: string;
  onTarget: (id: string) => void;
  mutations: Mutations;
}) {
  const { t } = useTranslation();
  const errorText = useErrorText();
  const [error, setError] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [groupPrompt, setGroupPrompt] = useState<string | null>(null);
  const [sectionToDelete, setSectionToDelete] = useState<SectionOut | null>(
    null,
  );

  const fail = (e: unknown) => {
    setError(errorText(e));
  };

  const numbering = new Map<string, number>();
  let counter = 0;
  for (const section of exam.sections) {
    for (const item of section.items) numbering.set(item.id, ++counter);
  }
  const digits = exam.settings.layout?.digits ?? "arabic";

  const removeItem = (id: string, group = false) => {
    setError("");
    mutations.removeItem.mutate(
      { id, group },
      {
        onSuccess: () => {
          setGroupPrompt(null);
        },
        onError: (e) => {
          if (errorStatus(e) === 409 && errorCode(e) === "stimulus_group") {
            setGroupPrompt(id);
          } else {
            fail(e);
          }
        },
      },
    );
  };

  const reorderItems = (sectionId: string, ids: string[] | null) => {
    if (!ids) return;
    setError("");
    mutations.reorderItems.mutate({ sectionId, ids }, { onError: fail });
  };

  return (
    <div className="flex flex-col gap-4">
      <div role="alert" aria-live="assertive">
        {error ? (
          <p className="border-destructive/40 bg-destructive/10 text-destructive rounded-md border p-3 text-sm">
            {error}
          </p>
        ) : null}
      </div>

      {exam.sections.map((section, sectionIndex) => {
        const units = groupUnits(section.items);
        const isTarget = section.id === targetSectionId;
        return (
          <section
            key={section.id}
            aria-label={section.title}
            className={`bg-card flex flex-col gap-3 rounded-lg border p-3 ${isTarget ? "border-primary" : ""}`}
          >
            <SectionHeader
              section={section}
              isTarget={isTarget}
              canUp={sectionIndex > 0}
              canDown={sectionIndex < exam.sections.length - 1}
              onTarget={() => {
                onTarget(section.id);
              }}
              onRename={(title) => {
                mutations.editSection.mutate(
                  { id: section.id, body: { title } },
                  { onError: fail },
                );
              }}
              onInstructions={(instructions) => {
                mutations.editSection.mutate(
                  { id: section.id, body: { instructions } },
                  { onError: fail },
                );
              }}
              onMove={(delta) => {
                const order = moveIdOrder(
                  exam.sections.map((s) => s.id),
                  sectionIndex,
                  delta,
                );
                if (order) {
                  setError("");
                  mutations.reorderSections.mutate(order, { onError: fail });
                }
              }}
              onDelete={() => {
                setSectionToDelete(section);
              }}
            />
            {units.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                {t("exams.builder.sectionEmpty")}
              </p>
            ) : (
              <ol className="flex flex-col gap-2">
                {units.map((unit, unitIndex) => (
                  <UnitBlock
                    key={unit.items[0]?.id}
                    unit={unit}
                    digits={digits}
                    numbering={numbering}
                    sections={exam.sections}
                    sectionId={section.id}
                    canUp={unitIndex > 0}
                    canDown={unitIndex < units.length - 1}
                    onMove={(delta) => {
                      reorderItems(
                        section.id,
                        moveUnitOrder(section.items, unitIndex, delta),
                      );
                    }}
                    onPoints={(item, points) => {
                      mutations.editPoints.mutate(
                        { id: item.id, points },
                        { onError: fail },
                      );
                    }}
                    onRemove={(item) => {
                      removeItem(item.id);
                    }}
                    onMoveSection={(item, target) => {
                      setError("");
                      mutations.moveItem.mutate(
                        { id: item.id, sectionId: target },
                        { onError: fail },
                      );
                    }}
                  />
                ))}
              </ol>
            )}
          </section>
        );
      })}

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const title = newTitle.trim();
          if (!title) return;
          mutations.addSection.mutate(
            { title },
            {
              onSuccess: () => {
                setNewTitle("");
              },
              onError: fail,
            },
          );
        }}
      >
        <Input
          aria-label={t("exams.builder.newSectionTitle")}
          placeholder={t("exams.builder.newSectionTitle")}
          value={newTitle}
          onChange={(event) => {
            setNewTitle(event.target.value);
          }}
        />
        <Button type="submit" variant="outline">
          <Plus aria-hidden="true" />
          {t("exams.builder.addSection")}
        </Button>
      </form>

      <ConfirmDialog
        open={groupPrompt !== null}
        title={t("exams.builder.groupTitle")}
        description={t("exams.builder.groupDescription")}
        confirmLabel={t("exams.builder.removeGroup")}
        destructive
        pending={mutations.removeItem.isPending}
        onConfirm={() => {
          if (groupPrompt) removeItem(groupPrompt, true);
        }}
        onClose={() => {
          setGroupPrompt(null);
        }}
        testId="group-dialog"
      />
      <ConfirmDialog
        open={sectionToDelete !== null}
        title={t("exams.builder.deleteSectionTitle")}
        description={t("exams.builder.deleteSectionDescription", {
          title: sectionToDelete?.title ?? "",
        })}
        confirmLabel={t("exams.builder.deleteSection")}
        destructive
        pending={mutations.deleteSection.isPending}
        onConfirm={() => {
          if (!sectionToDelete) return;
          setError("");
          mutations.deleteSection.mutate(sectionToDelete.id, {
            onError: fail,
            onSettled: () => {
              setSectionToDelete(null);
            },
          });
        }}
        onClose={() => {
          setSectionToDelete(null);
        }}
      />
    </div>
  );
}

function SectionHeader({
  section,
  isTarget,
  canUp,
  canDown,
  onTarget,
  onRename,
  onInstructions,
  onMove,
  onDelete,
}: {
  section: SectionOut;
  isTarget: boolean;
  canUp: boolean;
  canDown: boolean;
  onTarget: () => void;
  onRename: (title: string) => void;
  onInstructions: (text: string) => void;
  onMove: (delta: -1 | 1) => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState(section.title);
  const [instructions, setInstructions] = useState(section.instructions ?? "");
  useEffect(() => {
    setTitle(section.title);
    setInstructions(section.instructions ?? "");
  }, [section.title, section.instructions]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="min-w-40 flex-1 font-semibold"
          aria-label={t("exams.builder.sectionTitle")}
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
          }}
          onBlur={() => {
            const next = title.trim();
            if (next && next !== section.title) onRename(next);
            else setTitle(section.title);
          }}
        />
        <Button
          type="button"
          size="sm"
          variant={isTarget ? "default" : "outline"}
          aria-pressed={isTarget}
          onClick={onTarget}
        >
          <Target aria-hidden="true" />
          {isTarget
            ? t("exams.builder.targetActive")
            : t("exams.builder.setTarget")}
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          disabled={!canUp}
          aria-label={t("exams.builder.sectionUp", { title: section.title })}
          onClick={() => {
            onMove(-1);
          }}
        >
          <ArrowUp aria-hidden="true" />
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          disabled={!canDown}
          aria-label={t("exams.builder.sectionDown", { title: section.title })}
          onClick={() => {
            onMove(1);
          }}
        >
          <ArrowDown aria-hidden="true" />
        </Button>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          aria-label={t("exams.builder.deleteSectionAria", {
            title: section.title,
          })}
          onClick={onDelete}
        >
          <Trash2 aria-hidden="true" />
        </Button>
      </div>
      <Input
        aria-label={t("exams.builder.sectionInstructions")}
        placeholder={t("exams.builder.sectionInstructions")}
        value={instructions}
        onChange={(event) => {
          setInstructions(event.target.value);
        }}
        onBlur={() => {
          if (instructions !== (section.instructions ?? "")) {
            onInstructions(instructions);
          }
        }}
      />
    </div>
  );
}

function UnitBlock({
  unit,
  digits,
  numbering,
  sections,
  sectionId,
  canUp,
  canDown,
  onMove,
  onPoints,
  onRemove,
  onMoveSection,
}: {
  unit: Unit;
  digits: string;
  numbering: Map<string, number>;
  sections: readonly SectionOut[];
  sectionId: string;
  canUp: boolean;
  canDown: boolean;
  onMove: (delta: -1 | 1) => void;
  onPoints: (item: ItemOut, points: number) => void;
  onRemove: (item: ItemOut) => void;
  onMoveSection: (item: ItemOut, sectionId: string) => void;
}) {
  const { t } = useTranslation();
  const stimulus = unit.items[0]?.stimulus;
  const grouped = unit.stimulusId !== null && unit.items.length > 1;
  const first = unit.items[0];
  const label = first ? formatDigits(numbering.get(first.id) ?? 0, digits) : "";

  return (
    <li
      className={
        grouped ? "bg-muted/40 rounded-md border border-dashed p-2" : ""
      }
      data-testid={grouped ? "stimulus-group" : undefined}
    >
      <div className="flex items-start gap-2">
        <div className="flex flex-col gap-1">
          <Button
            type="button"
            size="icon"
            variant="ghost"
            disabled={!canUp}
            aria-label={t("exams.builder.moveUp", { n: label })}
            onClick={() => {
              onMove(-1);
            }}
          >
            <ArrowUp aria-hidden="true" />
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            disabled={!canDown}
            aria-label={t("exams.builder.moveDown", { n: label })}
            onClick={() => {
              onMove(1);
            }}
          >
            <ArrowDown aria-hidden="true" />
          </Button>
        </div>
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          {unit.stimulusId !== null && stimulus ? (
            <div className="bg-background rounded border p-2 text-sm">
              <Badge variant="info" className="mb-1">
                {t("exams.builder.stimulus")}
              </Badge>
              <QmdRenderer source={stimulus.content} />
            </div>
          ) : null}
          {unit.items.map((item) => (
            <ItemRow
              key={item.id}
              item={item}
              number={formatDigits(numbering.get(item.id) ?? 0, digits)}
              sections={sections}
              sectionId={sectionId}
              grouped={grouped}
              onPoints={onPoints}
              onRemove={onRemove}
              onMoveSection={onMoveSection}
            />
          ))}
        </div>
      </div>
    </li>
  );
}

function ItemRow({
  item,
  number,
  sections,
  sectionId,
  grouped,
  onPoints,
  onRemove,
  onMoveSection,
}: {
  item: ItemOut;
  number: string;
  sections: readonly SectionOut[];
  sectionId: string;
  grouped: boolean;
  onPoints: (item: ItemOut, points: number) => void;
  onRemove: (item: ItemOut) => void;
  onMoveSection: (item: ItemOut, sectionId: string) => void;
}) {
  const { t } = useTranslation();
  const [points, setPoints] = useState(String(item.points));
  useEffect(() => {
    setPoints(String(item.points));
  }, [item.points]);

  const commit = () => {
    const value = Number(points);
    if (points.trim() === "" || !Number.isFinite(value) || value < 0) {
      setPoints(String(item.points));
      return;
    }
    if (value !== item.points) onPoints(item, value);
  };

  return (
    <div className="flex flex-col gap-1 rounded-md border p-2">
      <div className="flex items-start gap-2">
        <span className="font-semibold tabular-nums">{number}.</span>
        <QmdRenderer
          className="min-w-0 flex-1 text-sm"
          source={item.question.stem}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge variant="secondary">
          {t(`review.types.${item.question.type}`)}
        </Badge>
        {item.question.difficulty !== null ? (
          <Badge variant="outline">
            {t("exams.builder.difficulty", { n: item.question.difficulty })}
          </Badge>
        ) : null}
        <label className="flex items-center gap-1">
          {t("exams.builder.points")}
          <Input
            className="h-7 w-20"
            type="number"
            min="0"
            step="0.5"
            aria-label={t("exams.builder.pointsFor", { n: number })}
            value={points}
            onChange={(event) => {
              setPoints(event.target.value);
            }}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === "Enter") commit();
            }}
          />
        </label>
        {!grouped && sections.length > 1 ? (
          <label className="flex items-center gap-1">
            <span className="sr-only">
              {t("exams.builder.moveToSection", { n: number })}
            </span>
            <select
              className="border-input bg-background h-7 rounded-md border px-1"
              aria-label={t("exams.builder.moveToSection", { n: number })}
              value={sectionId}
              onChange={(event) => {
                onMoveSection(item, event.target.value);
              }}
            >
              {sections.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          aria-label={t("exams.builder.removeItem", { n: number })}
          onClick={() => {
            onRemove(item);
          }}
        >
          <Trash2 aria-hidden="true" />
          {t("exams.builder.remove")}
        </Button>
      </div>
    </div>
  );
}
