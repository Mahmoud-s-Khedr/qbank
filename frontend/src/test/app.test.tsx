import { QueryClient } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import {
  apiClient,
  CSRF_HEADER_NAME,
  csrfMiddleware,
  readCookie,
} from "@/api/client";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";

function mockHealthFetch(
  response: { status: number; body: unknown } | { networkError: true },
) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((request) => {
    const url = request instanceof Request ? request.url : String(request);
    if (url.includes("/api/v1/auth/me")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            id: "u",
            name: "Admin",
            role: "admin",
            email: "a@example.com",
            is_active: true,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    }
    if (url.includes("/api/v1/org/settings")) {
      return Promise.resolve(
        new Response(
          JSON.stringify({
            name: "School",
            extract_model: "model",
            verify_policy: "all",
            default_digits: "arabic",
            default_template_id: null,
            llm_monthly_cap_usd: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    }
    if (url.includes("/api/v1/llm/models"))
      return Promise.resolve(
        new Response("[]", {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    if (url.endsWith("/api/v1/exams?limit=100"))
      return Promise.resolve(
        new Response('{"items":[],"next_cursor":null}', {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    if (url.includes("/api/v1/subjects"))
      return Promise.resolve(
        new Response('{"items":[],"next_cursor":null}', {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    if (url.includes("/api/v1/exam-templates"))
      return Promise.resolve(
        new Response('{"items":[],"next_cursor":null}', {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    if ("networkError" in response) {
      return Promise.reject(new Error("Network error"));
    }
    return Promise.resolve(
      new Response(JSON.stringify(response.body), {
        status: response.status,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });
}

function renderApp(initialEntries: string[] = ["/sources"]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const router = createAppRouter(initialEntries);
  return render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
}

describe("App shell, i18n/RTL, routing, and health indicator", () => {
  it("defaults to Arabic (RTL) and switches to English (LTR), updating document attributes and nav labels", async () => {
    mockHealthFetch({
      status: 200,
      body: { status: "ok", version: "0.1.0", db: "ok" },
    });

    const user = userEvent.setup();
    renderApp(["/sources"]);

    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");

    const nav = screen.getByRole("navigation", { name: "التنقل الرئيسي" });
    expect(
      within(nav).getByRole("link", { name: "المصادر" }),
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "المراجعة" }),
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "بنك الأسئلة" }),
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "الاختبارات" }),
    ).toBeInTheDocument();
    expect(
      within(nav).getByRole("link", { name: "الإعدادات" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "English" }));

    await waitFor(() => {
      expect(document.documentElement.lang).toBe("en");
      expect(document.documentElement.dir).toBe("ltr");
    });

    const enNav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(
      within(enNav).getByRole("link", { name: "Sources" }),
    ).toBeInTheDocument();
    expect(
      within(enNav).getByRole("link", { name: "Review" }),
    ).toBeInTheDocument();
    expect(
      within(enNav).getByRole("link", { name: "Question bank" }),
    ).toBeInTheDocument();
    expect(
      within(enNav).getByRole("link", { name: "Exams" }),
    ).toBeInTheDocument();
    expect(
      within(enNav).getByRole("link", { name: "Settings" }),
    ).toBeInTheDocument();
    expect(window.localStorage.getItem("qbank_lang")).toBe("en");
  });

  it("renders all navigation items and navigates to each placeholder page and 404 page", async () => {
    mockHealthFetch({
      status: 200,
      body: { status: "ok", version: "0.1.0", db: "ok" },
    });

    const user = userEvent.setup();
    renderApp(["/"]);

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(
      await screen.findByRole("heading", { level: 1, name: "Sources" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No sources yet")).toBeInTheDocument();

    const nav = screen.getByRole("navigation", { name: "Main navigation" });

    await user.click(within(nav).getByRole("link", { name: "Review" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Review" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Review queue is empty")).toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: "Question bank" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Question bank" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No approved questions in the bank"),
    ).toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: "Exams" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Exams" }),
    ).toBeInTheDocument();
    expect(screen.getByText("No exams created yet")).toBeInTheDocument();

    await user.click(within(nav).getByRole("link", { name: "Settings" }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Settings" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Organization" }),
    ).toBeInTheDocument();
  });

  it("renders the 404 page on unknown routes", async () => {
    mockHealthFetch({
      status: 200,
      body: { status: "ok", version: "0.1.0", db: "ok" },
    });

    renderApp(["/non-existent-route"]);

    expect(
      await screen.findByRole("heading", { level: 1, name: /404/ }),
    ).toBeInTheDocument();
  });

  it("displays the health status dot in ok (green), db-down (amber), and unreachable (red) states", async () => {
    mockHealthFetch({
      status: 200,
      body: { status: "ok", version: "0.1.0", db: "ok" },
    });

    const { unmount } = renderApp(["/sources"]);

    const dotOk = await screen.findByTestId("health-status-dot");
    await waitFor(() => {
      expect(dotOk).toHaveAttribute("data-status", "ok");
    });
    expect(dotOk.querySelector(".bg-green-500")).not.toBeNull();
    unmount();

    mockHealthFetch({
      status: 200,
      body: { status: "degraded", version: "0.1.0", db: "down" },
    });
    const { unmount: unmountDbDown } = renderApp(["/sources"]);
    const dotDbDown = await screen.findByTestId("health-status-dot");
    await waitFor(() => {
      expect(dotDbDown).toHaveAttribute("data-status", "db-down");
    });
    expect(dotDbDown.querySelector(".bg-amber-500")).not.toBeNull();
    unmountDbDown();

    mockHealthFetch({ networkError: true });
    const { unmount: unmountUnreachable } = renderApp(["/sources"]);
    const dotUnreachable = await screen.findByTestId("health-status-dot");
    await waitFor(() => {
      expect(dotUnreachable).toHaveAttribute("data-status", "unreachable");
    });
    expect(dotUnreachable.querySelector(".bg-red-500")).not.toBeNull();
    unmountUnreachable();
  });

  it("toggles light/dark theme and collapses desktop sidebar", async () => {
    mockHealthFetch({
      status: 200,
      body: { status: "ok", version: "0.1.0", db: "ok" },
    });

    const user = userEvent.setup();
    renderApp(["/sources"]);

    expect(document.documentElement.classList.contains("light")).toBe(true);
    await user.click(screen.getByRole("button", { name: "تبديل المظهر" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(window.localStorage.getItem("qbank_theme")).toBe("dark");

    const collapseBtn = screen.getByRole("button", {
      name: "طي القائمة الجانبية",
    });
    expect(collapseBtn).toHaveAttribute("aria-expanded", "true");
    await user.click(collapseBtn);
    expect(
      screen.getByRole("button", { name: "توسيع القائمة الجانبية" }),
    ).toHaveAttribute("aria-expanded", "false");
  });

  it("attaches X-CSRF-Token from qbank_csrf cookie on unsafe requests only", async () => {
    document.cookie = "qbank_csrf=test-csrf-token-123; path=/";
    expect(readCookie("qbank_csrf")).toBe("test-csrf-token-123");

    const postReq = new Request("http://localhost/api/v1/health", {
      method: "POST",
    });
    await csrfMiddleware.onRequest?.({
      request: postReq,
      schemaPath: "/api/v1/health",
      params: {},
      options: {} as never,
      id: "1",
    });
    expect(postReq.headers.get(CSRF_HEADER_NAME)).toBe("test-csrf-token-123");

    const getReq = new Request("http://localhost/api/v1/health", {
      method: "GET",
    });
    await csrfMiddleware.onRequest?.({
      request: getReq,
      schemaPath: "/api/v1/health",
      params: {},
      options: {} as never,
      id: "2",
    });
    expect(getReq.headers.get(CSRF_HEADER_NAME)).toBeNull();

    mockHealthFetch({
      status: 200,
      body: { status: "ok", version: "0.1.0", db: "ok" },
    });
    const res = await apiClient.GET("/api/v1/health");
    expect(res.data?.status).toBe("ok");
  });
});
