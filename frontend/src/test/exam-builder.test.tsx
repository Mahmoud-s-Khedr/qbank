import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { setAppLanguage } from "@/i18n";

type Json = Record<string, unknown>;
interface Call {
  method: string;
  path: string;
  query: URLSearchParams;
  body: Json | null;
}
type Handler = (call: Call) => Response | undefined;

const me = {
  id: "u1",
  org_id: "o",
  name: "Teacher",
  email: "t@example.com",
  role: "teacher",
  is_active: true,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
function problem(status: number, code: string, detail = code) {
  return new Response(JSON.stringify({ title: detail, detail, code, status }), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

function question(id: string, stem: string, extra: Json = {}): Json {
  return {
    id,
    stem,
    type: "mcq_single",
    difficulty: 2,
    number_label: id,
    answer: null,
    choices: [
      { label: "A", content: "four" },
      { label: "B", content: "five" },
    ],
    stimulus_id: null,
    stimulus_position: null,
    tags: [],
    status: "approved",
    ...extra,
  };
}
function item(id: string, q: Json, sectionId = "sec1", stimulus?: Json): Json {
  return {
    id,
    origin: "manual",
    points: 1,
    position: 0,
    question: q,
    question_id: q.id,
    section_id: sectionId,
    stimulus: stimulus ?? null,
  };
}
function exam(sections: Json[], extra: Json = {}): Json {
  const items = sections.flatMap((s) => s.items as Json[]);
  return {
    id: "e1",
    owner_id: "u1",
    subject_id: "s1",
    title: "Midterm",
    status: "draft",
    revision: 3,
    blueprint: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    question_count: items.length,
    total_points: items.length,
    sections,
    versions: [],
    settings: {
      language: "en",
      template_id: null,
      header: {
        school_name: "",
        exam_title: "",
        subject_label: "",
        grade: "",
        date: "",
        duration_minutes: null,
        instructions: "",
      },
      layout: {
        columns: 1,
        font_size_pt: 12,
        digits: "western",
        answer_space_lines: 4,
        choices_per_row: "auto",
      },
    },
    ...extra,
  };
}
function section(items: Json[], id = "sec1", title = "Section 1"): Json {
  return { id, title, instructions: null, position: 0, items };
}

const q1 = question("q1", "What is 2+2?");
const q2 = question("q2", "What is 3+3?");
const template = {
  id: "t1",
  name: "School A",
  header: {
    school_name: "Al-Nour School",
    exam_title: "Final",
    subject_label: "Math",
    grade: "5",
    date: "",
    duration_minutes: 60,
    instructions: "",
  },
  logo_asset_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

let calls: Call[] = [];
let overrides: Handler[] = [];

function defaults(call: Call): Response {
  const { path, method } = call;
  if (path === "/api/v1/auth/me") return json(me);
  if (path === "/api/v1/health") return json({ status: "ok" });
  if (path === "/api/v1/subjects")
    return json({
      items: [{ id: "s1", name: "Math", language: "en", grade: null }],
      next_cursor: null,
    });
  if (path === "/api/v1/subjects/s1/tree")
    return json({
      id: "s1",
      name: "Math",
      language: "en",
      chapters: [
        { id: "c1", title: "Algebra", lessons: [{ id: "l1", title: "Sums" }] },
      ],
    });
  if (path === "/api/v1/exam-templates")
    return json({ items: [template], next_cursor: null });
  if (path === "/api/v1/bank/stats")
    return json({
      total: 10,
      by_status: { approved: 8 },
      by_type: {},
      by_difficulty: {},
      approved_by_chapter: [{ id: "c1", title: "Algebra", count: 6 }],
      approved_by_lesson: [],
    });
  if (path === "/api/v1/bank/questions")
    return json({
      items: [
        {
          id: "q1",
          stem_preview: "What is 2+2?",
          type: "mcq_single",
          difficulty: 2,
          chapter_title: "Algebra",
          stimulus_id: null,
        },
      ],
      total: 1,
      next_cursor: null,
      match_mode: "fts",
    });
  const single = /^\/api\/v1\/questions\/(\w+)$/.exec(path);
  if (single && method === "GET") return json(single[1] === "q2" ? q2 : q1);
  if (path === "/api/v1/exams/e1/proposals") return json([]);
  if (path === "/api/v1/exams/e1/exports") return json([]);
  return json({ detail: `unmocked ${method} ${path}` }, 404);
}

function install() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const url = new URL(request.url);
      let body: Json | null = null;
      if (request.method !== "GET" && request.method !== "DELETE") {
        const text = await request.clone().text();
        body = text ? (JSON.parse(text) as Json) : null;
      }
      const call: Call = {
        method: request.method,
        path: url.pathname,
        query: url.searchParams,
        body,
      };
      calls.push(call);
      for (const handler of overrides) {
        const response = handler(call);
        if (response) return response;
      }
      return defaults(call);
    }),
  );
}

