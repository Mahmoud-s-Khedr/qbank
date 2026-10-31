import { AlertCircle, AlertTriangle } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import type { IssueOut, QuestionOut } from "@/api/hooks/review";
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
import { conflictingFields, type Draft } from "./review-model";

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  destructive = false,
  pending = false,
  onConfirm,
  onClose,
  children,
  testId,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onClose: () => void;
  children?: ReactNode;
  testId?: string;
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent data-testid={testId}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {children}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("review.common.cancel")}
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            disabled={pending}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ReasonDialog({
  open,
  onConfirm,
  onClose,
}: {
  open: boolean;
  onConfirm: (reason: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent data-testid="reject-dialog">
        <DialogHeader>
          <DialogTitle>{t("review.reject.title")}</DialogTitle>
          <DialogDescription>
            {t("review.reject.description")}
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            onConfirm(reason.trim());
            setReason("");
          }}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="reject-reason">{t("review.reject.reason")}</Label>
            <Input
              id="reject-reason"
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
              }}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("review.common.cancel")}
            </Button>
            <Button type="submit" variant="destructive">
              {t("review.reject.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ApproveBlockedDialog({
  open,
  message,
  issues,
  isAdmin,
  pending,
  onForce,
  onClose,
}: {
  open: boolean;
  message: string;
  issues: readonly IssueOut[];
  isAdmin: boolean;
  pending: boolean;
  onForce: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent data-testid="approve-blocked-dialog">
        <DialogHeader>
          <DialogTitle>{t("review.approveBlocked.title")}</DialogTitle>
          <DialogDescription data-testid="approve-blocked-message">
            {message}
          </DialogDescription>
        </DialogHeader>
        <ul className="flex max-h-60 flex-col gap-2 overflow-auto text-sm">
          {issues.map((issue) => (
            <li key={issue.id} className="flex items-start gap-2">
              <AlertCircle
                className="text-destructive mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <span>
                <span className="font-medium">
                  {t("review.severity.error")}:{" "}
                </span>
                {issue.message}
              </span>
            </li>
          ))}
        </ul>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            {t("review.common.close")}
          </Button>
          {isAdmin ? (
            <Button
              type="button"
              variant="destructive"
              disabled={pending}
              onClick={onForce}
            >
              {t("review.approveBlocked.force")}
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function ConflictDialog({
  current,
  draft,
  onReload,
  onOverwrite,
  onClose,
}: {
  current: QuestionOut | null;
  draft: Draft;
  onReload: () => void;
  onOverwrite: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const rows = current ? conflictingFields(current, draft) : [];
  return (
    <Dialog
      open={current !== null}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent data-testid="conflict-dialog" className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("review.conflict.title")}</DialogTitle>
          <DialogDescription>
            {t("review.conflict.description")}
          </DialogDescription>
        </DialogHeader>
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-muted-foreground text-start">
                <th className="p-2 text-start">{t("review.conflict.field")}</th>
                <th className="p-2 text-start">
                  {t("review.conflict.server")}
                </th>
                <th className="p-2 text-start">{t("review.conflict.mine")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.field} className="border-t align-top">
                  <td className="p-2 font-medium">
                    {t(`review.fields.${row.field}`)}
                  </td>
                  <td
                    className="p-2 whitespace-pre-wrap"
                    data-testid={`conflict-server-${row.field}`}
                  >
                    {row.theirs}
                  </td>
                  <td
                    className="p-2 whitespace-pre-wrap"
                    data-testid={`conflict-mine-${row.field}`}
                  >
                    {row.mine}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onReload}>
            {t("review.conflict.reload")}
          </Button>
          <Button type="button" onClick={onOverwrite}>
            {t("review.conflict.overwrite")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const SHORTCUTS: readonly [string, string][] = [
  ["J / ↓", "review.shortcuts.next"],
  ["K / ↑", "review.shortcuts.prev"],
  ["A", "review.shortcuts.approve"],
  ["R", "review.shortcuts.reject"],
  ["E", "review.shortcuts.edit"],
  ["Ctrl/⌘ + S", "review.shortcuts.save"],
  ["F", "review.shortcuts.figure"],
  ["Esc", "review.shortcuts.cancel"],
  ["?", "review.shortcuts.help"],
];

export function ShortcutsDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent data-testid="shortcuts-dialog">
        <DialogHeader>
          <DialogTitle>{t("review.shortcuts.title")}</DialogTitle>
          <DialogDescription>
            {t("review.shortcuts.description")}
          </DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
          {SHORTCUTS.map(([keys, labelKey]) => (
            <div key={keys} className="contents">
              <dt>
                <kbd
                  className="bg-muted rounded border px-1.5 py-0.5 font-mono text-xs"
                  dir="ltr"
                >
                  {keys}
                </kbd>
              </dt>
              <dd>{t(labelKey)}</dd>
            </div>
          ))}
        </dl>
      </DialogContent>
    </Dialog>
  );
}

export function SeverityIcon({ severity }: { severity: string }) {
  return severity === "error" ? (
    <AlertCircle
      className="text-destructive size-4 shrink-0"
      aria-hidden="true"
    />
  ) : (
    <AlertTriangle
      className="size-4 shrink-0 text-amber-600 dark:text-amber-400"
      aria-hidden="true"
    />
  );
}

export function BulkMetadataDialog({
  open,
  count,
  pending,
  onConfirm,
  onClose,
}: {
  open: boolean;
  count: number;
  pending: boolean;
  onConfirm: (metadata: {
    difficulty?: number;
    tags_add: string[];
    tags_remove: string[];
  }) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [difficulty, setDifficulty] = useState("");
  const [add, setAdd] = useState("");
  const [remove, setRemove] = useState("");
  const split = (value: string) =>
    value
      .split(/[,،]/)
      .map((tag) => tag.trim())
      .filter(Boolean);
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent data-testid="bulk-metadata-dialog">
        <DialogHeader>
          <DialogTitle>{t("review.bulk.metadataTitle")}</DialogTitle>
          <DialogDescription>
            {t("review.bulk.metadataDescription", { count })}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="bulk-difficulty">
              {t("review.fields.difficulty")}
            </Label>
            <select
              id="bulk-difficulty"
              className="border-input bg-background h-9 rounded-md border px-2 text-sm"
              value={difficulty}
              onChange={(event) => {
                setDifficulty(event.target.value);
              }}
            >
              <option value="">{t("review.bulk.keepAsIs")}</option>
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={String(n)}>
                  {n}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="bulk-tags-add">{t("review.bulk.tagsAdd")}</Label>
            <Input
              id="bulk-tags-add"
              value={add}
              onChange={(event) => {
                setAdd(event.target.value);
              }}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="bulk-tags-remove">
              {t("review.bulk.tagsRemove")}
            </Label>
            <Input
              id="bulk-tags-remove"
              value={remove}
              onChange={(event) => {
                setRemove(event.target.value);
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
            disabled={pending}
            onClick={() => {
              onConfirm({
                ...(difficulty ? { difficulty: Number(difficulty) } : {}),
                tags_add: split(add),
                tags_remove: split(remove),
              });
            }}
          >
            {t("review.bulk.apply")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
