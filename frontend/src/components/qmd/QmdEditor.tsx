import {
  type ChangeEvent,
  type FocusEventHandler,
  forwardRef,
  type KeyboardEvent,
  useCallback,
  useId,
  useRef,
} from "react";
import { useTranslation } from "react-i18next";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

export interface QmdEditorProps {
  value: string;
  onChange: (value: string) => void;
  lang?: "ar" | "en" | undefined;
  resolveAsset?: ((id: string) => string | undefined) | undefined;
  label?: string | undefined;
  error?: string | undefined;
  name?: string | undefined;
  onBlur?: FocusEventHandler<HTMLTextAreaElement> | undefined;
  disabled?: boolean | undefined;
  placeholder?: string | undefined;
  id?: string | undefined;
  rows?: number | undefined;
  className?: string | undefined;
}

export type QmdToolbarActionId =
  | "inline-math"
  | "display-math"
  | "fraction"
  | "sqrt"
  | "superscript"
  | "subscript"
  | "chemistry"
  | "blank"
  | "table";

interface ToolbarItem {
  id: QmdToolbarActionId;
  badge: string;
  labelKey:
    | "qmd.editor.toolbar.inlineMath"
    | "qmd.editor.toolbar.displayMath"
    | "qmd.editor.toolbar.fraction"
    | "qmd.editor.toolbar.sqrt"
    | "qmd.editor.toolbar.superscript"
    | "qmd.editor.toolbar.subscript"
    | "qmd.editor.toolbar.chemistry"
    | "qmd.editor.toolbar.blank"
    | "qmd.editor.toolbar.table";
  tooltipKey:
    | "qmd.editor.toolbar.inlineMathTooltip"
    | "qmd.editor.toolbar.displayMathTooltip"
    | "qmd.editor.toolbar.fractionTooltip"
    | "qmd.editor.toolbar.sqrtTooltip"
    | "qmd.editor.toolbar.superscriptTooltip"
    | "qmd.editor.toolbar.subscriptTooltip"
    | "qmd.editor.toolbar.chemistryTooltip"
    | "qmd.editor.toolbar.blankTooltip"
    | "qmd.editor.toolbar.tableTooltip";
  prefix: string;
  suffix: string;
}

