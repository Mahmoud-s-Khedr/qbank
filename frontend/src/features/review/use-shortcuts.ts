import { useEffect, useRef } from "react";

export interface ShortcutHandlers {
  next: () => void;
  prev: () => void;
  approve: () => void;
  reject: () => void;
  edit: () => void;
  save: () => void;
  figure: () => void;
  cancel: () => void;
  help: () => void;
}

export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

/**
 * Window-level review shortcuts. Plain keys are ignored while typing in a field
 * and while `disabled` (a dialog is open); Ctrl/Cmd+S works everywhere.
 */
export function useReviewShortcuts(
  handlers: ShortcutHandlers,
  disabled: boolean,
): void {
  const ref = useRef(handlers);
  useEffect(() => {
    ref.current = handlers;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (disabled) return;
      const h = ref.current;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        h.save();
        return;
      }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "Escape") {
        h.cancel();
        return;
      }
      if (isTypingTarget(event.target)) return;
      const inRegion =
        event.target instanceof HTMLElement &&
        event.target.closest("[data-region-id]") !== null;
      switch (event.key) {
        case "j":
        case "J":
          event.preventDefault();
          h.next();
          break;
        case "k":
        case "K":
          event.preventDefault();
          h.prev();
          break;
        case "ArrowDown":
          if (!inRegion) {
            event.preventDefault();
            h.next();
          }
          break;
        case "ArrowUp":
          if (!inRegion) {
            event.preventDefault();
            h.prev();
          }
          break;
        case "a":
        case "A":
          event.preventDefault();
          h.approve();
          break;
        case "r":
        case "R":
          event.preventDefault();
          h.reject();
          break;
        case "e":
        case "E":
          event.preventDefault();
          h.edit();
          break;
        case "f":
        case "F":
          event.preventDefault();
          h.figure();
          break;
        case "?":
          event.preventDefault();
          h.help();
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [disabled]);
}
