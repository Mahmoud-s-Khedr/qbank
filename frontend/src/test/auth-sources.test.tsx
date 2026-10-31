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
import type { PageOut, SourceDetail, SourceOut } from "@/api/hooks/sources";
import type { SubjectOut } from "@/api/hooks/subjects";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { setAppLanguage } from "@/i18n";

const SUBJECT_PHYSICS: SubjectOut = {
  id: "11111111-1111-1111-1111-111111111111",
  org_id: "00000000-0000-0000-0000-000000000001",
  name: "الفيزياء",
  language: "ar",
  grade: "الصف الثالث الثانوي",
  created_at: "2026-10-30T10:00:00Z",
  updated_at: "2026-10-30T10:00:00Z",
};

const SUBJECT_CHEMISTRY: SubjectOut = {
  id: "22222222-2222-2222-2222-222222222222",
  org_id: "00000000-0000-0000-0000-000000000001",
  name: "الكيمياء",
  language: "ar",
  grade: "الصف الثالث الثانوي",
  created_at: "2026-10-30T10:00:00Z",
  updated_at: "2026-10-30T10:00:00Z",
};

const SAMPLE_SUBJECTS: SubjectOut[] = [SUBJECT_PHYSICS, SUBJECT_CHEMISTRY];

function mustGet<T>(item: T | undefined, label = "item"): T {
  if (item === undefined) {
    throw new Error(`Expected ${label} to be defined`);
  }
  return item;
}

function makeUser(role: Role = "editor"): UserOut {
  return {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    org_id: "00000000-0000-0000-0000-000000000001",
    email: "user@school.edu.eg",
    name: "أحمد محمود",
    role,
    is_active: true,
    last_login_at: "2026-10-31T10:00:00Z",
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-31T10:00:00Z",
  };
}

function makeSource(overrides: Partial<SourceOut> = {}): SourceOut {
  return {
    id: "src-1111-1111-1111-111111111111",
    subject_id: SUBJECT_PHYSICS.id,
    title: "كتاب الامتحان فيزياء",
    grade: "3ث",
    status: "ready",
    stage: "ready",
    page_count: 12,
    cost_usd: 0.0425,
    error: null,
    created_at: new Date(Date.now() - 2 * 3600 * 1000).toISOString(),
    updated_at: new Date(Date.now() - 3600 * 1000).toISOString(),
    ...overrides,
  };
}

function makeSourceDetail(overrides: Partial<SourceDetail> = {}): SourceDetail {
  return {
    ...makeSource({
      status: "extracting",
      stage: "extract",
      page_count: 10,
      cost_usd: 0.015,
    }),
    page_counts: {
      pending: 2,
      rendered: 5,
      extracted: 2,
      validated: 0,
      failed: 1,
    },
    ...overrides,
  };
}

