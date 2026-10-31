import { QueryClient } from "@tanstack/react-query";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Role, UserOut } from "@/api/hooks/auth";
import type { IssueOut, QuestionOut, StimulusOut } from "@/api/hooks/review";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { setAppLanguage } from "@/i18n";

const SOURCE_ID = "src-1";
const SUBJECT_ID = "11111111-1111-1111-1111-111111111111";
const ASSET_ID = "aaaaaaaa-1111-2222-3333-444444444444";

function user(role: Role = "editor"): UserOut {
  return {
    id: "u1",
    org_id: "org",
    email: "e@x.edu",
    name: "Editor",
    role,
    is_active: true,
    last_login_at: null,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
  };
}

function issue(
  id: string,
  severity: "error" | "warning",
  extra: Partial<IssueOut> = {},
): IssueOut {
  return {
    id,
    code: `code_${id}`,
    severity,
    message: `Issue ${id}`,
    details: {},
    resolved_at: null,
    resolved_by: null,
    created_at: "2026-10-31T10:00:00Z",
    updated_at: "2026-10-31T10:00:00Z",
    ...extra,
  };
}

function question(
  id: string,
  overrides: Partial<QuestionOut> = {},
): QuestionOut {
  return {
    id,
    answer: null,
    chapter_id: null,
    choices: [
      { label: "A", content: "one", is_correct: true, pinned: false },
      { label: "B", content: "two", is_correct: false, pinned: false },
    ],
    confidence: 0.9,
    created_at: "2026-10-31T10:00:00Z",
    difficulty: 2,
    difficulty_reason: "Two steps",
    difficulty_source: "ai",
    duplicate_of_id: null,
    explanation: null,
    issues: [],
    language: "en",
    lesson_id: null,
    number_label: id.toUpperCase(),
    position: 1,
    regions: [{ page: "page-1", box: [0.1, 0.1, 0.9, 0.3] }],
    source_id: SOURCE_ID,
    status: "needs_review",
    stem: `Stem of ${id}`,
    stimulus_id: null,
    stimulus_position: null,
    subject_id: SUBJECT_ID,
    tags: ["algebra"],
    type: "mcq_single",
    updated_at: "2026-10-31T10:00:00Z",
    version: 1,
    ...overrides,
  };
}

interface Call {
  method: string;
  path: string;
  search: string;
  body: unknown;
}

class World {
  questions = new Map<string, QuestionOut>();
  stimuli: StimulusOut[] = [];
  calls: Call[] = [];
  role: Role = "editor";
  extraction: Record<string, unknown> | null = null;
  overrides = new Map<string, (call: Call) => Response | undefined>();

  constructor() {
    const q1 = question("q1", {
      position: 1,
      stem: `Stem of q1\n![](asset:${ASSET_ID})`,
      issues: [
        issue("i1", "error", {
          details: { field: "stem", suggested_fix: "Fixed stem" },
        }),
      ],
    });
    const q2 = question("q2", {
      position: 2,
      issues: [issue("i2", "warning")],
    });
    const q3 = question("q3", {
      position: 3,
      regions: [{ page: "page-2", box: [0.2, 0.2, 0.8, 0.4] }],
    });
    const q4 = question("q4", { position: 4, status: "approved" });
    for (const q of [q1, q2, q3, q4]) this.questions.set(q.id, q);
    this.stimuli = [
      {
        id: "s1",
        content: "Passage",
        created_at: "",
        kind: "passage",
        metadata: {},
        regions: [{ page: "page-1", box: [0.1, 0.5, 0.9, 0.7] }],
        source_id: SOURCE_ID,
        status: "needs_review",
        updated_at: "",
      },
    ];
    this.extraction = {
      headings: [{ text: "Unit 1", box_2d: [10, 10, 60, 500] }],
      questions: [
        {
          number_label: "Q1",
          figures: [{ box_2d: [400, 100, 600, 500], kind: "diagram" }],
        },
      ],
    };
  }

