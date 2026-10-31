import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef, useState } from "react";
import { RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import {
  type Box,
  PageCanvas,
  type Region,
} from "@/components/page-canvas/PageCanvas";
import { QmdEditor } from "@/components/qmd/QmdEditor";
import { QmdRenderer } from "@/components/qmd/QmdRenderer";
import { setAppLanguage } from "@/i18n";

describe("QmdRenderer", () => {
  it("renders inline and display math using KaTeX and supports mhchem \\ce{}", () => {
    const { container } = render(
      <QmdRenderer
        source={
          "المعادلة $x^2 + y^2 = r^2$ وتفاعل الماء $$\\ce{2H2 + O2 -> 2H2O}$$ وصيغة $\\ce{H2O}$."
        }
      />,
    );

    const katexElements = container.querySelectorAll(".katex");
    expect(katexElements.length).toBeGreaterThanOrEqual(3);
    for (const el of katexElements) {
      expect(el).toHaveAttribute("dir", "ltr");
    }

    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(container.textContent).toContain("H2O");
    expect(container.querySelector(".katex-error")).toBeNull();
  });

  it("does not render raw <script> or other raw HTML and restricts links to http(s) with noopener noreferrer", () => {
    const { container } = render(
      <QmdRenderer
        source={
          "نص آمن <script>window.__xss = true;</script> ورابط [آمن](https://example.com) ورابط [خبيث](javascript:alert(1))"
        }
      />,
    );

    expect(container.querySelector("script")).toBeNull();

    const safeLink = screen.getByRole("link", { name: "آمن" });
    expect(safeLink).toHaveAttribute("href", "https://example.com");
    expect(safeLink).toHaveAttribute("rel", "noopener noreferrer");

    expect(screen.queryByRole("link", { name: "خبيث" })).toBeNull();
  });

  it("resolves asset:<uuid> images with lazy loading and renders a visible placeholder when missing", () => {
    const resolveAsset = vi.fn((id: string) =>
      id === "known-uuid" ? "https://cdn.example.com/fig1.png" : undefined,
    );

    render(
      <QmdRenderer
        source={
          "![الشكل الأول](asset:known-uuid)\n\n![الشكل المفقود](asset:missing-uuid)"
        }
        resolveAsset={resolveAsset}
      />,
    );

    expect(resolveAsset).toHaveBeenCalledWith("known-uuid");
    expect(resolveAsset).toHaveBeenCalledWith("missing-uuid");

    const img = screen.getByRole("img", { name: "الشكل الأول" });
    expect(img.tagName).toBe("IMG");
    expect(img).toHaveAttribute("src", "https://cdn.example.com/fig1.png");
    expect(img).toHaveAttribute("loading", "lazy");

    expect(screen.getByText("الصورة غير متاحة")).toBeInTheDocument();
  });

  it("renders 4+ underscores as a styled inline blank with aria-label", () => {
    const { container } = render(
      <QmdRenderer source={"أكمل: عاصمة مصر هي ____ والرمز ______."} />,
    );

    const blanks = container.querySelectorAll("span.qmd-blank");
    expect(blanks).toHaveLength(2);
    for (const blank of blanks) {
      expect(blank).toHaveAttribute("aria-label", "فراغ");
    }
  });

  it("renders standalone ____ line as a blank rather than a horizontal rule", () => {
    const { container } = render(<QmdRenderer source={"____"} />);
    expect(container.querySelector("hr")).toBeNull();
    const blank = container.querySelector("span.qmd-blank");
    expect(blank).not.toBeNull();
    expect(blank).toHaveAttribute("aria-label", "فراغ");
  });

  it("sets dir='auto' on block elements, renders GFM tables, and omits block wrappers in inline mode", () => {
    const { container, rerender } = render(
      <QmdRenderer
        source={
          "# عنوان\n\nفقرة عربية مع English.\n\n| أ | ب |\n| --- | --- |\n| 1 | 2 |"
        }
        lang="ar"
      />,
    );

    const root = screen.getByTestId("qmd-renderer");
    expect(root).toHaveAttribute("dir", "auto");
    expect(root.tagName).toBe("DIV");

    const paragraph = container.querySelector("p");
    expect(paragraph).toHaveAttribute("dir", "auto");

    const table = container.querySelector("table");
    expect(table).toHaveAttribute("dir", "auto");
    expect(container.querySelector("th")).toHaveAttribute("dir", "auto");
    expect(container.querySelector("td")).toHaveAttribute("dir", "auto");

    rerender(<QmdRenderer source="خيار $x + 1$" inline />);
    const inlineRoot = screen.getByTestId("qmd-renderer");
    expect(inlineRoot.tagName).toBe("SPAN");
    expect(inlineRoot).toHaveAttribute("dir", "auto");
    expect(inlineRoot.querySelector("p")).toBeNull();
    expect(inlineRoot.querySelector("div")).toBeNull();
  });

  it("does not throw on a broken TeX string and renders raw TeX in a red-bordered span", () => {
    const { container } = render(
      <QmdRenderer source={"معادلة مكسورة: $\\frac{1 + x}{$ ونص بعدها."} />,
    );

    const errorSpan = container.querySelector(".katex-error");
    expect(errorSpan).not.toBeNull();
    expect(errorSpan?.textContent).toContain("\\frac{1 + x}{");
    expect(errorSpan?.className).toContain("border-red-500");
  });
});

describe("QmdEditor", () => {
  it("inserts the right snippet at the cursor for every toolbar button and fires onChange", async () => {
    const user = userEvent.setup();
    const expectedSnippets: readonly {
      action: string;
      expected: string;
    }[] = [
      { action: "inline-math", expected: "قبل $$ بعد" },
      { action: "display-math", expected: "قبل $$\n\n$$ بعد" },
      { action: "fraction", expected: "قبل \\frac{}{} بعد" },
      { action: "sqrt", expected: "قبل \\sqrt{} بعد" },
      { action: "superscript", expected: "قبل ^{} بعد" },
      { action: "subscript", expected: "قبل _{} بعد" },
      { action: "chemistry", expected: "قبل \\ce{} بعد" },
      { action: "blank", expected: "قبل ____ بعد" },
      {
        action: "table",
        expected:
          "قبل | العمود 1 | العمود 2 |\n| --- | --- |\n| خلية 1 | خلية 2 | بعد",
      },
    ];

    for (const { action, expected } of expectedSnippets) {
      const onChange = vi.fn();
      const { unmount } = render(
        <QmdEditor value="قبل  بعد" onChange={onChange} label="نص السؤال" />,
      );

      const textarea = screen.getByLabelText<HTMLTextAreaElement>("نص السؤال");
      textarea.focus();
      textarea.setSelectionRange(4, 4);

      const toolbar = screen.getByRole("toolbar");
      const button = toolbar.querySelector<HTMLButtonElement>(
        `button[data-toolbar-action="${action}"]`,
      );
      expect(button).not.toBeNull();
      if (button) {
        await user.click(button);
      }

      expect(onChange).toHaveBeenCalledTimes(1);
      expect(onChange).toHaveBeenCalledWith(expected);
      unmount();
    }
  });

  it("supports Ctrl/Cmd+M for inline math and Ctrl/Cmd+Shift+M for display math, plus forwardRef and error display", () => {
    const ref = createRef<HTMLTextAreaElement>();

    function ControlledEditor() {
      const [val, setVal] = useState("سؤال ");
      return (
        <QmdEditor
          ref={ref}
          value={val}
          onChange={setVal}
          label="المحرر"
          error="حقل مطلوب"
        />
      );
    }

    render(<ControlledEditor />);

    expect(ref.current).toBeInstanceOf(HTMLTextAreaElement);
    expect(screen.getByRole("alert")).toHaveTextContent("حقل مطلوب");

    const textarea = screen.getByLabelText<HTMLTextAreaElement>("المحرر");
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    fireEvent.keyDown(textarea, { key: "m", ctrlKey: true });
    expect(textarea.value).toBe("سؤال $$");

    // Put cursor at the end and press Cmd+Shift+M
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    fireEvent.keyDown(textarea, { key: "M", metaKey: true, shiftKey: true });
    expect(textarea.value).toBe("سؤال $$$$\n\n$$");
  });
});

describe("PageCanvas", () => {
  const sampleRegions: Region[] = [
    {
      id: "q1",
      box: [0.1, 0.2, 0.5, 0.6],
      kind: "question",
      status: "ok",
      label: "1",
    },
    {
      id: "fig1",
      box: [0.6, 0.1, 0.9, 0.4],
      kind: "figure",
      status: "warning",
      label: "شكل أ",
    },
  ];

  it("converts normalized boxes to pixel placement at 2 zoom levels", async () => {
    const user = userEvent.setup();
    render(
      <PageCanvas
        src="/fake-page.png"
        width={1000}
        height={2000}
        regions={sampleRegions}
      />,
    );

    expect(screen.getByTestId("page-canvas-zoom")).toHaveTextContent("100%");
    const rectAt100 = screen.getByTestId("region-rect-q1");
    expect(Number(rectAt100.getAttribute("x"))).toBeCloseTo(100);
    expect(Number(rectAt100.getAttribute("y"))).toBeCloseTo(400);
    expect(Number(rectAt100.getAttribute("width"))).toBeCloseTo(400);
    expect(Number(rectAt100.getAttribute("height"))).toBeCloseTo(800);

    // Click zoom in (+) -> 125%
    await user.click(screen.getByRole("button", { name: "تكبير" }));
    expect(screen.getByTestId("page-canvas-zoom")).toHaveTextContent("125%");

    const rectAt125 = screen.getByTestId("region-rect-q1");
    expect(Number(rectAt125.getAttribute("x"))).toBeCloseTo(125);
    expect(Number(rectAt125.getAttribute("y"))).toBeCloseTo(500);
    expect(Number(rectAt125.getAttribute("width"))).toBeCloseTo(500);
    expect(Number(rectAt125.getAttribute("height"))).toBeCloseTo(1000);
  });

  it("calls onSelect when clicking a region or pressing Enter/Space, and deselects on Escape", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <PageCanvas
        src="/fake-page.png"
        width={1000}
        height={1000}
        regions={sampleRegions}
        selectedId="q1"
        onSelect={onSelect}
      />,
    );

    const figButton = screen.getByRole("button", { name: "figure شكل أ" });
    await user.click(figButton);
    expect(onSelect).toHaveBeenCalledWith("fig1");

    onSelect.mockClear();
    figButton.focus();
    fireEvent.keyDown(figButton, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledWith("fig1");

    onSelect.mockClear();
    fireEvent.keyDown(figButton, { key: "Escape" });
    expect(onSelect).toHaveBeenCalledWith("");
  });

  it("nudges the selected region with arrow keys (and Shift = 10x) and clamps to 0–1 with 3 decimals", () => {
    const onChange = vi.fn();
    const edgeRegions: Region[] = [
      {
        id: "edge",
        box: [0.02, 0.03, 0.42, 0.43],
        kind: "question",
        label: "س١",
      },
    ];

    render(
      <PageCanvas
        src="/fake-page.png"
        width={1000}
        height={1000}
        regions={edgeRegions}
        selectedId="edge"
        mode="edit"
        onChange={onChange}
      />,
    );

    const regionBtn = screen.getByRole("button", { name: "question س١" });
    regionBtn.focus();

    // Normal nudge right (+0.01)
    fireEvent.keyDown(regionBtn, { key: "ArrowRight" });
    expect(onChange).toHaveBeenLastCalledWith("edge", [0.03, 0.03, 0.43, 0.43]);

    // Shift + ArrowLeft (-0.1) should clamp x0 at 0 (preserving width 0.4)
    fireEvent.keyDown(regionBtn, { key: "ArrowLeft", shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith("edge", [0, 0.03, 0.4, 0.43]);

    // Shift + ArrowUp (-0.1) should clamp y0 at 0 (preserving height 0.4)
    fireEvent.keyDown(regionBtn, { key: "ArrowUp", shiftKey: true });
    expect(onChange).toHaveBeenLastCalledWith("edge", [0.02, 0, 0.42, 0.4]);
  });

  it("moves and resizes the selected region via pointer events in edit mode", () => {
    const onChange = vi.fn();
    render(
      <PageCanvas
        src="/fake-page.png"
        width={1000}
        height={1000}
        regions={sampleRegions}
        selectedId="q1"
        mode="edit"
        onChange={onChange}
      />,
    );

    const svg = screen.getByTestId("page-canvas-svg");
    const regionBtn = screen.getByRole("button", { name: "question 1" });

    // Drag region by (+100px, +50px) on 1000x1000 -> (+0.1, +0.05)
    fireEvent.pointerDown(regionBtn, {
      pointerId: 1,
      clientX: 200,
      clientY: 300,
    });
    fireEvent.pointerMove(svg, {
      pointerId: 1,
      clientX: 300,
      clientY: 350,
    });
    fireEvent.pointerUp(svg, {
      pointerId: 1,
      clientX: 300,
      clientY: 350,
    });

    expect(onChange).toHaveBeenCalledWith("q1", [0.2, 0.25, 0.6, 0.65]);

    onChange.mockClear();
    const seHandle = screen.getByTestId("resize-handle-se");
    fireEvent.pointerDown(seHandle, {
      pointerId: 2,
      clientX: 500,
      clientY: 600,
    });
    fireEvent.pointerMove(svg, {
      pointerId: 2,
      clientX: 750,
      clientY: 850,
    });
    fireEvent.pointerUp(svg, {
      pointerId: 2,
      clientX: 750,
      clientY: 850,
    });

    expect(onChange).toHaveBeenCalledWith("q1", [0.1, 0.2, 0.75, 0.85]);
  });

  it("creates a box when dragging in draw mode and ignores tiny draws (<1%)", () => {
    const onCreate = vi.fn<(box: Box) => void>();
    render(
      <PageCanvas
        src="/fake-page.png"
        width={1000}
        height={1000}
        regions={[]}
        mode="draw"
        onCreate={onCreate}
      />,
    );

    const svg = screen.getByTestId("page-canvas-svg");

    // Tiny draw: 5px x 5px on 1000x1000 (0.5% < 1%) -> ignored
    fireEvent.pointerDown(svg, { pointerId: 1, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(svg, { pointerId: 1, clientX: 105, clientY: 105 });
    fireEvent.pointerUp(svg, { pointerId: 1, clientX: 105, clientY: 105 });
    expect(onCreate).not.toHaveBeenCalled();

    // Valid draw: (100, 200) -> (450, 700) on 1000x1000 -> [0.1, 0.2, 0.45, 0.7]
    fireEvent.pointerDown(svg, { pointerId: 2, clientX: 100, clientY: 200 });
    fireEvent.pointerMove(svg, { pointerId: 2, clientX: 450, clientY: 700 });
    fireEvent.pointerUp(svg, { pointerId: 2, clientX: 450, clientY: 700 });

    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate).toHaveBeenCalledWith([0.1, 0.2, 0.45, 0.7]);
  });

  it("does not mirror box coordinates when the document direction is RTL vs LTR", async () => {
    await setAppLanguage("ar");
    expect(document.documentElement.dir).toBe("rtl");

    const { unmount } = render(
      <PageCanvas
        src="/fake-page.png"
        width={800}
        height={1200}
        regions={sampleRegions}
      />,
    );

    const rectRtl = screen.getByTestId("region-rect-q1");
    const rtlCoords = {
      x: rectRtl.getAttribute("x"),
      y: rectRtl.getAttribute("y"),
      width: rectRtl.getAttribute("width"),
      height: rectRtl.getAttribute("height"),
    };
    const stageRtl = screen.getByTestId("page-canvas-stage");
    expect(stageRtl).toHaveAttribute("dir", "ltr");
    unmount();

    await setAppLanguage("en");
    expect(document.documentElement.dir).toBe("ltr");

    render(
      <PageCanvas
        src="/fake-page.png"
        width={800}
        height={1200}
        regions={sampleRegions}
      />,
    );

    const rectLtr = screen.getByTestId("region-rect-q1");
    const ltrCoords = {
      x: rectLtr.getAttribute("x"),
      y: rectLtr.getAttribute("y"),
      width: rectLtr.getAttribute("width"),
      height: rectLtr.getAttribute("height"),
    };

    expect(rtlCoords).toEqual(ltrCoords);
  });
});

describe("Dev playground route (/dev/components)", () => {
  it("renders all sample sections in dev mode", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({ status: "ok", version: "0.1.0", db: "ok" }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const router = createAppRouter(["/dev/components"]);
    render(
      <AppProviders>
        <RouterProvider router={router} />
      </AppProviders>,
    );

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "مختبر المكونات المشتركة (T13)",
      }),
    ).toBeInTheDocument();

    const canvas = screen.getByTestId("page-canvas");
    expect(within(canvas).getByTestId("page-canvas-zoom")).toHaveTextContent(
      "100%",
    );
  });
});