function makePage(
  pageNumber: number,
  overrides: Partial<PageOut> = {},
): PageOut {
  return {
    id: `page-id-${String(pageNumber)}`,
    page_number: pageNumber,
    status: "rendered",
    page_kind: "questions",
    width_px: 800,
    height_px: 1120,
    dpi: 150,
    error: null,
    created_at: "2026-10-31T10:00:00Z",
    updated_at: "2026-10-31T10:00:00Z",
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  if (status === 204) {
    return new Response(null, { status: 204 });
  }
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderWithRouter(initialEntries: string[] = ["/sources"]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const router = createAppRouter(initialEntries);
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, queryClient, router };
}

class MockEventSource {
  static instances: MockEventSource[] = [];

  readonly url: string;
  readonly withCredentials: boolean;
  closed = false;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  private listeners = new Map<string, Set<EventListener>>();

  constructor(url: string | URL, init?: EventSourceInit) {
    this.url = String(url);
    this.withCredentials = Boolean(init?.withCredentials);
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: EventListener): void {
    const set = this.listeners.get(type) ?? new Set<EventListener>();
    set.add(listener);
    this.listeners.set(type, set);
  }

  removeEventListener(type: string, listener: EventListener): void {
    this.listeners.get(type)?.delete(listener);
  }

  close(): void {
    this.closed = true;
  }

  emitProgress(data: unknown): void {
    const event = new MessageEvent("progress", {
      data: JSON.stringify(data),
    });
    const progressListeners = this.listeners.get("progress");
    if (progressListeners) {
      for (const listener of progressListeners) {
        listener(event);
      }
    }
  }

  emitError(): void {
    this.onerror?.(new Event("error"));
  }
}

class MockXMLHttpRequest {
  static instances: MockXMLHttpRequest[] = [];

  method = "";
  url = "";
  withCredentials = false;
  requestHeaders: Record<string, string> = {};
  status = 200;
  responseText = "";
  sentBody: FormData | null = null;

  upload: {
    onprogress: ((event: ProgressEvent) => void) | null;
  } = {
    onprogress: null,
  };

  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    MockXMLHttpRequest.instances.push(this);
  }

  open(method: string, url: string): void {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name: string, value: string): void {
    this.requestHeaders[name] = value;
  }

  send(body: Document | XMLHttpRequestBodyInit | null): void {
    this.sentBody = body instanceof FormData ? body : null;
  }

  triggerProgress(loaded: number, total: number): void {
    this.upload.onprogress?.(
      new ProgressEvent("progress", {
        lengthComputable: true,
        loaded,
        total,
      }),
    );
  }

  triggerResponse(status: number, body: unknown): void {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  MockXMLHttpRequest.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Auth, Route Guard, and Role-based Navigation", () => {
  it("shows validation errors, maps invalid_credentials error, and redirects to safe next path on login", async () => {
    let loginAttempt = 0;
    const userObj = makeUser("editor");

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/v1/auth/login")) {
        loginAttempt += 1;
        if (loginAttempt === 1) {
          return Promise.resolve(
            jsonResponse(
              {
                type: "about:blank",
                title: "Unauthorized",
                status: 401,
                detail: "Bad credentials",
                code: "invalid_credentials",
              },
              401,
            ),
          );
        }
        return Promise.resolve(jsonResponse(userObj, 200));
      }
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(userObj, 200));
      }
      if (url.includes("/api/v1/sources/src-target")) {
        return Promise.resolve(
          jsonResponse(makeSourceDetail({ id: "src-target" }), 200),
        );
      }
      if (url.includes("/api/v1/sources")) {
        return Promise.resolve(
          jsonResponse({ items: [], next_cursor: null }, 200),
        );
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    const { router } = renderWithRouter([
      "/login?next=%2Fsources%2Fsrc-target",
    ]);

    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");

    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));
    expect(
      await screen.findByText("البريد الإلكتروني مطلوب"),
    ).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("البريد الإلكتروني"),
      "user@school.edu.eg",
    );
    await user.type(screen.getByLabelText("كلمة المرور"), "wrong-pass");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));

    expect(
      await screen.findByText("البريد الإلكتروني أو كلمة المرور غير صحيحة"),
    ).toBeInTheDocument();

    await user.clear(screen.getByLabelText("كلمة المرور"));
    await user.type(screen.getByLabelText("كلمة المرور"), "correct-pass");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sources/src-target");
    });
  });

  it("rejects external next URLs on login and redirects to /sources instead", async () => {
    const userObj = makeUser("editor");
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (
        url.includes("/api/v1/auth/login") ||
        url.includes("/api/v1/auth/me")
      ) {
        return Promise.resolve(jsonResponse(userObj, 200));
      }
      if (url.includes("/api/v1/sources")) {
        return Promise.resolve(
          jsonResponse({ items: [], next_cursor: null }, 200),
        );
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    const { router } = renderWithRouter([
      "/login?next=https%3A%2F%2Fevil.example.com%2Fpwn",
    ]);

    await user.type(
      screen.getByLabelText("البريد الإلكتروني"),
      "user@school.edu.eg",
    );
    await user.type(screen.getByLabelText("كلمة المرور"), "secret");
    await user.click(screen.getByRole("button", { name: "تسجيل الدخول" }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sources");
    });
  });

  it("redirects to /login?next=... and invalidates me when any query returns 401", async () => {
    const userObj = makeUser("editor");

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(userObj, 200));
      }
      if (url.includes("/api/v1/sources")) {
        return Promise.resolve(
          jsonResponse(
            {
              type: "about:blank",
              title: "Unauthorized",
              status: 401,
              detail: "Session expired",
              code: "unauthorized",
            },
            401,
          ),
        );
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const { queryClient, router } = renderWithRouter([
      "/sources?filter=active",
    ]);
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
    expect(router.state.location.search).toBe(
      "?next=%2Fsources%3Ffilter%3Dactive",
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["auth", "me"] }),
    );
  });

  it("hides Sources and Review nav items for teacher role, shows user menu, and logs out", async () => {
    await setAppLanguage("en");
    const teacherUser = makeUser("teacher");

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(teacherUser, 200));
      }
      if (url.includes("/api/v1/auth/logout")) {
        return Promise.resolve(jsonResponse(null, 204));
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    const { router } = renderWithRouter(["/bank"]);

    const menuTrigger = await screen.findByTestId("user-menu-trigger");
    expect(menuTrigger).toHaveTextContent("أحمد محمود");
    expect(menuTrigger).toHaveTextContent("Teacher");

    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(
      within(nav).queryByRole("link", { name: "Sources" }),
    ).not.toBeInTheDocument();
    expect(
      within(nav).queryByRole("link", { name: "Review" }),
    ).not.toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "Question bank" }),
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "Exams" }),
    ).toBeInTheDocument();

    await user.click(menuTrigger);
    const logoutItem = await screen.findByTestId("logout-button");
    await user.click(logoutItem);

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/login");
    });
  });
});