  queue(search: URLSearchParams) {
    const status = search.get("status");
    const severity = search.get("severity");
    const items = [...this.questions.values()]
      .filter((q) => !status || q.status === status)
      .filter(
        (q) =>
          !severity ||
          q.issues.some(
            (i) => i.severity === severity && i.resolved_at === null,
          ),
      )
      .sort((a, b) => a.position - b.position)
      .map((q) => ({
        id: q.id,
        number_label: q.number_label,
        position: q.position,
        page: q.regions[0]?.page === "page-2" ? 2 : 1,
        status: q.status,
        confidence: q.confidence,
        issues: {
          error: q.issues.filter(
            (i) => i.severity === "error" && !i.resolved_at,
          ).length,
          warning: q.issues.filter(
            (i) => i.severity === "warning" && !i.resolved_at,
          ).length,
        },
      }));
    return {
      items,
      totals: {
        count: items.length,
        by_status: {},
        by_severity: {
          error: items.reduce((n, i) => n + i.issues.error, 0),
          warning: items.reduce((n, i) => n + i.issues.warning, 0),
        },
      },
    };
  }

  respond(call: Call): Response {
    const override = this.overrides.get(`${call.method} ${call.path}`);
    const forced = override?.(call);
    if (forced) return forced;
    const { method, path } = call;
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    const search = new URLSearchParams(call.search);
    if (path === "/api/v1/auth/me") return json(user(this.role));
    if (path === "/api/v1/subjects")
      return json({ items: [], next_cursor: null });
    if (path === "/api/v1/sources") {
      return json({
        items: [{ ...sourceOut(), id: SOURCE_ID }],
        next_cursor: null,
      });
    }
    if (path === `/api/v1/sources/${SOURCE_ID}`) {
      return json({ ...sourceOut(), page_counts: {} });
    }
    if (path === `/api/v1/sources/${SOURCE_ID}/pages`) {
      return json([pageOut(1), pageOut(2)]);
    }
    const pageMatch = /\/pages\/(\d+)$/.exec(path);
    if (pageMatch && method === "GET") {
      return json({
        ...pageOut(Number(pageMatch[1])),
        extraction: pageMatch[1] === "1" ? this.extraction : null,
      });
    }
    if (path === `/api/v1/sources/${SOURCE_ID}/review-queue`)
      return json(this.queue(search));
    if (path === `/api/v1/sources/${SOURCE_ID}/questions`) {
      return json([...this.questions.values()]);
    }
    if (path === `/api/v1/sources/${SOURCE_ID}/stimuli`)
      return json(this.stimuli);
    const qMatch = /^\/api\/v1\/questions\/([^/]+)$/.exec(path);
    if (qMatch && method === "GET") {
      const q = this.questions.get(qMatch[1] ?? "");
      return q ? json(q) : json({ detail: "nf", code: "not_found" }, 404);
    }
    if (qMatch && method === "PATCH") {
      const q = this.questions.get(qMatch[1] ?? "");
      if (!q) return json({ code: "not_found" }, 404);
      const body = call.body as Record<string, unknown>;
      const next = { ...q, ...body, version: q.version + 1 } as QuestionOut & {
        version: number;
      };
      this.questions.set(q.id, next);
      return json(next);
    }
    const act = /^\/api\/v1\/questions\/([^/]+)\/(approve|reject|reopen)$/.exec(
      path,
    );
    if (act && method === "POST") {
      const q = this.questions.get(act[1] ?? "");
      if (!q) return json({ code: "not_found" }, 404);
      const status =
        act[2] === "approve"
          ? "approved"
          : act[2] === "reject"
            ? "rejected"
            : "needs_review";
      const next = { ...q, status, version: q.version + 1 };
      this.questions.set(q.id, next);
      return json(next);
    }
    if (path === "/api/v1/questions/bulk") {
      const body = call.body as { ids: string[]; action: string };
      for (const id of body.ids) {
        const q = this.questions.get(id);
        if (q && body.action === "approve")
          this.questions.set(id, { ...q, status: "approved" });
      }
      return json({
        failed: 0,
        succeeded: body.ids.length,
        results: body.ids.map((id) => ({ id, ok: true })),
      });
    }
    return json(
      { detail: `unhandled ${method} ${path}`, code: "unhandled" },
      500,
    );
  }
}