function on(handler: Handler) {
  overrides.push(handler);
}
function serveExam(detail: () => Json) {
  on((c) =>
    c.path === "/api/v1/exams/e1" && c.method === "GET"
      ? json(detail())
      : undefined,
  );
}
function find(method: string, path: string) {
  return calls.filter((c) => c.method === method && c.path === path);
}

function setup(path: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={createAppRouter([path])} />
    </AppProviders>,
  );
}

async function openTab(name: string) {
  await userEvent.click(await screen.findByRole("tab", { name }));
}

beforeEach(async () => {
  await setAppLanguage("en");
  calls = [];
  overrides = [];
  install();
});

describe("exam list and creation", () => {
  it("creates an exam and navigates to the builder", async () => {
    const created = exam([section([])]);
    on((c) =>
      c.path === "/api/v1/exams" && c.method === "GET"
        ? json({ items: [], next_cursor: null })
        : undefined,
    );
    on((c) =>
      c.path === "/api/v1/exams" && c.method === "POST"
        ? json(created, 201)
        : undefined,
    );
    serveExam(() => created);
    setup("/exams");
    await userEvent.click(
      await screen.findByRole("button", { name: "New exam" }),
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.type(
      within(dialog).getByLabelText("Exam title"),
      "Midterm",
    );
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Create and open" }),
    );
    await screen.findByRole("tablist");
    expect(screen.getByLabelText("Exam title")).toHaveValue("Midterm");
    const post = find("POST", "/api/v1/exams")[0];
    expect(post?.body).toMatchObject({ subject_id: "s1", title: "Midterm" });
  });
});

