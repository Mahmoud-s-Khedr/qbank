import { Maximize, MoveHorizontal, ZoomIn, ZoomOut } from "lucide-react";
import {
  type PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

if (
  typeof window !== "undefined" &&
  typeof window.PointerEvent === "undefined"
) {
  class PolyfillPointerEvent extends MouseEvent {
    readonly pointerId: number;
    readonly pointerType: string;

    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
      this.pointerId = params.pointerId ?? 0;
      this.pointerType = params.pointerType ?? "mouse";
    }
  }

  Object.defineProperty(window, "PointerEvent", {
    writable: true,
    configurable: true,
    value: PolyfillPointerEvent,
  });
}

export type Box = [number, number, number, number];

export type RegionKind = "question" | "stimulus" | "figure" | "heading";
export type RegionStatus = "ok" | "warning" | "error" | "approved";
export type PageCanvasMode = "view" | "edit" | "draw";

export interface Region {
  id: string;
  box: Box;
  kind: RegionKind;
  status?: RegionStatus | undefined;
  label?: string | undefined;
}

export interface PageCanvasProps {
  src: string;
  width: number;
  height: number;
  regions: readonly Region[];
  selectedId?: string | undefined;
  onSelect?: ((id: string) => void) | undefined;
  mode?: PageCanvasMode | undefined;
  onChange?: ((id: string, box: Box) => void) | undefined;
  onCreate?: ((box: Box) => void) | undefined;
  className?: string | undefined;
  /** Zoom applied when the page (src) first shows. Default: fit the page width. */
  initialFit?: "none" | "width" | "page" | undefined;
}

export type ResizeHandle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w";

const RESIZE_HANDLES: readonly ResizeHandle[] = [
  "nw",
  "n",
  "ne",
  "e",
  "se",
  "s",
  "sw",
  "w",
];

const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;
const ZOOM_STEP = 0.25;
const NUDGE_STEP = 0.01;
const MIN_DRAW_SIZE = 0.01;

const KIND_COLORS: Record<RegionKind, { stroke: string; fill: string }> = {
  question: { stroke: "#2563eb", fill: "rgba(37, 99, 235, 0.14)" },
  stimulus: { stroke: "#9333ea", fill: "rgba(147, 51, 234, 0.14)" },
  figure: { stroke: "#d97706", fill: "rgba(217, 119, 6, 0.14)" },
  heading: { stroke: "#0d9488", fill: "rgba(13, 148, 136, 0.14)" },
};

const STATUS_STROKE: Partial<Record<RegionStatus, string>> = {
  error: "#dc2626",
  approved: "#16a34a",
};