export const QmdEditor = forwardRef<HTMLTextAreaElement, QmdEditorProps>(
  function QmdEditor(
    {
      value,
      onChange,
      lang,
      resolveAsset,
      label,
      error,
      name,
      onBlur,
      disabled = false,
      placeholder,
      id,
      rows = 6,
      className,
    },
    forwardedRef,
  ) {
    const { t } = useTranslation();
    const generatedId = useId();
    const textareaId = id ?? `qmd-editor-${generatedId}`;
    const errorId = `${textareaId}-error`;
    const textareaRef = useRef<HTMLTextAreaElement | null>(null);
    const changeFiredByExecRef = useRef(false);

    const setTextareaRef = useCallback(
      (node: HTMLTextAreaElement | null) => {
        textareaRef.current = node;
        if (typeof forwardedRef === "function") {
          forwardedRef(node);
        } else if (forwardedRef) {
          forwardedRef.current = node;
        }
      },
      [forwardedRef],
    );

    const insertSnippet = useCallback(
      (prefix: string, suffix = "") => {
        if (disabled) {
          return;
        }
        const textarea = textareaRef.current;
        const start = textarea ? textarea.selectionStart : value.length;
        const end = textarea ? textarea.selectionEnd : value.length;
        const selected = value.slice(start, end);
        const inserted = `${prefix}${selected}${suffix}`;
        const nextValue = `${value.slice(0, start)}${inserted}${value.slice(end)}`;
        const nextSelectionStart = start + prefix.length;
        const nextSelectionEnd = nextSelectionStart + selected.length;

        changeFiredByExecRef.current = false;

        if (textarea) {
          textarea.focus();
          textarea.setSelectionRange(start, end);
          // eslint-disable-next-line @typescript-eslint/no-deprecated -- T13 spec requires document.execCommand('insertText') with fallback to preserve undo stack
          if (typeof document.execCommand === "function") {
            try {
              // eslint-disable-next-line @typescript-eslint/no-deprecated -- T13 spec requires document.execCommand('insertText') with fallback to preserve undo stack
              document.execCommand("insertText", false, inserted);
            } catch {
              // Fallback handled below
            }
          }
        }

        const didFireDuringExec = changeFiredByExecRef.current as boolean;
        if (!didFireDuringExec) {
          onChange(nextValue);
        }

        if (textarea) {
          textarea.setSelectionRange(nextSelectionStart, nextSelectionEnd);
        }
      },
      [disabled, onChange, value],
    );

    const handleTextareaChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
      changeFiredByExecRef.current = true;
      onChange(event.target.value);
    };

    const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "m") {
        event.preventDefault();
        if (event.shiftKey) {
          insertSnippet("$$\n", "\n$$");
        } else {
          insertSnippet("$", "$");
        }
      }
    };

    const tableTemplate = `| ${t("qmd.editor.toolbar.tableCol1")} | ${t("qmd.editor.toolbar.tableCol2")} |\n| --- | --- |\n| ${t("qmd.editor.toolbar.tableCell1")} | ${t("qmd.editor.toolbar.tableCell2")} |`;

    const toolbarItems: readonly ToolbarItem[] = [
      {
        id: "inline-math",
        badge: "$…$",
        labelKey: "qmd.editor.toolbar.inlineMath",
        tooltipKey: "qmd.editor.toolbar.inlineMathTooltip",
        prefix: "$",
        suffix: "$",
      },
      {
        id: "display-math",
        badge: "$$…$$",
        labelKey: "qmd.editor.toolbar.displayMath",
        tooltipKey: "qmd.editor.toolbar.displayMathTooltip",
        prefix: "$$\n",
        suffix: "\n$$",
      },
      {
        id: "fraction",
        badge: "a/b",
        labelKey: "qmd.editor.toolbar.fraction",
        tooltipKey: "qmd.editor.toolbar.fractionTooltip",
        prefix: "\\frac{",
        suffix: "}{}",
      },
      {
        id: "sqrt",
        badge: "√",
        labelKey: "qmd.editor.toolbar.sqrt",
        tooltipKey: "qmd.editor.toolbar.sqrtTooltip",
        prefix: "\\sqrt{",
        suffix: "}",
      },
      {
        id: "superscript",
        badge: "x²",
        labelKey: "qmd.editor.toolbar.superscript",
        tooltipKey: "qmd.editor.toolbar.superscriptTooltip",
        prefix: "^{",
        suffix: "}",
      },
      {
        id: "subscript",
        badge: "x₂",
        labelKey: "qmd.editor.toolbar.subscript",
        tooltipKey: "qmd.editor.toolbar.subscriptTooltip",
        prefix: "_{",
        suffix: "}",
      },
      {
        id: "chemistry",
        badge: "\\ce{}",
        labelKey: "qmd.editor.toolbar.chemistry",
        tooltipKey: "qmd.editor.toolbar.chemistryTooltip",
        prefix: "\\ce{",
        suffix: "}",
      },
      {
        id: "blank",
        badge: "____",
        labelKey: "qmd.editor.toolbar.blank",
        tooltipKey: "qmd.editor.toolbar.blankTooltip",
        prefix: "____",
        suffix: "",
      },
      {
        id: "table",
        badge: "⊞",
        labelKey: "qmd.editor.toolbar.table",
        tooltipKey: "qmd.editor.toolbar.tableTooltip",
        prefix: tableTemplate,
        suffix: "",
      },
    ];

    const resolvedLabel = label ?? t("qmd.editor.defaultLabel");

    return (
      <TooltipProvider>
        <div
          data-testid="qmd-editor"
          className={cn("flex flex-col gap-2", className)}
        >
          <Label htmlFor={textareaId}>{resolvedLabel}</Label>

          <div
            role="toolbar"
            aria-label={t("qmd.editor.toolbar.label")}
            className="bg-muted/40 border-border flex flex-wrap items-center gap-1 rounded-md border p-1.5"
          >
            {toolbarItems.map((item) => {
              const itemLabel = t(item.labelKey);
              const itemTooltip = t(item.tooltipKey);
              return (
                <Tooltip key={item.id}>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={disabled}
                      aria-label={itemLabel}
                      data-toolbar-action={item.id}
                      className="h-7 px-2 font-mono text-xs"
                      onClick={() => {
                        insertSnippet(item.prefix, item.suffix);
                      }}
                    >
                      <span dir="ltr">{item.badge}</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{itemTooltip}</TooltipContent>
                </Tooltip>
              );
            })}
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <textarea
              ref={setTextareaRef}
              id={textareaId}
              name={name}
              dir="auto"
              lang={lang}
              rows={rows}
              value={value}
              disabled={disabled}
              placeholder={placeholder}
              onBlur={onBlur}
              onChange={handleTextareaChange}
              onKeyDown={handleKeyDown}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? errorId : undefined}
              className={cn(
                "border-input bg-background placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 font-content min-h-36 w-full rounded-md border p-3 text-base leading-relaxed shadow-xs transition-[color,box-shadow] outline-none focus-visible:ring-[3px] disabled:cursor-not-allowed disabled:opacity-50",
                error && "border-destructive focus-visible:border-destructive",
              )}
            />

            <div className="border-border bg-card flex min-h-36 flex-col rounded-md border p-3">
              <div className="text-muted-foreground mb-2 border-b pb-1.5 text-xs font-medium">
                {t("qmd.editor.preview")}
              </div>
              {value.trim() ? (
                <QmdRenderer
                  source={value}
                  resolveAsset={resolveAsset}
                  lang={lang}
                  className="flex-1 text-base"
                />
              ) : (
                <p className="text-muted-foreground text-sm italic">
                  {t("qmd.editor.emptyPreview")}
                </p>
              )}
            </div>
          </div>

          {error ? (
            <p id={errorId} role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
        </div>
      </TooltipProvider>
    );
  },
);
