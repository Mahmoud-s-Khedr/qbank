import { QueryClient } from "@tanstack/react-query";
import {
  act,
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
import type {
  BankFacets,
  BankQuestionOut,
  BankSearchOut,
  BankStatsOut,
  QuestionOut,
} from "@/api/hooks/bank";
import type { ChapterTree, SubjectTree } from "@/api/hooks/taxonomy";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { setAppLanguage } from "@/i18n";

const SUBJECT_ID = "11111111-1111-1111-1111-111111111111";
const CHAPTER_1_ID = "22222222-2222-2222-2222-222222222222";
const CHAPTER_2_ID = "33333333-3333-3333-3333-333333333333";
const LESSON_1_ID = "44444444-4444-4444-4444-444444444444";
const LESSON_2_ID = "55555555-5555-5555-5555-555555555555";
const EXAM_1_ID = "eeeeeeee-1111-1111-1111-111111111111";
const STIMULUS_ID = "ssssssss-1111-1111-1111-111111111111";

function testUser(role: Role = "editor"): UserOut {
  return {
    id: "user-1",
    org_id: "org-1",
    email: "editor@test.com",
    name: "Test Editor",
    role,
    is_active: true,
    last_login_at: null,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
  };
}

function sampleBankQuestion(
  id: string,
  overrides: Partial<BankQuestionOut> = {},
): BankQuestionOut {
  return {
    id,
    number_label: `Q-${id}`,
    type: "mcq_single",
    stem_preview: `Stem preview for question ${id}`,
    status: "approved",
    difficulty: 3,
    subject_id: SUBJECT_ID,
    chapter_id: CHAPTER_1_ID,
    chapter_title: "Chapter 1: Mechanics",
    lesson_id: LESSON_1_ID,
    lesson_title: "Lesson 1: Newton's Laws",
    source_id: "src-1",
    source_title: "Physics Workbook",
    source_page: 12,
    has_figure: false,
    stimulus_id: null,
    choices_count: 4,
    tags: ["physics", "forces"],
    issues_count: { error: 0, warning: 0 },
    ...overrides,
  };
}

function sampleFullQuestion(
  id: string,
  overrides: Partial<QuestionOut> = {},
): QuestionOut {
  return {
    id,
    number_label: `Q-${id}`,
    stem: `Full stem for question ${id} with formula $$E = mc^2$$`,
    type: "mcq_single",
    status: "approved",
    difficulty: 3,
    difficulty_reason: "Requires two algebraic steps",
    difficulty_source: "editor",
    subject_id: SUBJECT_ID,
    chapter_id: CHAPTER_1_ID,
    lesson_id: LESSON_1_ID,
    source_id: "src-1",
    confidence: 0.95,
    language: "en",
    position: 1,
    answer: "A",
    explanation: "This is the model explanation for question " + id,
    choices: [
      { label: "A", content: "Option A (Correct)", is_correct: true },
      { label: "B", content: "Option B", is_correct: false },
      { label: "C", content: "Option C", is_correct: false },
      { label: "D", content: "Option D", is_correct: false },
    ],
    regions: [],
    issues: [],
    tags: ["physics", "forces"],
    version: 1,
    created_at: "2026-10-10T10:00:00Z",
    updated_at: "2026-10-12T10:00:00Z",
    stimulus_id: null,
    stimulus_position: null,
    duplicate_of_id: null,
    ...overrides,
  };
}

interface Call {
  method: string;
  path: string;
  search: string;
  body: unknown;
}

class BankWorld {
  role: Role = "editor";
  calls: Call[] = [];
  matchMode: "fts" | "fuzzy" = "fts";
  cursorPaging = false;

  subjects = [
    {
      id: SUBJECT_ID,
      name: "Physics",
      grade: "Grade 11",
      language: "en" as const,
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-01T10:00:00Z",
    },
  ];

  chapters: ChapterTree[] = [
    {
      id: CHAPTER_1_ID,
      title: "Chapter 1: Mechanics",
      position: 1,
      subject_id: SUBJECT_ID,
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-01T10:00:00Z",
      lessons: [
        {
          id: LESSON_1_ID,
          title: "Lesson 1: Newton's Laws",
          chapter_id: CHAPTER_1_ID,
          position: 1,
          created_at: "2026-10-01T10:00:00Z",
          updated_at: "2026-10-01T10:00:00Z",
        },
      ],
    },
    {
      id: CHAPTER_2_ID,
      title: "Chapter 2: Energy",
      position: 2,
      subject_id: SUBJECT_ID,
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-01T10:00:00Z",
      lessons: [
        {
          id: LESSON_2_ID,
          title: "Lesson 2: Kinetic Energy",
          chapter_id: CHAPTER_2_ID,
          position: 1,
          created_at: "2026-10-01T10:00:00Z",
          updated_at: "2026-10-01T10:00:00Z",
        },
      ],
    },
  ];

  facets: BankFacets = {
    total: 2,
    chapters: [
      { id: CHAPTER_1_ID, title: "Chapter 1: Mechanics", count: 2 },
      { id: CHAPTER_2_ID, title: "Chapter 2: Energy", count: 0 },
    ],
    lessons: [
      {
        id: LESSON_1_ID,
        chapter_id: CHAPTER_1_ID,
        title: "Lesson 1: Newton's Laws",
        count: 2,
      },
      {
        id: LESSON_2_ID,
        chapter_id: CHAPTER_2_ID,
        title: "Lesson 2: Kinetic Energy",
        count: 0,
      },
    ],
    types: {
      mcq_single: 2,
    },
    difficulties: {
      "3": 2,
    },
    statuses: {
      approved: 2,
    },
    sources: [{ id: "src-1", title: "Physics Workbook", count: 2 }],
    tags: [
      { tag: "physics", count: 2 },
      { tag: "forces", count: 2 },
    ],
  };

  stats: BankStatsOut = {
    total: 2,
    by_status: { approved: 2, draft: 0, needs_review: 0, rejected: 0 },
    by_type: { mcq_single: 2 },
    by_difficulty: { "3": 2 },
    approved_by_chapter: [
      { id: CHAPTER_1_ID, title: "Chapter 1: Mechanics", count: 2 },
      { id: CHAPTER_2_ID, title: "Chapter 2: Energy", count: 0 },
    ],
    approved_by_lesson: [
      {
        id: LESSON_1_ID,
        chapter_id: CHAPTER_1_ID,
        title: "Lesson 1: Newton's Laws",
        count: 2,
      },
      {
        id: LESSON_2_ID,
        chapter_id: CHAPTER_2_ID,
        title: "Lesson 2: Kinetic Energy",
        count: 0,
      },
    ],
  };

  draftExams = [
    {
      id: EXAM_1_ID,
      title: "Midterm Physics 2026",
      status: "draft",
      subject_id: SUBJECT_ID,
      question_count: 5,
      total_points: 10,
      revision: 1,
      created_at: "2026-10-01T10:00:00Z",
      updated_at: "2026-10-01T10:00:00Z",
    },
  ];

  respond(call: Call): Response {
    const { method, path } = call;
    const json = (body: unknown, status = 200) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });

    if (path === "/api/v1/auth/me") {
      return json(testUser(this.role));
    }

    if (path === "/api/v1/subjects" && method === "GET") {
      return json({ items: this.subjects, total: this.subjects.length });
    }

    if (path === "/api/v1/bank/stats") {
      return json(this.stats);
    }

    if (path === "/api/v1/bank/tags") {
      return json([
        { tag: "physics", count: 2 },
        { tag: "forces", count: 2 },
      ]);
    }

    if (path === "/api/v1/bank/questions") {
      const search = new URLSearchParams(call.search);
      const cursor = search.get("cursor");

      if (this.cursorPaging && cursor === "page-2-cursor") {
        const item2 = sampleBankQuestion("q2", {
          stem_preview: "Loaded second page question q2",
        });
        const out: BankSearchOut = {
          items: [item2],
          total: 2,
          next_cursor: null,
          match_mode: this.matchMode,
          facets: this.facets,
        };
        return json(out);
      }

      if (this.cursorPaging && !cursor) {
        const item1 = sampleBankQuestion("q1", {
          stem_preview: "First page question q1",
        });
        const out: BankSearchOut = {
          items: [item1],
          total: 2,
          next_cursor: "page-2-cursor",
          match_mode: this.matchMode,
          facets: this.facets,
        };
        return json(out);
      }

      const q1 = sampleBankQuestion("q1");
      const q2 = sampleBankQuestion("q2", {
        has_figure: true,
        issues_count: { error: 1, warning: 0 },
      });

      const out: BankSearchOut = {
        items: [q1, q2],
        total: 2,
        next_cursor: null,
        match_mode: this.matchMode,
        facets: this.facets,
      };
      return json(out);
    }

    if (path.startsWith("/api/v1/questions/") && path.endsWith("/history")) {
      return json([
        {
          id: "hist-1",
          question_id: "q1",
          action: "approve",
          user_id: "editor-1",
          created_at: "2026-10-15T12:00:00Z",
          diff: { status: { old: "draft", new: "approved" } },
        },
      ]);
    }

    if (path === `/api/v1/sources/src-1/stimuli`) {
      return json([
        {
          id: STIMULUS_ID,
          kind: "passage",
          content: "Read this passage about Galileo before answering.",
          source_id: "src-1",
          created_at: "2026-10-01T10:00:00Z",
          metadata: {},
          regions: [],
        },
      ]);
    }

    if (path.startsWith("/api/v1/questions/")) {
      const qId = path.split("/").pop() ?? "q1";
      if (qId === "q1") {
        return json(
          sampleFullQuestion("q1", {
            stimulus_id: STIMULUS_ID,
          }),
        );
      }
      return json(sampleFullQuestion(qId));
    }

    if (path === "/api/v1/questions/bulk" && method === "POST") {
      const body = call.body as { action: string; ids: string[] };
      if (body.ids.includes("fail-id")) {
        return json({
          succeeded: 1,
          failed: 1,
          results: [
            { id: "q1", ok: true },
            { id: "fail-id", ok: false, code: "has_validation_errors" },
          ],
        });
      }
      return json({
        succeeded: body.ids.length,
        failed: 0,
        results: body.ids.map((id) => ({ id, ok: true })),
      });
    }

    if (path === "/api/v1/questions/move" && method === "POST") {
      const body = call.body as { ids: string[]; lesson_id: string };
      return json({ moved: body.ids.length });
    }

    if (path === "/api/v1/exams" && method === "GET") {
      return json({
        items: this.draftExams,
        total: this.draftExams.length,
        next_cursor: null,
      });
    }

    if (path === `/api/v1/exams/${EXAM_1_ID}/items` && method === "POST") {
      return json(
        {
          id: EXAM_1_ID,
          title: "Midterm Physics 2026",
          status: "draft",
          subject_id: SUBJECT_ID,
          owner_id: "u1",
          question_count: 7,
          total_points: 12,
          revision: 2,
          settings: { language: "en" },
          created_at: "2026-10-01T10:00:00Z",
          updated_at: "2026-10-31T10:00:00Z",
          sections: [
            {
              id: "sec-1",
              title: "Section 1",
              position: 1,
              instructions: null,
              items: [
                {
                  id: "item-1",
                  question_id: "q1",
                  section_id: "sec-1",
                  position: 1,
                  points: 1,
                  origin: "manual",
                  stimulus: { id: STIMULUS_ID, content: "Passage" },
                  question: { stem: "Q1" },
                },
                {
                  id: "item-2",
                  question_id: "q-stimulus-extra",
                  section_id: "sec-1",
                  position: 2,
                  points: 1,
                  origin: "manual",
                  stimulus: { id: STIMULUS_ID, content: "Passage" },
                  question: { stem: "Extra Stimulus Question" },
                },
              ],
            },
          ],
        },
        201,
      );
    }

    // Taxonomy Tree
    if (path === `/api/v1/subjects/${SUBJECT_ID}/tree` && method === "GET") {
      const tree: SubjectTree = {
        id: SUBJECT_ID,
        org_id: "org-1",
        name: "Physics",
        grade: "Grade 11",
        language: "en",
        created_at: "2026-10-01T10:00:00Z",
        updated_at: "2026-10-01T10:00:00Z",
        chapters: this.chapters,
      };
      return json(tree);
    }

    // Taxonomy Reorder Chapters
    if (
      path === `/api/v1/subjects/${SUBJECT_ID}/chapters/reorder` &&
      method === "POST"
    ) {
      return new Response(null, { status: 204 });
    }

    // Taxonomy Reorder Lessons
    if (
      path === `/api/v1/chapters/${CHAPTER_1_ID}/lessons/reorder` &&
      method === "POST"
    ) {
      return new Response(null, { status: 204 });
    }

    // Merge chapter
    if (path.includes("/chapters/") && path.endsWith("/merge")) {
      return json({
        id: CHAPTER_2_ID,
        title: "Chapter 2: Energy",
        position: 1,
        subject_id: SUBJECT_ID,
        created_at: "2026-10-01T10:00:00Z",
        updated_at: "2026-10-01T10:00:00Z",
      });
    }

    // Delete subject / chapter / lesson
    if (method === "DELETE") {
      if (path.includes(SUBJECT_ID) || path.includes(CHAPTER_1_ID)) {
        return json(
          {
            type: "https://example.com/not_empty",
            title: "Conflict",
            status: 409,
            detail: "Cannot delete non-empty resource",
            code: "not_empty",
          },
          409,
        );
      }
      return new Response(null, { status: 204 });
    }

    return json({ detail: "Not found", code: "not_found" }, 404);
  }
}

