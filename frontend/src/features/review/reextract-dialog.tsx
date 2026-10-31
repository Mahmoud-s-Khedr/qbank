import { Loader2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ApiError } from "@/api/client";
import {
  type AcceptOut,
  type ProposalDetail,
  useAcceptProposal,
  useDiscardProposal,
  useJob,
  useProposal,
  useStartReextract,
} from "@/api/hooks/review";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { REEXTRACT_MODELS } from "./review-model";

function show(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function ReextractDialog({
  open,
  sourceId,
  pageNumber,
  onClose,
}: {
  open: boolean;
  sourceId: string;
  pageNumber: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [model, setModel] = useState("");
  const [jobId, setJobId] = useState<string | undefined>();
  const [selected, setSelected] = useState<Set<string> | null>(null);
  const [result, setResult] = useState<AcceptOut | null>(null);
  const start = useStartReextract();
  const job = useJob(jobId);
  const proposalId =
    job.data?.status === "ready" &&
    typeof job.data.progress.proposal_id === "string"
      ? job.data.progress.proposal_id
      : undefined;
  const proposal = useProposal(proposalId);
  const accept = useAcceptProposal();
  const discard = useDiscardProposal();

  const reset = () => {
    setJobId(undefined);
    setSelected(null);
    setResult(null);
    onClose();
  };

  const begin = async () => {
    try {
      const out = await start.mutateAsync({
        sourceId,
        pageNumber,
        ...(model ? { model } : {}),
      });
      setJobId(out.job_id);
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : t("review.reextract.startFailed"),
      );
    }
  };

  const detail: ProposalDetail | undefined = proposal.data;
  const candidates = detail
    ? [
        ...detail.diff.changed.map((c) => ({
          label: c.number_label,
          skipped: c.status === "approved",
        })),
        ...detail.diff.added.map((a) => ({
          label: a.number_label,
          skipped: false,
        })),
        ...detail.diff.removed.map((r) => ({
          label: r.number_label,
          skipped: r.status === "approved",
        })),
      ]
    : [];
  const effective =
    selected ??
    new Set(candidates.filter((c) => !c.skipped).map((c) => c.label));
  const toggle = (label: string) => {
    const next = new Set(effective);
    if (next.has(label)) next.delete(label);
    else next.add(label);
    setSelected(next);
  };

  const onAccept = async () => {
    if (!proposalId) return;
    try {
      setResult(
        await accept.mutateAsync({
          id: proposalId,
          numberLabels: [...effective],
        }),
      );
    } catch (error) {
      toast.error(
        error instanceof ApiError
          ? error.message
          : t("review.reextract.acceptFailed"),
      );
    }
  };

  const onDiscard = async () => {
    if (proposalId) {
      try {
        await discard.mutateAsync(proposalId);
      } catch {
        // The proposal may already be gone; closing is still right.
      }
    }
    reset();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
      }}
    >
      <DialogContent className="max-w-3xl" data-testid="reextract-dialog">
        <DialogHeader>
          <DialogTitle>
            {t("review.reextract.title", { page: pageNumber })}
          </DialogTitle>
          <DialogDescription>
            {t("review.reextract.description")}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div
            className="flex flex-col gap-2 text-sm"
            data-testid="reextract-result"
          >
            <p>
              {t("review.reextract.applied", { count: result.applied.length })}
            </p>
            {result.skipped.length > 0 ? (
              <ul>
                {result.skipped.map((s) => (
                  <li key={s.number_label}>
                    {t("review.reextract.skippedItem", {
                      label: s.number_label,
                      reason: s.reason,
                    })}
                  </li>
                ))}
              </ul>
            ) : null}
            <DialogFooter>
              <Button type="button" onClick={reset}>
                {t("review.common.close")}
              </Button>
            </DialogFooter>
          </div>
        ) : jobId === undefined ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="reextract-model">
                {t("review.reextract.model")}
              </Label>
              <select
                id="reextract-model"
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={model}
                onChange={(event) => {
                  setModel(event.target.value);
                }}
              >
                <option value="">{t("review.reextract.defaultModel")}</option>
                {REEXTRACT_MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={reset}>
                {t("review.common.cancel")}
              </Button>
              <Button
                type="button"
                disabled={start.isPending}
                onClick={() => {
                  void begin();
                }}
              >
                {t("review.reextract.start")}
              </Button>
            </DialogFooter>
          </div>
        ) : job.data?.status === "failed" ? (
          <div className="flex flex-col gap-3">
            <p role="alert" className="text-destructive text-sm">
              {t("review.reextract.failed", { error: job.data.error ?? "" })}
            </p>
            <DialogFooter>
              <Button type="button" onClick={reset}>
                {t("review.common.close")}
              </Button>
            </DialogFooter>
          </div>
        ) : !detail ? (
          <p
            className="text-muted-foreground flex items-center gap-2 text-sm"
            role="status"
            data-testid="reextract-progress"
          >
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            {t("review.reextract.running")}
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-muted-foreground text-xs">
              {t("review.reextract.summary", {
                model: detail.proposal.model,
                unchanged: detail.diff.unchanged.length,
              })}
            </p>
            <div
              className="max-h-96 overflow-auto"
              data-testid="reextract-diff"
            >
              {detail.diff.changed.map((item) => {
                const skipped = item.status === "approved";
                return (
                  <section
                    key={item.question_id}
                    className="border-border mb-2 rounded-md border p-2"
                  >
                    <label className="flex items-center gap-2 text-sm font-medium">
                      <input
                        type="checkbox"
                        checked={!skipped && effective.has(item.number_label)}
                        disabled={skipped}
                        onChange={() => {
                          toggle(item.number_label);
                        }}
                      />
                      {t("review.reextract.changed", {
                        label: item.number_label,
                      })}
                      {skipped ? (
                        <span className="text-muted-foreground text-xs">
                          ({t("review.reextract.skipped")})
                        </span>
                      ) : null}
                    </label>
                    <table className="mt-1 w-full text-xs">
                      <tbody>
                        {Object.entries(item.fields).map(([field, change]) => (
                          <tr key={field} className="border-t align-top">
                            <td className="p-1 font-medium">{field}</td>
                            <td className="p-1 whitespace-pre-wrap line-through opacity-70">
                              {show(change.before)}
                            </td>
                            <td className="p-1 whitespace-pre-wrap">
                              {show(change.after)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </section>
                );
              })}
              {detail.diff.added.map((item) => (
                <section
                  key={`add-${item.number_label}`}
                  className="mb-2 rounded-md border border-emerald-500/40 p-2"
                >
                  <label className="flex items-center gap-2 text-sm font-medium">
                    <input
                      type="checkbox"
                      checked={effective.has(item.number_label)}
                      onChange={() => {
                        toggle(item.number_label);
                      }}
                    />
                    {t("review.reextract.added", { label: item.number_label })}
                  </label>
                  <p className="text-xs whitespace-pre-wrap">
                    {show(item.question.stem)}
                  </p>
                </section>
              ))}
              {detail.diff.removed.map((item) => {
                const skipped = item.status === "approved";
                return (
                  <section
                    key={`rm-${item.question_id}`}
                    className="border-destructive/40 mb-2 rounded-md border p-2"
                  >
                    <label className="flex items-center gap-2 text-sm font-medium">
                      <input
                        type="checkbox"
                        checked={!skipped && effective.has(item.number_label)}
                        disabled={skipped}
                        onChange={() => {
                          toggle(item.number_label);
                        }}
                      />
                      {t("review.reextract.removed", {
                        label: item.number_label,
                      })}
                      {skipped ? (
                        <span className="text-muted-foreground text-xs">
                          ({t("review.reextract.skipped")})
                        </span>
                      ) : null}
                    </label>
                  </section>
                );
              })}
              {candidates.length === 0 ? (
                <p className="text-muted-foreground text-sm">
                  {t("review.reextract.noChanges")}
                </p>
              ) : null}
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                disabled={discard.isPending}
                onClick={() => {
                  void onDiscard();
                }}
              >
                {t("review.reextract.discard")}
              </Button>
              <Button
                type="button"
                disabled={accept.isPending || effective.size === 0}
                onClick={() => {
                  void onAccept();
                }}
              >
                {t("review.reextract.accept", { count: effective.size })}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