function round3(value: number): number {
  return Math.round(value * 1000) / 1000;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function normalizeAndClampBox(box: Box): Box {
  const c0 = clamp01(box[0]);
  const c1 = clamp01(box[1]);
  const c2 = clamp01(box[2]);
  const c3 = clamp01(box[3]);
  return [
    round3(Math.min(c0, c2)),
    round3(Math.min(c1, c3)),
    round3(Math.max(c0, c2)),
    round3(Math.max(c1, c3)),
  ];
}

function getHandlePosition(
  handle: ResizeHandle,
  x: number,
  y: number,
  w: number,
  h: number,
): { cx: number; cy: number } {
  switch (handle) {
    case "nw":
      return { cx: x, cy: y };
    case "n":
      return { cx: x + w / 2, cy: y };
    case "ne":
      return { cx: x + w, cy: y };
    case "e":
      return { cx: x + w, cy: y + h / 2 };
    case "se":
      return { cx: x + w, cy: y + h };
    case "s":
      return { cx: x + w / 2, cy: y + h };
    case "sw":
      return { cx: x, cy: y + h };
    case "w":
      return { cx: x, cy: y + h / 2 };
  }
}

function applyResizeDelta(
  initial: Box,
  handle: ResizeHandle,
  dx: number,
  dy: number,
): Box {
  let [x0, y0, x1, y1] = initial;
  if (handle.includes("w")) {
    x0 = clamp01(x0 + dx);
  }
  if (handle.includes("e")) {
    x1 = clamp01(x1 + dx);
  }
  if (handle.includes("n")) {
    y0 = clamp01(y0 + dy);
  }
  if (handle.includes("s")) {
    y1 = clamp01(y1 + dy);
  }
  return [
    Math.min(x0, x1),
    Math.min(y0, y1),
    Math.max(x0, x1),
    Math.max(y0, y1),
  ];
}

type InteractionState =
  | {
      kind: "pan";
      pointerId: number;
      startClientX: number;
      startClientY: number;
      startPanX: number;
      startPanY: number;
    }
  | {
      kind: "move";
      pointerId: number;
      regionId: string;
      initialBox: Box;
      currentBox: Box;
      startClientX: number;
      startClientY: number;
      moved: boolean;
    }
  | {
      kind: "resize";
      pointerId: number;
      regionId: string;
      handle: ResizeHandle;
      initialBox: Box;
      currentBox: Box;
      startClientX: number;
      startClientY: number;
      moved: boolean;
    }
  | {
      kind: "draw";
      pointerId: number;
      startNormX: number;
      startNormY: number;
      currentBox: Box;
    };

export function PageCanvas({
  src,
  width,
  height,
  regions,
  selectedId,
  onSelect,
  mode = "view",
  onChange,
  onCreate,
  className,
  initialFit = "width",
}: PageCanvasProps) {
  const { t } = useTranslation();
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isSpacePressed, setIsSpacePressed] = useState(false);
  const [deselectedPropId, setDeselectedPropId] = useState<string | null>(null);
  const [interaction, setInteraction] = useState<InteractionState | null>(null);

  const viewportRef = useRef<HTMLDivElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const activePointersRef = useRef<Map<number, { x: number; y: number }>>(
    new Map(),
  );
  const pinchDistanceRef = useRef<number | null>(null);
  const suppressClickRef = useRef(false);

  const effectiveSelectedId =
    selectedId && selectedId !== deselectedPropId ? selectedId : undefined;

  const safeWidth = Math.max(1, width);
  const safeHeight = Math.max(1, height);
  const scaledWidth = safeWidth * zoom;
  const scaledHeight = safeHeight * zoom;

  useEffect(() => {
    const handleWindowKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (event.code === "Space") {
        setIsSpacePressed(true);
      }
    };

    const handleWindowKeyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") {
        setIsSpacePressed(false);
      }
    };

    window.addEventListener("keydown", handleWindowKeyDown);
    window.addEventListener("keyup", handleWindowKeyUp);
    return () => {
      window.removeEventListener("keydown", handleWindowKeyDown);
      window.removeEventListener("keyup", handleWindowKeyUp);
    };
  }, []);

  const clampZoom = useCallback((nextZoom: number) => {
    return Math.max(
      MIN_ZOOM,
      Math.min(MAX_ZOOM, Math.round(nextZoom * 100) / 100),
    );
  }, []);

  const handleZoomIn = () => {
    setZoom((prev) => clampZoom(prev + ZOOM_STEP));
  };

  const handleZoomOut = () => {
    setZoom((prev) => clampZoom(prev - ZOOM_STEP));
  };

  const handleFitWidth = () => {
    const viewport = viewportRef.current;
    const vw =
      viewport && viewport.clientWidth > 0 ? viewport.clientWidth : safeWidth;
    setZoom(clampZoom(vw / safeWidth));
    setPan({ x: 0, y: 0 });
  };

  // Fit once per page. Skipped when the viewport has no layout yet (e.g. jsdom), keeping zoom 1.
  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (initialFit === "none" || !viewport || viewport.clientWidth === 0)
      return;
    const byWidth = viewport.clientWidth / safeWidth;
    const byPage = Math.min(byWidth, viewport.clientHeight / safeHeight);
    setZoom(clampZoom(initialFit === "width" ? byWidth : byPage));
    setPan({ x: 0, y: 0 });
  }, [src, initialFit, safeWidth, safeHeight, clampZoom]);

  const handleFitPage = () => {
    const viewport = viewportRef.current;
    const vw =
      viewport && viewport.clientWidth > 0 ? viewport.clientWidth : safeWidth;
    const vh =
      viewport && viewport.clientHeight > 0
        ? viewport.clientHeight
        : safeHeight;
    setZoom(clampZoom(Math.min(vw / safeWidth, vh / safeHeight)));
    setPan({ x: 0, y: 0 });
  };

  const clientToNormalized = useCallback(
    (clientX: number, clientY: number): { nx: number; ny: number } => {
      const rect = svgRef.current?.getBoundingClientRect();
      const effW = rect && rect.width > 0 ? rect.width : scaledWidth;
      const effH = rect && rect.height > 0 ? rect.height : scaledHeight;
      const left = rect ? rect.left : 0;
      const top = rect ? rect.top : 0;
      return {
        nx: clamp01((clientX - left) / effW),
        ny: clamp01((clientY - top) / effH),
      };
    },
    [scaledHeight, scaledWidth],
  );

  const handlePointerDownBackground = (
    event: ReactPointerEvent<SVGSVGElement>,
  ) => {
    activePointersRef.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });

    if (activePointersRef.current.size >= 2) {
      const pts = [...activePointersRef.current.values()];
      const p0 = pts[0];
      const p1 = pts[1];
      if (p0 && p1) {
        pinchDistanceRef.current = Math.hypot(p1.x - p0.x, p1.y - p0.y);
      }
      setInteraction(null);
      return;
    }

    if (isSpacePressed || mode !== "draw") {
      setInteraction({
        kind: "pan",
        pointerId: event.pointerId,
        startClientX: event.clientX,
        startClientY: event.clientY,
        startPanX: pan.x,
        startPanY: pan.y,
      });
      return;
    }

    const { nx, ny } = clientToNormalized(event.clientX, event.clientY);
    setInteraction({
      kind: "draw",
      pointerId: event.pointerId,
      startNormX: nx,
      startNormY: ny,
      currentBox: [nx, ny, nx, ny],
    });
  };

  const handlePointerDownRegion = (
    event: ReactPointerEvent<SVGGElement>,
    region: Region,
  ) => {
    if (isSpacePressed || mode === "draw") {
      return;
    }
    event.stopPropagation();
    activePointersRef.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });

    if (activePointersRef.current.size >= 2) {
      setInteraction(null);
      return;
    }

    setDeselectedPropId(null);

    if (mode === "edit" && effectiveSelectedId === region.id) {
      setInteraction({
        kind: "move",
        pointerId: event.pointerId,
        regionId: region.id,
        initialBox: region.box,
        currentBox: region.box,
        startClientX: event.clientX,
        startClientY: event.clientY,
        moved: false,
      });
    }
  };

  const handlePointerDownHandle = (
    event: ReactPointerEvent<SVGRectElement>,
    region: Region,
    handle: ResizeHandle,
  ) => {
    if (mode !== "edit") {
      return;
    }
    event.stopPropagation();
    activePointersRef.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });

    setInteraction({
      kind: "resize",
      pointerId: event.pointerId,
      regionId: region.id,
      handle,
      initialBox: region.box,
      currentBox: region.box,
      startClientX: event.clientX,
      startClientY: event.clientY,
      moved: false,
    });
  };

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (activePointersRef.current.has(event.pointerId)) {
      activePointersRef.current.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      });
    }

    if (activePointersRef.current.size >= 2) {
      const pts = [...activePointersRef.current.values()];
      const p0 = pts[0];
      const p1 = pts[1];
      if (p0 && p1) {
        const dist = Math.hypot(p1.x - p0.x, p1.y - p0.y);
        const prevDist = pinchDistanceRef.current;
        if (prevDist && prevDist > 0 && dist > 0) {
          const ratio = dist / prevDist;
          setZoom((prev) => clampZoom(prev * ratio));
        }
        pinchDistanceRef.current = dist;
      }
      return;
    }

    if (interaction?.pointerId !== event.pointerId) {
      return;
    }

    if (interaction.kind === "pan") {
      const dx = event.clientX - interaction.startClientX;
      const dy = event.clientY - interaction.startClientY;
      setPan({
        x: interaction.startPanX + dx,
        y: interaction.startPanY + dy,
      });
      return;
    }

    if (interaction.kind === "move") {
      const rawDx = (event.clientX - interaction.startClientX) / scaledWidth;
      const rawDy = (event.clientY - interaction.startClientY) / scaledHeight;
      const [x0, y0, x1, y1] = interaction.initialBox;
      const clampedDx = Math.max(-x0, Math.min(1 - x1, rawDx));
      const clampedDy = Math.max(-y0, Math.min(1 - y1, rawDy));
      const nextBox: Box = [
        x0 + clampedDx,
        y0 + clampedDy,
        x1 + clampedDx,
        y1 + clampedDy,
      ];
      setInteraction({
        ...interaction,
        currentBox: nextBox,
        moved:
          interaction.moved ||
          Math.abs(event.clientX - interaction.startClientX) > 1 ||
          Math.abs(event.clientY - interaction.startClientY) > 1,
      });
      return;
    }

    if (interaction.kind === "resize") {
      const dx = (event.clientX - interaction.startClientX) / scaledWidth;
      const dy = (event.clientY - interaction.startClientY) / scaledHeight;
      const nextBox = applyResizeDelta(
        interaction.initialBox,
        interaction.handle,
        dx,
        dy,
      );
      setInteraction({
        ...interaction,
        currentBox: nextBox,
        moved: true,
      });
      return;
    }

    // interaction.kind === "draw"
    const { nx, ny } = clientToNormalized(event.clientX, event.clientY);
    const nextBox: Box = [
      Math.min(interaction.startNormX, nx),
      Math.min(interaction.startNormY, ny),
      Math.max(interaction.startNormX, nx),
      Math.max(interaction.startNormY, ny),
    ];
    setInteraction({
      ...interaction,
      currentBox: nextBox,
    });
  };

  const finishInteraction = (event: ReactPointerEvent<SVGSVGElement>) => {
    activePointersRef.current.delete(event.pointerId);
    if (activePointersRef.current.size < 2) {
      pinchDistanceRef.current = null;
    }

    if (interaction?.pointerId !== event.pointerId) {
      return;
    }

    if (interaction.kind === "move" && interaction.moved) {
      suppressClickRef.current = true;
      onChange?.(
        interaction.regionId,
        normalizeAndClampBox(interaction.currentBox),
      );
    } else if (interaction.kind === "resize" && interaction.moved) {
      suppressClickRef.current = true;
      onChange?.(
        interaction.regionId,
        normalizeAndClampBox(interaction.currentBox),
      );
    } else if (interaction.kind === "draw") {
      const { nx, ny } = clientToNormalized(event.clientX, event.clientY);
      const rawBox: Box = [
        Math.min(interaction.startNormX, nx),
        Math.min(interaction.startNormY, ny),
        Math.max(interaction.startNormX, nx),
        Math.max(interaction.startNormY, ny),
      ];
      const finalBox = normalizeAndClampBox(rawBox);
      const w = finalBox[2] - finalBox[0];
      const h = finalBox[3] - finalBox[1];
      if (w >= MIN_DRAW_SIZE && h >= MIN_DRAW_SIZE) {
        onCreate?.(finalBox);
      }
    }

    setInteraction(null);
  };

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) {
      return;
    }

    const onWheel = (event: WheelEvent) => {
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
        const delta = event.deltaY < 0 ? 0.1 : -0.1;
        setZoom((prev) => clampZoom(prev + delta));
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (selectedId) {
          setDeselectedPropId(selectedId);
        }
        onSelect?.("");
        return;
      }

      if (!effectiveSelectedId) {
        return;
      }

      const selectedRegion = regions.find((r) => r.id === effectiveSelectedId);
      if (!selectedRegion) {
        return;
      }

      const step = event.shiftKey ? NUDGE_STEP * 10 : NUDGE_STEP;
      let dx = 0;
      let dy = 0;

      if (event.key === "ArrowLeft") {
        dx = -step;
      } else if (event.key === "ArrowRight") {
        dx = step;
      } else if (event.key === "ArrowUp") {
        dy = -step;
      } else if (event.key === "ArrowDown") {
        dy = step;
      } else {
        return;
      }

      event.preventDefault();
      const [x0, y0, x1, y1] = selectedRegion.box;
      const clampedDx = Math.max(-x0, Math.min(1 - x1, dx));
      const clampedDy = Math.max(-y0, Math.min(1 - y1, dy));
      const nextBox = normalizeAndClampBox([
        x0 + clampedDx,
        y0 + clampedDy,
        x1 + clampedDx,
        y1 + clampedDy,
      ]);
      onChange?.(selectedRegion.id, nextBox);
    };

    viewport.addEventListener("wheel", onWheel, { passive: false });
    viewport.addEventListener("keydown", onKeyDown);
    return () => {
      viewport.removeEventListener("wheel", onWheel);
      viewport.removeEventListener("keydown", onKeyDown);
    };
  }, [clampZoom, effectiveSelectedId, onChange, onSelect, regions, selectedId]);

  const zoomPercent = `${String(Math.round(zoom * 100))}%`;

  return (
    <div
      data-testid="page-canvas"
      data-mode={mode}
      className={cn(
        "border-border bg-card flex flex-col overflow-hidden rounded-lg border",
        className,
      )}
    >
      {/* Toolbar follows UI direction (RTL/LTR) */}
      <div
        role="toolbar"
        aria-label={t("pageCanvas.toolbarLabel")}
        className="border-border bg-muted/40 flex flex-wrap items-center gap-1.5 border-b px-3 py-1.5"
      >
        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={t("pageCanvas.zoomOut")}
          data-action="zoom-out"
          onClick={handleZoomOut}
        >
          <ZoomOut className="size-4" aria-hidden="true" />
          <span>−</span>
        </Button>

        <span
          data-testid="page-canvas-zoom"
          dir="ltr"
          className="min-w-14 text-center font-mono text-xs font-medium"
        >
          {zoomPercent}
        </span>

        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={t("pageCanvas.zoomIn")}
          data-action="zoom-in"
          onClick={handleZoomIn}
        >
          <ZoomIn className="size-4" aria-hidden="true" />
          <span>+</span>
        </Button>

        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={t("pageCanvas.fitWidth")}
          data-action="fit-width"
          onClick={handleFitWidth}
        >
          <MoveHorizontal className="size-4" aria-hidden="true" />
          <span className="hidden sm:inline">{t("pageCanvas.fitWidth")}</span>
        </Button>

        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-label={t("pageCanvas.fitPage")}
          data-action="fit-page"
          onClick={handleFitPage}
        >
          <Maximize className="size-4" aria-hidden="true" />
          <span className="hidden sm:inline">{t("pageCanvas.fitPage")}</span>
        </Button>
      </div>

      {/* Physical coordinate viewport — always LTR so coordinates never mirror in RTL */}
      <div
        ref={viewportRef}
        aria-label={t("pageCanvas.overlayLabel")}
        dir="ltr"
        className="bg-muted/20 relative flex-1 overflow-auto p-4 outline-none select-none"
      >
        <div
          data-testid="page-canvas-stage"
          dir="ltr"
          style={{
            width: `${String(scaledWidth)}px`,
            height: `${String(scaledHeight)}px`,
            transform: `translate(${String(pan.x)}px, ${String(pan.y)}px)`,
          }}
          className="relative"
        >
          <img
            src={src}
            alt={t("pageCanvas.pageAlt")}
            width={scaledWidth}
            height={scaledHeight}
            draggable={false}
            style={{
              width: `${String(scaledWidth)}px`,
              height: `${String(scaledHeight)}px`,
            }}
            className="pointer-events-none block select-none"
          />

          <svg
            ref={svgRef}
            data-testid="page-canvas-svg"
            width={scaledWidth}
            height={scaledHeight}
            viewBox={`0 0 ${String(scaledWidth)} ${String(scaledHeight)}`}
            style={{
              direction: "ltr",
              left: 0,
              top: 0,
              width: `${String(scaledWidth)}px`,
              height: `${String(scaledHeight)}px`,
              touchAction: "none",
            }}
            onPointerDown={handlePointerDownBackground}
            onPointerMove={handlePointerMove}
            onPointerUp={finishInteraction}
            onPointerCancel={finishInteraction}
            className={cn(
              "absolute top-0",
              mode === "draw"
                ? "cursor-crosshair"
                : isSpacePressed
                  ? "cursor-grab"
                  : "cursor-default",
            )}
          >
            {regions.map((region) => {
              const isSelected = effectiveSelectedId === region.id;
              const activeBox =
                (interaction?.kind === "move" ||
                  interaction?.kind === "resize") &&
                interaction.regionId === region.id
                  ? interaction.currentBox
                  : region.box;

              const pxX = activeBox[0] * scaledWidth;
              const pxY = activeBox[1] * scaledHeight;
              const pxW = (activeBox[2] - activeBox[0]) * scaledWidth;
              const pxH = (activeBox[3] - activeBox[1]) * scaledHeight;

              const kindStyle = KIND_COLORS[region.kind];
              const status = region.status ?? "ok";
              const strokeColor = STATUS_STROKE[status] ?? kindStyle.stroke;
              const strokeDasharray = status === "warning" ? "6 4" : undefined;
              const strokeWidth = isSelected ? 3 : 1.5;
              const ariaLabel = region.label
                ? `${region.kind} ${region.label}`
                : region.kind;

              return (
                <g
                  key={region.id}
                  role="button"
                  tabIndex={0}
                  aria-label={ariaLabel}
                  aria-pressed={isSelected}
                  data-region-id={region.id}
                  data-kind={region.kind}
                  data-status={status}
                  data-selected={isSelected ? "true" : "false"}
                  onPointerDown={(event) => {
                    handlePointerDownRegion(event, region);
                  }}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (suppressClickRef.current) {
                      suppressClickRef.current = false;
                      return;
                    }
                    setDeselectedPropId(null);
                    onSelect?.(region.id);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      event.stopPropagation();
                      setDeselectedPropId(null);
                      onSelect?.(region.id);
                    }
                  }}
                  className="group cursor-pointer outline-none focus-visible:outline-2 focus-visible:outline-offset-2"
                >
                  <rect
                    data-testid={`region-rect-${region.id}`}
                    x={pxX}
                    y={pxY}
                    width={pxW}
                    height={pxH}
                    fill={kindStyle.fill}
                    stroke={strokeColor}
                    strokeWidth={strokeWidth}
                    strokeDasharray={strokeDasharray}
                  />

                  {/* Visible focus ring */}
                  <rect
                    x={Math.max(0, pxX - 3)}
                    y={Math.max(0, pxY - 3)}
                    width={pxW + 6}
                    height={pxH + 6}
                    fill="none"
                    stroke="#2563eb"
                    strokeWidth={2}
                    strokeDasharray="3 2"
                    className="pointer-events-none opacity-0 group-focus-visible:opacity-100"
                  />

                  {isSelected
                    ? RESIZE_HANDLES.map((handle) => {
                        const { cx, cy } = getHandlePosition(
                          handle,
                          pxX,
                          pxY,
                          pxW,
                          pxH,
                        );
                        const handleSize = 8;
                        return (
                          <rect
                            key={handle}
                            data-testid={`resize-handle-${handle}`}
                            data-handle={handle}
                            x={cx - handleSize / 2}
                            y={cy - handleSize / 2}
                            width={handleSize}
                            height={handleSize}
                            fill="#ffffff"
                            stroke={strokeColor}
                            strokeWidth={2}
                            onPointerDown={(event) => {
                              handlePointerDownHandle(event, region, handle);
                            }}
                          />
                        );
                      })
                    : null}
                </g>
              );
            })}

            {interaction?.kind === "draw" ? (
              <rect
                data-testid="draw-preview-rect"
                x={interaction.currentBox[0] * scaledWidth}
                y={interaction.currentBox[1] * scaledHeight}
                width={
                  (interaction.currentBox[2] - interaction.currentBox[0]) *
                  scaledWidth
                }
                height={
                  (interaction.currentBox[3] - interaction.currentBox[1]) *
                  scaledHeight
                }
                fill="rgba(37, 99, 235, 0.15)"
                stroke="#2563eb"
                strokeWidth={2}
                strokeDasharray="4 4"
                className="pointer-events-none"
              />
            ) : null}
          </svg>
        </div>
      </div>
    </div>
  );
}
