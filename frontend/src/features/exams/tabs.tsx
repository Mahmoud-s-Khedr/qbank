import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabDef {
  id: string;
  label: string;
  panel: ReactNode;
}

/** Accessible tabs with roving tabindex and arrow/Home/End key navigation. */
export function Tabs({
  tabs,
  value,
  onChange,
  label,
  idPrefix,
}: {
  tabs: readonly TabDef[];
  value: string;
  onChange: (id: string) => void;
  label: string;
  idPrefix: string;
}) {
  const refs = useRef(new Map<string, HTMLButtonElement>());

  const onKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    // In RTL the visual order is mirrored, so ArrowRight/Left swap meaning.
    const rtl = getComputedStyle(event.currentTarget).direction === "rtl";
    let next = index;
    if (event.key === "ArrowRight") next = index + (rtl ? -1 : 1);
    else if (event.key === "ArrowLeft") next = index + (rtl ? 1 : -1);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    const target = tabs[(next + tabs.length) % tabs.length];
    if (!target) return;
    onChange(target.id);
    refs.current.get(target.id)?.focus();
  };

  const active = tabs.find((tab) => tab.id === value) ?? tabs[0];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div
        role="tablist"
        aria-label={label}
        className="flex flex-wrap gap-1 border-b"
      >
        {tabs.map((tab, index) => {
          const selected = tab.id === active?.id;
          return (
            <button
              key={tab.id}
              ref={(node) => {
                if (node) refs.current.set(tab.id, node);
                else refs.current.delete(tab.id);
              }}
              type="button"
              role="tab"
              id={`${idPrefix}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => {
                onChange(tab.id);
              }}
              onKeyDown={(event) => {
                onKeyDown(event, index);
              }}
              className={cn(
                "focus-visible:ring-ring -mb-px rounded-t-md border-b-2 px-3 py-2 text-sm font-medium outline-none focus-visible:ring-2",
                selected
                  ? "border-primary text-foreground"
                  : "text-muted-foreground hover:text-foreground border-transparent",
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {active ? (
        <div
          role="tabpanel"
          id={`${idPrefix}-panel-${active.id}`}
          aria-labelledby={`${idPrefix}-tab-${active.id}`}
          tabIndex={0}
          className="min-h-0 flex-1 overflow-y-auto outline-none"
        >
          {active.panel}
        </div>
      ) : null}
    </div>
  );
}