describe("Sources List and Upload Dialog", () => {
  it("renders sources table, filters by subject and status, and loads more via cursor pagination", async () => {
    await setAppLanguage("en");
    const editorUser = makeUser("editor");
    const source1 = makeSource({
      id: "src-1",
      title: "Physics Workbook Part 1",
      subject_id: SUBJECT_PHYSICS.id,
      status: "ready",
      page_count: 20,
      cost_usd: 0.1234,
    });
    const source2 = makeSource({
      id: "src-2",
      title: "Chemistry Workbook Part 2",
      subject_id: SUBJECT_CHEMISTRY.id,
      status: "extracting",
      page_count: 15,
      cost_usd: 0.005,
    });

    const requestedUrls: string[] = [];

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      requestedUrls.push(url);

      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(editorUser, 200));
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      if (url.includes("/api/v1/sources")) {
        const parsedUrl = new URL(url, "http://localhost");
        const cursor = parsedUrl.searchParams.get("cursor");
        const statusParam = parsedUrl.searchParams.get("status");
        const subjectParam = parsedUrl.searchParams.get("subject_id");

        if (statusParam === "failed") {
          return Promise.resolve(
            jsonResponse({ items: [], next_cursor: null }, 200),
          );
        }
        if (subjectParam === SUBJECT_CHEMISTRY.id) {
          return Promise.resolve(
            jsonResponse({ items: [source2], next_cursor: null }, 200),
          );
        }
        if (cursor === "cursor-page-2") {
          return Promise.resolve(
            jsonResponse({ items: [source2], next_cursor: null }, 200),
          );
        }
        return Promise.resolve(
          jsonResponse({ items: [source1], next_cursor: "cursor-page-2" }, 200),
        );
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    renderWithRouter(["/sources"]);

    expect(
      await screen.findByText("Physics Workbook Part 1"),
    ).toBeInTheDocument();
    expect(screen.getByText("$0.1234")).toBeInTheDocument();
    expect(screen.getByText("20 / 0 / 20")).toBeInTheDocument();

    const loadMoreBtn = await screen.findByTestId("sources-load-more");
    await user.click(loadMoreBtn);

    expect(
      await screen.findByText("Chemistry Workbook Part 2"),
    ).toBeInTheDocument();
    expect(screen.getByText("$0.0050")).toBeInTheDocument();

    // Filter by subject
    await user.selectOptions(
      screen.getByTestId("filter-subject"),
      SUBJECT_CHEMISTRY.id,
    );
    await waitFor(() => {
      expect(
        requestedUrls.some((u) =>
          u.includes(`subject_id=${SUBJECT_CHEMISTRY.id}`),
        ),
      ).toBe(true);
    });

    // Filter by status -> failed -> empty state
    await user.selectOptions(screen.getByTestId("filter-status"), "failed");
    expect(await screen.findByText("No sources yet")).toBeInTheDocument();
  });

  it("validates file type and size in upload dialog, reports XHR progress, and navigates to source detail on 202", async () => {
    await setAppLanguage("en");
    document.cookie = "qbank_csrf=csrf-upload-token; path=/";
    vi.stubGlobal("XMLHttpRequest", MockXMLHttpRequest);

    const editorUser = makeUser("editor");
    const createdSource = makeSource({
      id: "src-uploaded-99",
      title: "al-emtihan-physics",
      status: "rendering",
      stage: "render",
    });

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(editorUser, 200));
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      if (url.includes("/api/v1/sources/src-uploaded-99/pages")) {
        return Promise.resolve(jsonResponse([], 200));
      }
      if (url.includes("/api/v1/sources/src-uploaded-99")) {
        return Promise.resolve(
          jsonResponse(
            makeSourceDetail({
              ...createdSource,
              page_counts: { rendered: 0 },
            }),
            200,
          ),
        );
      }
      if (url.includes("/api/v1/sources")) {
        return Promise.resolve(
          jsonResponse({ items: [], next_cursor: null }, 200),
        );
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    const { router } = renderWithRouter(["/sources"]);

    const uploadBtn = await screen.findByTestId("upload-workbook-button");
    await user.click(uploadBtn);

    const fileInput = await screen.findByTestId("upload-file-input");

    // 1. Wrong file type (.txt)
    const badFile = new File(["not a pdf"], "notes.txt", {
      type: "text/plain",
    });
    await user.upload(fileInput, badFile);
    expect(
      await screen.findByText("Only PDF files (.pdf) are allowed"),
    ).toBeInTheDocument();

    // 2. File too large (> 300 MB)
    const hugeFile = new File(["%PDF-1.7"], "huge-book.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(hugeFile, "size", { value: 305 * 1024 * 1024 });
    await user.upload(fileInput, hugeFile);
    expect(
      await screen.findByText("File size must not exceed 300 MB"),
    ).toBeInTheDocument();

    // 3. Valid PDF file defaults title without extension
    const titleInput = screen.getByLabelText("Title");
    await user.clear(titleInput);
    const validPdf = new File(["%PDF-1.7 content"], "al-emtihan-physics.pdf", {
      type: "application/pdf",
    });
    await user.upload(fileInput, validPdf);
    expect(titleInput).toHaveValue("al-emtihan-physics");

    // Submit upload
    await user.click(screen.getByTestId("upload-submit"));

    expect(MockXMLHttpRequest.instances).toHaveLength(1);
    const xhr = mustGet(MockXMLHttpRequest.instances[0], "xhr");
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("/api/v1/sources");
    expect(xhr.withCredentials).toBe(true);
    expect(xhr.requestHeaders["X-CSRF-Token"]).toBe("csrf-upload-token");

    act(() => {
      xhr.triggerProgress(50, 100);
    });
    expect(await screen.findByRole("progressbar")).toHaveAttribute(
      "aria-valuenow",
      "50",
    );

    act(() => {
      xhr.triggerResponse(202, {
        job_id: "job-123",
        source: createdSource,
      });
    });

    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/sources/src-uploaded-99");
    });
  });

  it("maps server error codes invalid_pdf and file_too_large in upload dialog", async () => {
    await setAppLanguage("en");
    vi.stubGlobal("XMLHttpRequest", MockXMLHttpRequest);

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(makeUser("admin"), 200));
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      return Promise.resolve(
        jsonResponse({ items: [], next_cursor: null }, 200),
      );
    });

    const user = userEvent.setup();
    renderWithRouter(["/sources"]);

    await user.click(await screen.findByTestId("upload-workbook-button"));
    const fileInput = await screen.findByTestId("upload-file-input");
    const pdfFile = new File(["corrupted"], "corrupted.pdf", {
      type: "application/pdf",
    });
    await user.upload(fileInput, pdfFile);
    await user.click(screen.getByTestId("upload-submit"));

    const xhr = mustGet(MockXMLHttpRequest.instances[0], "xhr");
    act(() => {
      xhr.triggerResponse(422, {
        code: "invalid_pdf",
        detail: "Invalid PDF header",
      });
    });

    expect(
      await screen.findByText(
        "The uploaded file is not a valid PDF or is corrupted",
      ),
    ).toBeInTheDocument();
  });
});