function sourceOut() {
  return {
    id: SOURCE_ID,
    subject_id: SUBJECT_ID,
    title: "Physics workbook",
    grade: null,
    status: "ready",
    stage: "ready",
    page_count: 2,
    cost_usd: 0,
    error: null,
    created_at: "2026-10-31T10:00:00Z",
    updated_at: "2026-10-31T10:00:00Z",
  };
}

function pageOut(n: number) {
  return {
    id: `page-${String(n)}`,
    page_number: n,
    status: "validated",
    page_kind: "questions",
    width_px: 1000,
    height_px: 1000,
    dpi: 150,
    error: null,
    created_at: "2026-10-31T10:00:00Z",
    updated_at: "2026-10-31T10:00:00Z",
  };
}

function must<T>(value: T | undefined): T {
  if (value === undefined) throw new Error("missing fixture");
  return value;
}

let world: World;

function installFetch() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const request =
      input instanceof Request ? input : new Request(String(input), init);
    const url = new URL(request.url);
    let body: unknown = null;
    const text = await request.clone().text();
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    const call: Call = {
      method: request.method,
      path: url.pathname,
      search: url.search,
      body,
    };
    world.calls.push(call);
    return world.respond(call);
  });
}

function callsTo(method: string, pattern: RegExp): Call[] {
  return world.calls.filter((c) => c.method === method && pattern.test(c.path));
}

function renderReview(path = `/sources/${SOURCE_ID}/review`) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const router = createAppRouter([path]);
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router };
}

function pageImageSrc(): string | null {
  return (
    screen
      .getByTestId("page-canvas-stage")
      .querySelector("img")
      ?.getAttribute("src") ?? null
  );
}

async function waitForEditor(label: string) {
  await waitFor(() => {
    expect(screen.getByTestId("editor-title")).toHaveTextContent(label);
  });
}