describe("exam builder", () => {
  it("adds a question from the bank", async () => {
    let current = exam([section([])]);
    serveExam(() => current);
    on((c) => {
      if (c.path === "/api/v1/exams/e1/items" && c.method === "POST") {
        current = exam([section([item("i1", q1)])]);
        return json(current, 201);
      }
      return undefined;
    });
    setup("/exams/e1");
    const add = await screen.findByRole("button", { name: /Add question/ });
    await userEvent.click(add);
    await waitFor(() => {
      expect(screen.getByText("In exam")).toBeInTheDocument();
    });
    expect(find("POST", "/api/v1/exams/e1/items")[0]?.body).toEqual({
      question_ids: ["q1"],
      points: 1,
      section_id: "sec1",
    });
    expect(
      find("GET", "/api/v1/bank/questions")[0]?.query.get("statuses"),
    ).toBe("approved");
    expect(screen.getByLabelText("Points for question 1")).toHaveValue(1);
  });

  it("removes a stimulus group as one unit after a 409", async () => {
    const stim = { id: "st1", kind: "passage", content: "Read the passage." };
    const g1 = question("q1", "First?", { stimulus_id: "st1" });
    const g2 = question("q2", "Second?", { stimulus_id: "st1" });
    let current = exam([
      section([item("i1", g1, "sec1", stim), item("i2", g2, "sec1", stim)]),
    ]);
    serveExam(() => current);
    on((c) => {
      if (c.path === "/api/v1/exam-items/i1" && c.method === "DELETE") {
        if (c.query.get("group") !== "true")
          return problem(409, "stimulus_group", "group");
        current = exam([section([])]);
        return json(current);
      }
      return undefined;
    });
    setup("/exams/e1");
    expect(await screen.findAllByText("Read the passage.")).toHaveLength(1);
    expect(screen.getByTestId("stimulus-group")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Remove question 1" }),
    );
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Remove the whole group" }),
    );
    await waitFor(() => {
      expect(screen.queryByTestId("stimulus-group")).not.toBeInTheDocument();
    });
    const deletes = find("DELETE", "/api/v1/exam-items/i1");
    expect(deletes.map((d) => d.query.get("group"))).toEqual(["false", "true"]);
  });

  it("reorders with buttons and shows the 422 error, rolling back", async () => {
    const current = exam([section([item("i1", q1), item("i2", q2)])]);
    serveExam(() => current);
    on((c) =>
      c.path === "/api/v1/exams/e1/items/reorder"
        ? problem(422, "stimulus_group", "bad")
        : undefined,
    );
    setup("/exams/e1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Move question 1 down" }),
    );
    expect(await screen.findByText(/must stay together/)).toBeInTheDocument();
    expect(find("POST", "/api/v1/exams/e1/items/reorder")[0]?.body).toEqual({
      section_id: "sec1",
      ids: ["i2", "i1"],
    });
    const stems = screen.getAllByText(/What is \d\+\d\?/);
    expect(stems[0]).toHaveTextContent("2+2");
  });

  it("previews a blueprint and applies it", async () => {
    const current = exam([section([])]);
    serveExam(() => current);
    on((c) =>
      c.path === "/api/v1/exams/e1/blueprint/preview"
        ? json({
            seed: 7,
            rows: [
              { requested: 5, selected: ["q1"], shortfall: 4, available: 1 },
            ],
          })
        : undefined,
    );
    on((c) =>
      c.path === "/api/v1/exams/e1/blueprint/apply"
        ? json(exam([section([item("i1", q1)])]))
        : undefined,
    );
    setup("/exams/e1");
    await openTab("Blueprint");
    await userEvent.click(
      within(screen.getByRole("tabpanel")).getByRole("button", {
        name: "Preview",
      }),
    );
    expect(
      await screen.findByText("Selected 1 of 5 (shortfall 4, available 1)"),
    ).toBeInTheDocument();
    expect(
      find("POST", "/api/v1/exams/e1/blueprint/preview")[0]?.body,
    ).toMatchObject({ rows: [{ count: 5, points: 1 }] });
    await userEvent.click(screen.getByRole("button", { name: "Apply" }));
    const dialog = await screen.findByRole("dialog");
    await userEvent.click(
      within(dialog).getByRole("button", { name: "Apply" }),
    );
    await waitFor(() => {
      expect(find("POST", "/api/v1/exams/e1/blueprint/apply")).toHaveLength(1);
    });
    expect(
      find("POST", "/api/v1/exams/e1/blueprint/apply")[0]?.body,
    ).toMatchObject({ seed: 7 });
  });

  describe("AI assistant", () => {
    const proposal = {
      proposal_id: "p1",
      status: "pending",
      cost_usd: 0.0123,
      rationale: "Balanced coverage",
      warnings: ["Only two matched"],
      blueprint: {
        title: null,
        notes: "",
        sections: [
          {
            title: "Part 1",
            rows: [{ count: 2, points: 1, types: ["mcq_single"] }],
          },
        ],
      },
      selection: [["q1", "q2"]],
    };

    it("shows a proposal, removes a question and applies", async () => {
      serveExam(() => exam([section([])]));
      on((c) =>
        c.path === "/api/v1/exams/e1/compose" ? json(proposal) : undefined,
      );
      on((c) =>
        c.path === "/api/v1/exam-proposals/p1/apply"
          ? json(exam([section([item("i1", q1)])]))
          : undefined,
      );
      setup("/exams/e1");
      await openTab("AI assistant");
      await userEvent.type(
        screen.getByLabelText("Describe the exam you want"),
        "A short math quiz",
      );
      await userEvent.click(screen.getByRole("button", { name: "Compose" }));
      expect(await screen.findByText("Balanced coverage")).toBeInTheDocument();
      expect(screen.getByText("Cost: $0.0123")).toBeInTheDocument();
      expect(screen.getByText("Only two matched")).toBeInTheDocument();
      await userEvent.click(
        await screen.findByRole("button", {
          name: /Remove question: What is 3\+3/,
        }),
      );
      await userEvent.click(screen.getByRole("button", { name: "Apply" }));
      await waitFor(() => {
        expect(find("POST", "/api/v1/exam-proposals/p1/apply")).toHaveLength(1);
      });
      expect(find("POST", "/api/v1/exam-proposals/p1/apply")[0]?.body).toEqual({
        edits: { remove_question_ids: ["q2"] },
      });
      expect(
        await screen.findByText("Proposal applied to the exam."),
      ).toBeInTheDocument();
    });

    it("explains a 402 budget error", async () => {
      serveExam(() => exam([section([])]));
      on((c) =>
        c.path === "/api/v1/exams/e1/compose"
          ? problem(402, "budget_exceeded")
          : undefined,
      );
      setup("/exams/e1");
      await openTab("AI assistant");
      await userEvent.type(
        screen.getByLabelText("Describe the exam you want"),
        "quiz",
      );
      await userEvent.click(screen.getByRole("button", { name: "Compose" }));
      expect(
        await screen.findByText(/monthly AI budget has been reached/),
      ).toBeInTheDocument();
    });

    it("offers a retry after a 502", async () => {
      serveExam(() => exam([section([])]));
      let attempts = 0;
      on((c) => {
        if (c.path !== "/api/v1/exams/e1/compose") return undefined;
        attempts += 1;
        return attempts === 1 ? problem(502, "compose_failed") : json(proposal);
      });
      setup("/exams/e1");
      await openTab("AI assistant");
      await userEvent.type(
        screen.getByLabelText("Describe the exam you want"),
        "quiz",
      );
      await userEvent.click(screen.getByRole("button", { name: "Compose" }));
      await userEvent.click(
        await screen.findByRole("button", { name: "Retry" }),
      );
      expect(await screen.findByText("Balanced coverage")).toBeInTheDocument();
      expect(attempts).toBe(2);
    });
  });

  it("saves settings with a debounce and prefills from a template", async () => {
    const current = exam([section([])]);
    serveExam(() => current);
    on((c) =>
      c.path === "/api/v1/exams/e1" && c.method === "PATCH"
        ? json(exam([section([])], { settings: c.body?.settings }))
        : undefined,
    );
    setup("/exams/e1");
    await openTab("Settings");
    const school = await screen.findByLabelText("School name");
    await userEvent.type(school, "Hi");
    expect(find("PATCH", "/api/v1/exams/e1")).toHaveLength(0);
    await waitFor(
      () => {
        expect(find("PATCH", "/api/v1/exams/e1")).toHaveLength(1);
      },
      { timeout: 3000 },
    );
    const first = find("PATCH", "/api/v1/exams/e1")[0]?.body as {
      settings: { header: { school_name: string } };
    };
    expect(first.settings.header.school_name).toBe("Hi");

    await userEvent.selectOptions(
      await screen.findByLabelText("Header template"),
      "t1",
    );
    expect(screen.getByLabelText("School name")).toHaveValue("Al-Nour School");
    await waitFor(
      () => {
        expect(find("PATCH", "/api/v1/exams/e1")).toHaveLength(2);
      },
      { timeout: 3000 },
    );
    expect(find("PATCH", "/api/v1/exams/e1")[1]?.body).toMatchObject({
      settings: {
        template_id: "t1",
        header: { school_name: "Al-Nour School", duration_minutes: 60 },
      },
    });
  });

  it("generates versions", async () => {
    let versions: Json[] = [];
    serveExam(() => exam([section([item("i1", q1)])], { versions }));
    on((c) => {
      if (c.path === "/api/v1/exams/e1/versions" && c.method === "POST") {
        versions = [
          {
            id: "v1",
            label: "A",
            seed: 1,
            stale: false,
            exam_revision: 3,
            created_at: "2026-01-02T00:00:00Z",
          },
        ];
        return json(versions, 201);
      }
      return undefined;
    });
    setup("/exams/e1?tab=versions");
    await userEvent.click(
      await screen.findByRole("button", { name: "Generate versions" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Answer key" }),
    ).toBeInTheDocument();
    expect(find("POST", "/api/v1/exams/e1/versions")[0]?.body).toMatchObject({
      count: 1,
    });
  });

  it("warns when versions are stale and shows the answer key table", async () => {
    serveExam(() =>
      exam([section([item("i1", q1)])], {
        versions: [
          {
            id: "v1",
            label: "A",
            seed: 1,
            stale: true,
            exam_revision: 1,
            created_at: "2026-01-02T00:00:00Z",
          },
        ],
      }),
    );
    on((c) =>
      c.path === "/api/v1/exams/e1/versions/A/answer-key"
        ? json({
            label: "A",
            warnings: [],
            items: [
              {
                number: 1,
                question_id: "q1",
                type: "mcq_single",
                correct: ["B"],
                answer_text: null,
                points: 1,
              },
            ],
          })
        : undefined,
    );
    setup("/exams/e1?tab=versions");
    expect(
      await screen.findByText(/changed after its versions were generated/),
    ).toBeInTheDocument();
    const table = await screen.findByRole("table", {
      name: "Answer key for version A",
    });
    expect(within(table).getByText("B")).toBeInTheDocument();
    expect(within(table).getByText("What is 2+2?")).toBeInTheDocument();
  });

  it("renders the preview in RTL with Arabic-Indic numbering", async () => {
    const detail = exam([section([item("i1", q1), item("i2", q2)])], {});
    const settings = detail.settings as Json;
    detail.settings = {
      ...settings,
      language: "ar",
      layout: { ...(settings.layout as Json), digits: "arabic" },
    };
    serveExam(() => detail);
    setup("/exams/e1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Preview" }),
    );
    const preview = await screen.findByTestId("exam-preview");
    expect(preview).toHaveAttribute("dir", "rtl");
    expect(within(preview).getByText("١.")).toBeInTheDocument();
    expect(within(preview).getByText("٢.")).toBeInTheDocument();
  });

  it("keeps tabs keyboard accessible with roving focus", async () => {
    serveExam(() => exam([section([])]));
    setup("/exams/e1");
    const bank = await screen.findByRole("tab", { name: "Add from bank" });
    bank.focus();
    await userEvent.keyboard("{End}");
    const versions = screen.getByRole("tab", { name: "Versions & export" });
    expect(versions).toHaveFocus();
    expect(versions).toHaveAttribute("aria-selected", "true");
    expect(bank).toHaveAttribute("tabindex", "-1");
  });
});