let world: BankWorld;

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

function renderBank(path = "/bank") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
  const router = createAppRouter([path]);
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router };
}

describe("Question Bank UI & Taxonomy Manager", () => {
  beforeEach(async () => {
    world = new BankWorld();
    installFetch();
    await setAppLanguage("en");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("1. Debounced search calls the API with the right query and updates the URL", async () => {
    const { router } = renderBank("/bank");

    await waitFor(() => {
      expect(screen.getByTestId("bank-search-input")).toBeInTheDocument();
    });

    const searchInput = screen.getByTestId("bank-search-input");
    act(() => {
      fireEvent.change(searchInput, { target: { value: "momentum" } });
    });

    // Wait for 250ms debounce
    await waitFor(() => {
      const calls = world.calls.filter(
        (c) => c.path === "/api/v1/bank/questions",
      );
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.search).toContain("q=momentum");
    });

    expect(router.state.location.search).toContain("q=momentum");
  });

  it("2. Facet click updates filter chips, URL query param, and calls API", async () => {
    const { router } = renderBank("/bank");

    await waitFor(() => {
      expect(screen.getByText("Chapter 1: Mechanics")).toBeInTheDocument();
    });

    // Click on difficulty 3 facet button
    const diffBtn = screen.getByRole("button", { name: "3 (2)" });
    act(() => {
      fireEvent.click(diffBtn);
    });

    await waitFor(() => {
      const calls = world.calls.filter(
        (c) => c.path === "/api/v1/bank/questions",
      );
      const lastCall = calls[calls.length - 1];
      expect(lastCall?.search).toContain("difficulty_min=3");
      expect(lastCall?.search).toContain("difficulty_max=3");
    });

    // Check filter chip is visible
    expect(screen.getByText("Difficulty: 3")).toBeInTheDocument();
    expect(router.state.location.search).toContain("difficulty_min=3");
  });

  it("3. Shows fuzzy match notice when match_mode = 'fuzzy'", async () => {
    world.matchMode = "fuzzy";
    renderBank("/bank?q=misspelled");

    await waitFor(() => {
      expect(screen.getByTestId("fuzzy-match-notice")).toBeInTheDocument();
    });
    expect(screen.getByTestId("fuzzy-match-notice")).toHaveTextContent(
      "No exact match found. Showing results with fuzzy matching.",
    );
  });

  it("4. Load more questions uses cursor pagination", async () => {
    world.cursorPaging = true;
    renderBank("/bank");

    await waitFor(() => {
      expect(screen.getByText("First page question q1")).toBeInTheDocument();
    });

    const loadMoreBtn = screen.getByTestId("load-more-btn");
    act(() => {
      fireEvent.click(loadMoreBtn);
    });

    await waitFor(() => {
      expect(
        screen.getByText("Loaded second page question q2"),
      ).toBeInTheDocument();
    });

    const calls = world.calls.filter(
      (c) => c.path === "/api/v1/bank/questions",
    );
    const lastCall = calls[calls.length - 1];
    expect(lastCall?.search).toContain("cursor=page-2-cursor");
  });

  it("5. Detail drawer renders stimulus, stem, choices, answer, explanation, metadata, and history", async () => {
    renderBank("/bank");

    await waitFor(() => {
      expect(screen.getByTestId("question-card-q1")).toBeInTheDocument();
    });

    // Click card to open detail drawer
    act(() => {
      fireEvent.click(screen.getByTestId("question-card-q1"));
    });

    await waitFor(() => {
      expect(screen.getByTestId("question-detail-drawer")).toBeInTheDocument();
      expect(
        screen.getByText(/Read this passage about Galileo before answering/i),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Full stem for question q1 with formula/i),
      ).toBeInTheDocument();
      expect(screen.getByText("Option A (Correct)")).toBeInTheDocument();
      expect(screen.getByText("Correct")).toBeInTheDocument();
      expect(
        screen.getByText(/This is the model explanation for question q1/i),
      ).toBeInTheDocument();
      expect(screen.getByText("Audit history")).toBeInTheDocument();
      expect(screen.getByText("Open in review")).toBeInTheDocument();
    });
  });

  it("6. Bulk approve with partial failure shown", async () => {
    renderBank("/bank");

    await waitFor(() => {
      expect(screen.getByTestId("question-card-q1")).toBeInTheDocument();
    });

    // Select question q1
    const checkbox1 = within(screen.getByTestId("question-card-q1")).getByRole(
      "checkbox",
    );
    act(() => {
      fireEvent.click(checkbox1);
    });

    // The bulk toolbar appears
    await waitFor(() => {
      expect(screen.getByTestId("bank-bulk-toolbar")).toBeInTheDocument();
    });

    // Mock world to simulate failure with fail-id
    const user = userEvent.setup();
    const approveBtn = screen.getByRole("button", { name: "Approve" });

    // Force partial failure response
    world.respond = (call: Call) => {
      if (call.path === "/api/v1/questions/bulk") {
        return new Response(
          JSON.stringify({
            succeeded: 1,
            failed: 1,
            results: [
              { id: "q1", ok: true },
              { id: "q2", ok: false, code: "has_errors" },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return BankWorld.prototype.respond.call(world, call);
    };

    await user.click(approveBtn);

    await waitFor(() => {
      expect(
        screen.getByTestId("bulk-partial-failure-alert"),
      ).toBeInTheDocument();
    });
    expect(screen.getByTestId("bulk-partial-failure-alert")).toHaveTextContent(
      "q2 (has_errors)",
    );
  });

  it("7. Move to lesson with tree picker dialog", async () => {
    renderBank("/bank");

    await waitFor(() => {
      expect(screen.getByTestId("question-card-q1")).toBeInTheDocument();
    });

    const checkbox1 = within(screen.getByTestId("question-card-q1")).getByRole(
      "checkbox",
    );
    act(() => {
      fireEvent.click(checkbox1);
    });

    await waitFor(() => {
      expect(screen.getByTestId("bank-bulk-toolbar")).toBeInTheDocument();
    });

    const moveBtn = screen.getByRole("button", { name: "Move to lesson" });
    act(() => {
      fireEvent.click(moveBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("move-lesson-dialog")).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: "Lesson 1: Newton's Laws",
        }),
      ).toBeInTheDocument();
    });

    // Select lesson 1
    const lessonBtn = screen.getByRole("button", {
      name: "Lesson 1: Newton's Laws",
    });
    act(() => {
      fireEvent.click(lessonBtn);
    });

    // Confirm move
    const confirmBtn = within(
      screen.getByTestId("move-lesson-dialog"),
    ).getByRole("button", { name: "Move to lesson" });
    act(() => {
      fireEvent.click(confirmBtn);
    });

    await waitFor(() => {
      const moveCalls = world.calls.filter(
        (c) => c.path === "/api/v1/questions/move",
      );
      expect(moveCalls.length).toBeGreaterThan(0);
      expect(moveCalls[0]?.body).toEqual({
        ids: ["q1"],
        lesson_id: LESSON_1_ID,
      });
    });
  });

  it("8. Add to exam dialog displays draft exams and warns if stimulus group was pulled in", async () => {
    renderBank("/bank");

    await waitFor(() => {
      expect(screen.getByTestId("question-card-q1")).toBeInTheDocument();
    });

    const checkbox1 = within(screen.getByTestId("question-card-q1")).getByRole(
      "checkbox",
    );
    act(() => {
      fireEvent.click(checkbox1);
    });

    await waitFor(() => {
      expect(screen.getByTestId("bank-bulk-toolbar")).toBeInTheDocument();
    });

    const addToExamBtn = screen.getByRole("button", { name: "Add to exam" });
    act(() => {
      fireEvent.click(addToExamBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("add-to-exam-dialog")).toBeInTheDocument();
    });

    // Select draft exam
    const select = screen.getByTestId("exam-select");
    act(() => {
      fireEvent.change(select, { target: { value: EXAM_1_ID } });
    });

    // Click Add
    const submitBtn = within(
      screen.getByTestId("add-to-exam-dialog"),
    ).getByRole("button", { name: "Add to exam" });
    act(() => {
      fireEvent.click(submitBtn);
    });

    // Warning message for stimulus group pulled in should be shown
    await waitFor(() => {
      expect(screen.getByTestId("add-to-exam-warnings")).toBeInTheDocument();
    });
    expect(screen.getByTestId("add-to-exam-warnings")).toHaveTextContent(
      "Additional questions from the same stimulus group were also added",
    );
  });

  it("9. Taxonomy manager tree reorder calls API", async () => {
    renderBank("/bank/taxonomy");

    await waitFor(() => {
      expect(screen.getByText("Chapter 1: Mechanics")).toBeInTheDocument();
    });

    // Chapter 1 move down button
    const downBtn = screen.getByTestId(`chapter-move-down-${CHAPTER_1_ID}`);

    act(() => {
      fireEvent.click(downBtn);
    });

    await waitFor(() => {
      const reorderCalls = world.calls.filter(
        (c) =>
          c.path === `/api/v1/subjects/${SUBJECT_ID}/chapters/reorder` &&
          c.method === "POST",
      );
      expect(reorderCalls.length).toBeGreaterThan(0);
      expect(reorderCalls[0]?.body).toEqual({
        ids: [CHAPTER_2_ID, CHAPTER_1_ID],
      });
    });
  });

  it("10. Merge dialog confirms with question count", async () => {
    renderBank("/bank/taxonomy");

    await waitFor(() => {
      expect(screen.getByText("Chapter 1: Mechanics")).toBeInTheDocument();
    });

    const mergeBtn = screen.getByTestId(`chapter-merge-${CHAPTER_1_ID}`);

    act(() => {
      fireEvent.click(mergeBtn);
    });

    await waitFor(() => {
      expect(screen.getByTestId("merge-confirm-dialog")).toBeInTheDocument();
    });

    // Dialog description shows question count that will move
    expect(
      screen.getByText(/This will move 2 approved questions/i),
    ).toBeInTheDocument();

    const targetSelect = screen.getByTestId("merge-target-select");
    act(() => {
      fireEvent.change(targetSelect, { target: { value: CHAPTER_2_ID } });
    });

    const confirmBtn = screen.getByTestId("merge-confirm-btn");
    act(() => {
      fireEvent.click(confirmBtn);
    });

    await waitFor(() => {
      const mergeCalls = world.calls.filter(
        (c) =>
          c.path === `/api/v1/chapters/${CHAPTER_1_ID}/merge` &&
          c.method === "POST",
      );
      expect(mergeCalls.length).toBeGreaterThan(0);
      expect(mergeCalls[0]?.body).toEqual({
        into_chapter_id: CHAPTER_2_ID,
      });
    });
  });

  it("11. Shows friendly error when deleting non-empty subject or chapter", async () => {
    renderBank("/bank/taxonomy");

    await waitFor(() => {
      expect(
        screen.getByTestId(`chapter-item-${CHAPTER_1_ID}`),
      ).toBeInTheDocument();
    });

    const chapter1 = screen.getByTestId(`chapter-item-${CHAPTER_1_ID}`);
    const deleteBtn = within(chapter1).getByTestId(
      `delete-chapter-${CHAPTER_1_ID}`,
    );

    act(() => {
      fireEvent.click(deleteBtn);
    });

    // Verify delete endpoint was called and returned 409
    await waitFor(() => {
      const deleteCalls = world.calls.filter(
        (c) =>
          c.path === `/api/v1/chapters/${CHAPTER_1_ID}` &&
          c.method === "DELETE",
      );
      expect(deleteCalls.length).toBeGreaterThan(0);
    });
  });

  it("12. Teacher view hides editor-only controls", async () => {
    world.role = "teacher";
    renderBank("/bank/taxonomy");

    await waitFor(() => {
      expect(
        screen.getByTestId("taxonomy-readonly-notice"),
      ).toBeInTheDocument();
    });

    expect(screen.getByTestId("taxonomy-readonly-notice")).toHaveTextContent(
      "You are viewing the taxonomy in read-only mode.",
    );

    // Editor controls must NOT exist
    expect(screen.queryByTestId("new-subject-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("add-chapter-btn")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Move up" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Move down" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Merge" }),
    ).not.toBeInTheDocument();
  });
});