beforeEach(async () => {
  world = new World();
  installFetch();
  await setAppLanguage("en");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Review workspace", () => {
  it("renders the queue with totals, status chips and issue counts, and filters via the server", async () => {
    const u = userEvent.setup();
    renderReview();
    const list = await screen.findByRole("listbox", { name: "Review queue" });
    const options = within(list).getAllByRole("option");
    expect(options).toHaveLength(4);
    expect(within(must(options[0])).getByText("Q1")).toBeInTheDocument();
    expect(
      within(must(options[0])).getAllByText("Error").length,
    ).toBeGreaterThan(0);
    expect(screen.getByTestId("queue-totals")).toHaveTextContent("4 questions");
    // The first item is selected automatically.
    await waitFor(() => {
      expect(within(list).getAllByRole("option")[0]).toHaveAttribute(
        "aria-selected",
        "true",
      );
    });

    await u.selectOptions(screen.getByLabelText("Status"), "approved");
    await waitFor(() => {
      expect(
        within(screen.getByRole("listbox")).getAllByRole("option"),
      ).toHaveLength(1);
    });
    expect(
      callsTo("GET", /review-queue$/).some((c) =>
        c.search.includes("status=approved"),
      ),
    ).toBe(true);

    await u.selectOptions(screen.getByLabelText("Status"), "");
    await u.selectOptions(screen.getByLabelText("Severity"), "warning");
    await waitFor(() => {
      expect(
        within(screen.getByRole("listbox")).getAllByRole("option"),
      ).toHaveLength(1);
    });
    await u.selectOptions(screen.getByLabelText("Sort"), "confidence");
    await waitFor(() => {
      expect(
        callsTo("GET", /review-queue$/).some((c) =>
          c.search.includes("sort=confidence"),
        ),
      ).toBe(true);
    });
  });

  it("selecting an item loads its page and draws every region on it", async () => {
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    expect(pageImageSrc()).toContain("/pages/1/image");
    // questions, the stimulus, the heading and the figure of Q1 are all drawn.
    expect(
      await screen.findByRole("button", { name: "question Q2" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "stimulus passage" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "heading Unit 1" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "figure Q1.1" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "question Q1" })).toHaveAttribute(
      "data-selected",
      "true",
    );

    await u.click(screen.getByTestId("queue-item-q3"));
    await waitForEditor("Q3");
    await waitFor(() => {
      expect(pageImageSrc()).toContain("/pages/2/image");
    });
    expect(
      screen.queryByRole("button", { name: "question Q2" }),
    ).not.toBeInTheDocument();

    // Clicking a box on the canvas selects that question.
    await u.click(screen.getByTestId("queue-item-q1"));
    await waitForEditor("Q1");
    fireEvent.click(await screen.findByRole("button", { name: "question Q2" }));
    await waitForEditor("Q2");
  });

  it("moves through the queue with J and K", async () => {
    renderReview();
    await waitForEditor("Q1");
    fireEvent.keyDown(window, { key: "j" });
    await waitForEditor("Q2");
    fireEvent.keyDown(window, { key: "ArrowDown" });
    await waitForEditor("Q3");
    fireEvent.keyDown(window, { key: "k" });
    await waitForEditor("Q2");
    fireEvent.keyDown(window, { key: "ArrowUp" });
    await waitForEditor("Q1");
  });

  it("approve (A) sends the version and moves to the next open question", async () => {
    renderReview();
    await waitForEditor("Q1");
    // Q1 has an open error in the fixture; resolve it server-side first.
    world.questions.set("q1", {
      ...must(world.questions.get("q1")),
      issues: [],
    });
    fireEvent.keyDown(window, { key: "j" });
    await waitForEditor("Q2");
    world.questions.set("q2", {
      ...must(world.questions.get("q2")),
      issues: [],
    });
    fireEvent.keyDown(window, { key: "a" });
    await waitFor(() => {
      expect(callsTo("POST", /q2\/approve$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /q2\/approve$/)[0]?.body).toEqual({
      force: false,
      version: 1,
    });
    await waitForEditor("Q3");
  });

  it("shows the unresolved_errors message and offers force only to admins", async () => {
    world.overrides.set("POST /api/v1/questions/q1/approve", (call) => {
      const body = call.body as { force: boolean };
      if (body.force) return undefined;
      return new Response(
        JSON.stringify({
          code: "unresolved_errors",
          detail: "Resolve the 1 error issue first",
          issues: ["code_i1"],
        }),
        {
          status: 422,
          headers: { "Content-Type": "application/problem+json" },
        },
      );
    });
    world.role = "admin";
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    await u.click(screen.getByTestId("approve-button"));
    const dialog = await screen.findByTestId("approve-blocked-dialog");
    expect(screen.getByTestId("approve-blocked-message")).toHaveTextContent(
      "Resolve the 1 error issue first",
    );
    expect(within(dialog).getByText(/Issue i1/)).toBeInTheDocument();
    await u.click(
      within(dialog).getByRole("button", { name: "Force approve" }),
    );
    await waitFor(() => {
      expect(callsTo("POST", /q1\/approve$/).at(-1)?.body).toMatchObject({
        force: true,
      });
    });
  });

  it("hides force approve from editors", async () => {
    world.overrides.set(
      "POST /api/v1/questions/q1/approve",
      () =>
        new Response(
          JSON.stringify({ code: "unresolved_errors", detail: "Blocked" }),
          {
            status: 422,
            headers: { "Content-Type": "application/problem+json" },
          },
        ),
    );
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    await u.click(screen.getByTestId("approve-button"));
    const dialog = await screen.findByTestId("approve-blocked-dialog");
    expect(
      within(dialog).queryByRole("button", { name: "Force approve" }),
    ).not.toBeInTheDocument();
  });

  it("opens the conflict dialog on 409 version_conflict and can overwrite with the new version", async () => {
    let first = true;
    world.overrides.set("PATCH /api/v1/questions/q1", () => {
      if (!first) return undefined;
      first = false;
      const current = {
        ...must(world.questions.get("q1")),
        stem: "Server stem",
        version: 5,
      };
      return new Response(
        JSON.stringify({
          code: "version_conflict",
          detail: "version conflict",
          current,
        }),
        {
          status: 409,
          headers: { "Content-Type": "application/problem+json" },
        },
      );
    });
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    const stem = screen.getByLabelText("Question text");
    await u.clear(stem);
    await u.type(stem, "My stem");
    await u.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByTestId("conflict-dialog");
    expect(
      within(dialog).getByTestId("conflict-server-stem"),
    ).toHaveTextContent("Server stem");
    expect(within(dialog).getByTestId("conflict-mine-stem")).toHaveTextContent(
      "My stem",
    );
    await u.click(
      within(dialog).getByRole("button", { name: "Overwrite with my edits" }),
    );
    await waitFor(() => {
      expect(callsTo("PATCH", /q1$/)).toHaveLength(2);
    });
    expect(callsTo("PATCH", /q1$/)[1]?.body).toMatchObject({
      version: 5,
      stem: "My stem",
    });
    await waitFor(() => {
      expect(screen.queryByTestId("conflict-dialog")).not.toBeInTheDocument();
    });
  });

  it("draws a figure box and posts it, then re-crops it and cache-busts the image", async () => {
    world.overrides.set("POST /api/v1/questions/q2/figures", () => {
      const q = must(world.questions.get("q2"));
      world.questions.set("q2", {
        ...q,
        stem: `${q.stem}\n![](asset:bbbbbbbb-1111-2222-3333-444444444444)`,
        version: 2,
      });
      return new Response(
        JSON.stringify({
          id: "bbbbbbbb-1111-2222-3333-444444444444",
          created_at: "",
          height: 10,
          width: 10,
          kind: "figure",
          pipeline_generated: false,
          region: [0.1, 0.2, 0.45, 0.7],
          source_page_id: "page-1",
          updated_at: "2026-10-31T12:00:00Z",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    });
    world.overrides.set(
      `PUT /api/v1/assets/${ASSET_ID}/region`,
      (call) =>
        new Response(
          JSON.stringify({
            id: ASSET_ID,
            created_at: "",
            height: 10,
            width: 10,
            kind: "figure",
            pipeline_generated: true,
            region: (call.body as { box: number[] }).box,
            source_page_id: "page-1",
            updated_at: "2026-10-31T13:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");

    // Re-crop: select the figure box (edit mode) and nudge it.
    const thumb = await screen.findByTestId(`figure-thumb-${ASSET_ID}`);
    expect(thumb.getAttribute("src")).not.toContain("?v=");
    const figure = await screen.findByRole("button", { name: "figure Q1.1" });
    fireEvent.click(figure);
    await waitFor(() => {
      expect(screen.getByTestId("page-canvas")).toHaveAttribute(
        "data-mode",
        "edit",
      );
    });
    fireEvent.keyDown(screen.getByRole("button", { name: "figure Q1.1" }), {
      key: "ArrowRight",
    });
    await waitFor(() => {
      expect(callsTo("PUT", /\/assets\/.+\/region$/)).toHaveLength(1);
    });
    expect(callsTo("PUT", /region$/)[0]?.body).toEqual({
      box: [0.11, 0.4, 0.51, 0.6],
    });
    await waitFor(() => {
      expect(
        screen.getByTestId(`figure-thumb-${ASSET_ID}`).getAttribute("src"),
      ).toContain(`/assets/${ASSET_ID}/image?v=`);
    });

    // Add figure on Q2: draw mode, then drag on the canvas.
    await u.click(screen.getByTestId("queue-item-q2"));
    await waitForEditor("Q2");
    await u.click(
      screen.getByRole("button", { name: "Add figure", pressed: false }),
    );
    expect(screen.getByTestId("page-canvas")).toHaveAttribute(
      "data-mode",
      "draw",
    );
    const svg = screen.getByTestId("page-canvas-svg");
    fireEvent.pointerDown(svg, { pointerId: 1, clientX: 100, clientY: 200 });
    fireEvent.pointerMove(svg, { pointerId: 1, clientX: 450, clientY: 700 });
    fireEvent.pointerUp(svg, { pointerId: 1, clientX: 450, clientY: 700 });
    await waitFor(() => {
      expect(callsTo("POST", /q2\/figures$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /q2\/figures$/)[0]?.body).toEqual({
      page_id: "page-1",
      box: [0.1, 0.2, 0.45, 0.7],
    });
  });

  it("splits at the cursor and at a choice, and merges with the next question after confirming", async () => {
    world.overrides.set("POST /api/v1/questions/q1/split", () => {
      const q = must(world.questions.get("q1"));
      return new Response(
        JSON.stringify({ first: q, second: question("q1b", { position: 2 }) }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    world.overrides.set(
      "POST /api/v1/questions/merge",
      () =>
        new Response(JSON.stringify(world.questions.get("q1")), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    const stem = screen.getByLabelText<HTMLTextAreaElement>("Question text");
    stem.focus();
    stem.setSelectionRange(4, 4);
    await u.click(screen.getByRole("button", { name: "Split at cursor" }));
    await waitFor(() => {
      expect(callsTo("POST", /q1\/split$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /q1\/split$/)[0]?.body).toEqual({
      at: { field: "stem", offset: 4 },
    });

    await u.click(
      screen.getByRole("button", { name: "Split before choice 2" }),
    );
    await waitFor(() => {
      expect(callsTo("POST", /q1\/split$/)).toHaveLength(2);
    });
    expect(callsTo("POST", /q1\/split$/)[1]?.body).toEqual({
      at: { choice_index: 1 },
    });

    await u.click(screen.getByRole("button", { name: "Merge with next" }));
    const dialog = await screen.findByTestId("merge-dialog");
    expect(within(dialog).getByText("Q1")).toBeInTheDocument();
    expect(within(dialog).getByText("Q2")).toBeInTheDocument();
    await u.click(within(dialog).getByRole("button", { name: "Merge" }));
    await waitFor(() => {
      expect(callsTo("POST", /questions\/merge$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /questions\/merge$/)[0]?.body).toEqual({
      ids: ["q1", "q2"],
    });
  });

  it("re-extracts a page, shows the diff, skips approved questions and accepts the selection", async () => {
    world.overrides.set(
      "POST /api/v1/sources/src-1/pages/1/reextract",
      () =>
        new Response(JSON.stringify({ job_id: "job-1" }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        }),
    );
    world.overrides.set(
      "GET /api/v1/jobs/job-1",
      () =>
        new Response(
          JSON.stringify({
            id: "job-1",
            kind: "reextract",
            status: "ready",
            error: null,
            progress: { proposal_id: "prop-1" },
            ref_id: SOURCE_ID,
            created_at: "",
            updated_at: "",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    const proposal = {
      id: "prop-1",
      cost_usd: 0,
      created_at: "",
      created_by: null,
      extraction: {},
      model: "openai/gpt-6-luna",
      page_id: "page-1",
      page_number: 1,
      source_id: SOURCE_ID,
      status: "pending",
      updated_at: "",
    };
    world.overrides.set(
      "GET /api/v1/page-proposals/prop-1",
      () =>
        new Response(
          JSON.stringify({
            proposal,
            diff: {
              changed: [
                {
                  question_id: "q1",
                  number_label: "Q1",
                  status: "needs_review",
                  fields: { stem: { before: "old stem", after: "new stem" } },
                },
                {
                  question_id: "q4",
                  number_label: "Q4",
                  status: "approved",
                  fields: { stem: { before: "a", after: "b" } },
                },
              ],
              added: [{ number_label: "Q9", question: { stem: "brand new" } }],
              removed: [],
              unchanged: ["Q2"],
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    world.overrides.set(
      "POST /api/v1/page-proposals/prop-1/accept",
      () =>
        new Response(
          JSON.stringify({
            proposal,
            applied: ["Q1"],
            skipped: [{ number_label: "Q4", reason: "approved" }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    await u.click(screen.getByRole("button", { name: "Re-extract page" }));
    const dialog = await screen.findByTestId("reextract-dialog");
    expect(
      within(dialog).getByRole("option", { name: "openai/gpt-6-luna" }),
    ).toBeInTheDocument();
    await u.click(within(dialog).getByRole("button", { name: "Start" }));
    const diff = await within(dialog).findByTestId(
      "reextract-diff",
      undefined,
      { timeout: 4000 },
    );
    expect(within(diff).getByText("old stem")).toBeInTheDocument();
    expect(within(diff).getByText("new stem")).toBeInTheDocument();
    expect(within(diff).getByText(/approved, skipped/)).toBeInTheDocument();
    const boxes = within(diff).getAllByRole("checkbox");
    expect(boxes).toHaveLength(3);
    expect(boxes[1]).toBeDisabled();
    // Untick the new question, keep Q1.
    await u.click(must(boxes[2]));
    await u.click(
      within(dialog).getByRole("button", { name: /Accept selected/ }),
    );
    await waitFor(() => {
      expect(callsTo("POST", /prop-1\/accept$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /prop-1\/accept$/)[0]?.body).toEqual({
      number_labels: ["Q1"],
    });
    expect(
      await within(dialog).findByTestId("reextract-result"),
    ).toHaveTextContent("Q4 skipped");
  });

  it("bulk approves a Shift-click range from the queue", async () => {
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    await u.click(screen.getByRole("checkbox", { name: "Select Q1" }));
    await u.keyboard("{Shift>}");
    await u.click(screen.getByRole("checkbox", { name: "Select Q3" }));
    await u.keyboard("{/Shift}");
    expect(screen.getByTestId("bulk-bar")).toHaveTextContent("3 selected");
    await u.click(
      within(screen.getByTestId("bulk-bar")).getByRole("button", {
        name: "Approve",
      }),
    );
    await waitFor(() => {
      expect(callsTo("POST", /questions\/bulk$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /questions\/bulk$/)[0]?.body).toEqual({
      action: "approve",
      ids: ["q1", "q2", "q3"],
    });
  });

  it("ignores single-key shortcuts while typing in a field but still saves with Ctrl+S", async () => {
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    const number = screen.getByLabelText("Number");
    await u.click(number);
    await u.keyboard("ja");
    expect(callsTo("POST", /approve$/)).toHaveLength(0);
    expect(screen.getByTestId("editor-title")).toHaveTextContent("Q1");
    expect(number).toHaveValue("Q1ja");
    await u.keyboard("{Control>}s{/Control}");
    await waitFor(() => {
      expect(callsTo("PATCH", /q1$/)).toHaveLength(1);
    });
    expect(callsTo("PATCH", /q1$/)[0]?.body).toMatchObject({
      number_label: "Q1ja",
      version: 1,
    });
  });

  it("shows the shortcut help on ? and rejects with a reason on R", async () => {
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    fireEvent.keyDown(window, { key: "?" });
    expect(await screen.findByTestId("shortcuts-dialog")).toBeInTheDocument();
    await u.keyboard("{Escape}");
    await waitFor(() => {
      expect(screen.queryByTestId("shortcuts-dialog")).not.toBeInTheDocument();
    });
    fireEvent.keyDown(window, { key: "r" });
    const dialog = await screen.findByTestId("reject-dialog");
    await u.type(within(dialog).getByLabelText(/Reason/), "blurry");
    await u.click(within(dialog).getByRole("button", { name: "Reject" }));
    await waitFor(() => {
      expect(callsTo("POST", /q1\/reject$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /q1\/reject$/)[0]?.body).toEqual({
      reason: "blurry",
      version: 1,
    });
  });

  it("applies a verifier's suggested fix by patching the field", async () => {
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    await u.click(
      await screen.findByRole("button", { name: /Apply fix to Question text/ }),
    );
    await waitFor(() => {
      expect(callsTo("PATCH", /q1$/)).toHaveLength(1);
    });
    expect(callsTo("PATCH", /q1$/)[0]?.body).toEqual({
      version: 1,
      stem: "Fixed stem",
    });
  });
});

describe("Review workspace extras", () => {
  it("windows a 1,000 item queue instead of rendering every row", async () => {
    world.overrides.set("GET /api/v1/sources/src-1/review-queue", () => {
      const items = Array.from({ length: 1000 }, (_, i) => ({
        id: i === 0 ? "q1" : `bulk-${String(i)}`,
        number_label: `N${String(i)}`,
        position: i,
        page: 1,
        status: "needs_review",
        confidence: 0.5,
        issues: { error: 0, warning: 0 },
      }));
      return new Response(
        JSON.stringify({
          items,
          totals: {
            count: 1000,
            by_status: {},
            by_severity: { error: 0, warning: 0 },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    });
    renderReview();
    const list = await screen.findByRole("listbox", { name: "Review queue" });
    await waitFor(() => {
      expect(within(list).getAllByRole("option").length).toBeGreaterThan(0);
    });
    expect(within(list).getAllByRole("option").length).toBeLessThan(60);
    expect(screen.getByTestId("queue-totals")).toHaveTextContent(
      "1000 questions",
    );
  });

  it("creates a missed question from a drawn region, then attaches its page region", async () => {
    world.overrides.set(
      "POST /api/v1/sources/src-1/pages/1/extract-region",
      () =>
        new Response(
          JSON.stringify({
            number_label: "Q9",
            type: "mcq_single",
            stem: "Recovered stem",
            choices: [{ label: "A", content: "yes" }],
            answer: { labels: ["A"], text: null },
            box_2d: [0, 0, 1, 1],
            confidence: 0.8,
            continues_from_previous: false,
            continues_on_next: false,
            figures: [],
            stimulus_ref: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    );
    world.overrides.set("POST /api/v1/questions", () => {
      const created = question("q9", {
        position: 9,
        version: 1,
        stem: "Recovered stem",
        regions: [],
      });
      world.questions.set("q9", created);
      return new Response(JSON.stringify(created), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    });
    const u = userEvent.setup();
    renderReview();
    await waitForEditor("Q1");
    await u.click(screen.getByRole("button", { name: "Add missed question" }));
    const svg = screen.getByTestId("page-canvas-svg");
    fireEvent.pointerDown(svg, { pointerId: 1, clientX: 100, clientY: 200 });
    fireEvent.pointerMove(svg, { pointerId: 1, clientX: 450, clientY: 700 });
    fireEvent.pointerUp(svg, { pointerId: 1, clientX: 450, clientY: 700 });
    const dialog = await screen.findByTestId("missed-dialog");
    expect(within(dialog).getByLabelText("Question text")).toHaveValue(
      "Recovered stem",
    );
    await u.click(
      within(dialog).getByRole("button", { name: "Save question" }),
    );
    await waitFor(() => {
      expect(callsTo("POST", /\/questions$/)).toHaveLength(1);
    });
    expect(callsTo("POST", /\/questions$/)[0]?.body).toMatchObject({
      subject_id: SUBJECT_ID,
      type: "mcq_single",
      stem: "Recovered stem",
      number_label: "Q9",
    });
    await waitFor(() => {
      expect(callsTo("PATCH", /q9$/)).toHaveLength(1);
    });
    expect(callsTo("PATCH", /q9$/)[0]?.body).toEqual({
      version: 1,
      regions: [{ page: "page-1", box: [0.1, 0.2, 0.45, 0.7] }],
    });
    await waitForEditor("Q9");
  });

  it("renders the workspace in Arabic with RTL direction and unmirrored boxes", async () => {
    await setAppLanguage("ar");
    renderReview();
    await waitForEditor("Q1");
    expect(document.documentElement.dir).toBe("rtl");
    expect(
      screen.getByRole("listbox", { name: "قائمة المراجعة" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "القائمة" }),
    ).toBeInTheDocument();
    const rect = await screen.findByTestId("region-rect-q:q2");
    expect(rect).toHaveAttribute("x", "100");
  });
});

describe("Review list page", () => {
  it("lists sources with questions awaiting review", async () => {
    renderReview("/review");
    const list = await screen.findByTestId("review-sources");
    expect(within(list).getByText("Physics workbook")).toBeInTheDocument();
    expect(within(list).getByRole("link", { name: "Review" })).toHaveAttribute(
      "href",
      `/sources/${SOURCE_ID}/review`,
    );
  });
});