describe("Source Detail, SSE Live Progress, Page Grid, and Page Viewer", () => {
  it("updates progress UI from SSE events, reconnects on error, and closes stream on terminal status", async () => {
    await setAppLanguage("en");
    const detail = makeSourceDetail({
      id: "src-live-1",
      title: "Live Physics Source",
      status: "extracting",
      stage: "extract",
      page_count: 10,
      page_counts: {
        rendered: 5,
        extracted: 2,
        validated: 0,
        failed: 1,
      },
    });

    let pageListFetches = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(makeUser("editor"), 200));
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      if (url.includes("/api/v1/sources/src-live-1/pages")) {
        pageListFetches += 1;
        return Promise.resolve(
          jsonResponse(
            [
              makePage(1, { status: "validated", page_kind: "questions" }),
              makePage(2, {
                status: "failed",
                page_kind: null,
                error: "Broken PDF page stream",
              }),
            ],
            200,
          ),
        );
      }
      if (url.includes("/api/v1/sources/src-live-1")) {
        return Promise.resolve(jsonResponse(detail, 200));
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    renderWithRouter(["/sources/src-live-1"]);

    expect(
      await screen.findByRole("heading", {
        level: 1,
        name: "Live Physics Source",
      }),
    ).toBeInTheDocument();
    // Counts are per current page status; progress is cumulative (5 rendered + 2 extracted).
    expect(screen.getByTestId("stage-count-rendered")).toHaveTextContent(
      "7 / 10",
    );
    expect(screen.getByTestId("stage-count-extracted")).toHaveTextContent(
      "2 / 10",
    );

    // Failed page shows error in tooltip trigger and tooltip content on hover
    const errorTrigger = await screen.findByTestId("page-error-trigger-2");
    expect(errorTrigger).toHaveAttribute("title", "Broken PDF page stream");
    await user.hover(errorTrigger);
    expect(await screen.findByTestId("page-error-tooltip-2")).toHaveTextContent(
      "Broken PDF page stream",
    );

    expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(1);
    const es = mustGet(
      MockEventSource.instances[MockEventSource.instances.length - 1],
      "eventSource",
    );
    expect(es.url).toBe("/api/v1/sources/src-live-1/events");
    expect(es.withCredentials).toBe(true);

    // Emit progress update
    act(() => {
      es.emitProgress({
        status: "validating",
        stage: "validate",
        page_counts: {
          rendered: 0,
          extracted: 3,
          validated: 6,
          failed: 1,
        },
      });
    });

    expect(await screen.findByTestId("stage-count-rendered")).toHaveTextContent(
      "9 / 10",
    );
    expect(screen.getByTestId("stage-count-validated")).toHaveTextContent(
      "6 / 10",
    );
    expect(screen.getByTestId("source-stage")).toHaveTextContent("validate");
    expect(es.closed).toBe(false);
    // Moving page counts refresh the page grid, which is a separate query.
    await waitFor(() => {
      expect(pageListFetches).toBeGreaterThanOrEqual(2);
    });

    // Emit terminal status -> closes EventSource
    act(() => {
      es.emitProgress({
        status: "ready",
        stage: "ready",
        page_counts: {
          rendered: 9,
          extracted: 9,
          validated: 9,
          failed: 1,
        },
      });
    });

    await waitFor(() => {
      expect(es.closed).toBe(true);
    });
  });

  it("reconnects EventSource with backoff on error and closes on unmount", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const detail = makeSourceDetail({
        id: "src-reconnect",
        status: "rendering",
        stage: "render",
      });

      vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
        const url = input instanceof Request ? input.url : String(input);
        if (url.includes("/api/v1/auth/me")) {
          return Promise.resolve(jsonResponse(makeUser("editor"), 200));
        }
        if (url.includes("/api/v1/subjects")) {
          return Promise.resolve(
            jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
          );
        }
        if (url.includes("/api/v1/sources/src-reconnect/pages")) {
          return Promise.resolve(jsonResponse([], 200));
        }
        if (url.includes("/api/v1/sources/src-reconnect")) {
          return Promise.resolve(jsonResponse(detail, 200));
        }
        return Promise.resolve(
          jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
        );
      });

      const { unmount } = renderWithRouter(["/sources/src-reconnect"]);

      await waitFor(() => {
        expect(MockEventSource.instances).toHaveLength(1);
      });
      const firstEs = mustGet(MockEventSource.instances[0], "firstEs");

      act(() => {
        firstEs.emitError();
      });
      expect(firstEs.closed).toBe(true);

      // Advance backoff timer (1000ms)
      act(() => {
        vi.advanceTimersByTime(1100);
      });

      expect(MockEventSource.instances).toHaveLength(2);
      const secondEs = mustGet(MockEventSource.instances[1], "secondEs");
      expect(secondEs.closed).toBe(false);

      unmount();
      expect(secondEs.closed).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows paused reason banner, windows page grid past 200 pages, and deletes source via confirm dialog", async () => {
    await setAppLanguage("en");
    const pausedDetail = makeSourceDetail({
      id: "src-paused",
      title: "Paused Workbook",
      status: "paused",
      stage: "extract",
      error: "Monthly LLM spend cap reached",
      page_count: 250,
    });
    const manyPages = Array.from({ length: 250 }, (_, idx) =>
      makePage(idx + 1),
    );

    let deleted = false;
    vi.spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      const url = input instanceof Request ? input.url : String(input);
      const method =
        input instanceof Request ? input.method : (init?.method ?? "GET");

      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(makeUser("admin"), 200));
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      if (url.includes("/api/v1/sources/src-paused/pages")) {
        return Promise.resolve(jsonResponse(manyPages, 200));
      }
      if (url.includes("/api/v1/sources/src-paused")) {
        if (method === "DELETE") {
          deleted = true;
          return Promise.resolve(jsonResponse(null, 204));
        }
        return Promise.resolve(jsonResponse(pausedDetail, 200));
      }
      if (url.includes("/api/v1/sources")) {
        return Promise.resolve(
          jsonResponse({ items: [], next_cursor: null }, 200),
        );
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    const { router } = renderWithRouter(["/sources/src-paused"]);

    expect(await screen.findByTestId("source-paused-banner")).toHaveTextContent(
      "Monthly LLM spend cap reached",
    );

    // Windowed grid: only 200 cards mounted at once
    const grid = await screen.findByTestId("page-grid");
    expect(within(grid).getByTestId("page-card-1")).toBeInTheDocument();
    expect(within(grid).getByTestId("page-card-200")).toBeInTheDocument();
    expect(within(grid).queryByTestId("page-card-201")).not.toBeInTheDocument();

    // Delete via confirm Dialog component
    await user.click(screen.getByTestId("delete-source-button"));
    expect(
      await screen.findByTestId("delete-confirm-dialog"),
    ).toBeInTheDocument();
    await user.click(screen.getByTestId("confirm-delete-source"));

    await waitFor(() => {
      expect(deleted).toBe(true);
      expect(router.state.location.pathname).toBe("/sources");
    });
  });

  it("opens PageCanvas viewer in view mode and maps ArrowLeft/ArrowRight according to RTL and LTR reading direction", async () => {
    const detail = makeSourceDetail({
      id: "src-rtl",
      title: "كتاب الأحياء",
      status: "ready",
      stage: "ready",
      page_count: 3,
    });
    const pages = [makePage(1), makePage(2), makePage(3)];

    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const url = input instanceof Request ? input.url : String(input);
      if (url.includes("/api/v1/auth/me")) {
        return Promise.resolve(jsonResponse(makeUser("editor"), 200));
      }
      if (url.includes("/api/v1/subjects")) {
        return Promise.resolve(
          jsonResponse({ items: SAMPLE_SUBJECTS, next_cursor: null }, 200),
        );
      }
      if (url.includes("/api/v1/sources/src-rtl/pages")) {
        return Promise.resolve(jsonResponse(pages, 200));
      }
      if (url.includes("/api/v1/sources/src-rtl")) {
        return Promise.resolve(jsonResponse(detail, 200));
      }
      return Promise.resolve(
        jsonResponse({ status: "ok", version: "0.1.0", db: "ok" }, 200),
      );
    });

    const user = userEvent.setup();
    renderWithRouter(["/sources/src-rtl"]);

    // Default is Arabic (RTL)
    expect(document.documentElement.dir).toBe("rtl");

    const page1Card = await screen.findByTestId("page-card-1");
    await user.click(within(page1Card).getByRole("button"));

    const viewerTitle = await screen.findByTestId("page-viewer-title");
    expect(viewerTitle).toHaveTextContent("عرض الصفحة 1 من 3");
    expect(screen.getByTestId("page-canvas")).toHaveAttribute(
      "data-mode",
      "view",
    );

    // In RTL, ArrowLeft (←) goes to NEXT page (1 -> 2)
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(await screen.findByTestId("page-viewer-title")).toHaveTextContent(
      "عرض الصفحة 2 من 3",
    );

    // In RTL, ArrowRight (→) goes to PREVIOUS page (2 -> 1)
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByTestId("page-viewer-title")).toHaveTextContent(
      "عرض الصفحة 1 من 3",
    );

    // Switch to English (LTR)
    await act(async () => {
      await setAppLanguage("en");
    });
    expect(document.documentElement.dir).toBe("ltr");

    // In LTR, ArrowRight (→) goes to NEXT page (1 -> 2)
    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(await screen.findByTestId("page-viewer-title")).toHaveTextContent(
      "Page 2 of 3",
    );

    // In LTR, ArrowLeft (←) goes to PREVIOUS page (2 -> 1)
    fireEvent.keyDown(window, { key: "ArrowLeft" });
    expect(await screen.findByTestId("page-viewer-title")).toHaveTextContent(
      "Page 1 of 3",
    );
  });
});

describe("cumulativeStageCount", () => {
  it("counts pages that reached a stage or any later stage", async () => {
    const { cumulativeStageCount } =
      await import("@/features/sources/progress");
    const counts = { rendered: 1, extracted: 2, validated: 3, failed: 4 };
    expect(cumulativeStageCount(counts, "rendered")).toBe(6);
    expect(cumulativeStageCount(counts, "extracted")).toBe(5);
    expect(cumulativeStageCount(counts, "validated")).toBe(3);
    expect(cumulativeStageCount(counts, "failed")).toBe(4);
    expect(cumulativeStageCount({}, "rendered")).toBe(0);
  });
});
