import { QueryClient } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { setAppLanguage } from "@/i18n";

const user = {
  id: "u",
  org_id: "o",
  name: "Admin",
  email: "admin@example.com",
  role: "admin",
  is_active: true,
  last_login_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const template = {
  id: "t",
  name: "School",
  header: {
    school_name: "School",
    exam_title: "Exam",
    subject_label: "Math",
    grade: "3",
    date: "",
    duration_minutes: null,
    instructions: "Read",
  },
  logo_asset_id: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const org = {
  name: "School",
  llm_monthly_cap_usd: 10,
  verify_policy: "all",
  default_digits: "arabic",
  default_template_id: null,
  extract_model: "model",
};
let role = "admin";
let questionType = "essay";
let version = false;
let pending = false;
let polls = 0;
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
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
beforeEach(async () => {
  await setAppLanguage("en");
  role = "admin";
  questionType = "essay";
  version = false;
  pending = false;
  polls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      await Promise.resolve();
      const url = new URL(request.url);
      const p = url.pathname;
      const method = request.method;
      if (p === "/api/v1/auth/me") return json({ ...user, role });
      if (p === "/api/v1/health") return json({ status: "ok" });
      if (p === "/api/v1/org/settings") return json(org);
      if (p === "/api/v1/llm/models")
        return json([
          {
            id: "model",
            price_in_per_m: "0.1",
            price_out_per_m: "0.5",
            default_for_stages: ["extract"],
          },
        ]);
      if (p === "/api/v1/users")
        return json(
          method === "POST" ? user : { items: [user], next_cursor: null },
        );
      if (p === "/api/v1/users/u")
        return json({ detail: "Cannot demote yourself" }, 403);
      if (p === "/api/v1/exam-templates")
        return json(
          method === "POST"
            ? template
            : { items: [template], next_cursor: null },
        );
      if (p === "/api/v1/exam-templates/t/logo")
        return json({ ...template, logo_asset_id: "logo" });
      if (p === "/api/v1/exam-templates/t") return json(template);
      if (p === "/api/v1/costs/summary")
        return json({
          total_usd: "0.2",
          average_cost_per_page: "0.1",
          this_month_usd: "0.2",
          cap_usd: 10,
          by_month: [{ name: "2026-10", cost_usd: "0.2" }],
          by_stage: [{ name: "extract", cost_usd: "0.2" }],
          by_model: [],
          top_sources: [],
        });
      if (p === "/api/v1/exams/e")
        return json({
          id: "e",
          title: "Exam",
          sections: [{ items: [{ question: { type: questionType } }] }],
          versions: version ? [{ id: "v", label: "A" }] : [],
        });
      if (p === "/api/v1/exams/e/versions") {
        version = true;
        return json([]);
      }
      if (p === "/api/v1/exams/e/exports" && method === "POST") {
        pending = true;
        return json({ exports: [] }, 202);
      }
      if (p === "/api/v1/exports/x" && method === "DELETE") {
        pending = false;
        return new Response(null, { status: 204 });
      }
      if (p === "/api/v1/exams/e/exports") {
        if (pending) polls++;
        return json(
          pending
            ? [
                {
                  id: "x",
                  version_label: "A",
                  kind: "pdf",
                  status: polls > 1 ? "ready" : "pending",
                  size_bytes: 100,
                  created_at: "2026-01-01T00:00:00Z",
                  stale: true,
                  error: null,
                },
              ]
            : [],
        );
      }
      return json({});
    }),
  );
});
describe("admin and exports", () => {
  it("edits organization and renders the cost chart and table", async () => {
    setup("/settings");
    expect(await screen.findByLabelText("Name")).toHaveValue("School");
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "New school" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => {
      expect(
        vi
          .mocked(fetch)
          .mock.calls.some(
            ([req]) =>
              req instanceof Request &&
              req.method === "PATCH" &&
              req.url.includes("/org/settings"),
          ),
      ).toBe(true);
    });
    fireEvent.click(screen.getByRole("button", { name: "Costs" }));
    expect(
      await screen.findByRole("img", { name: "By month" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "2026-10" }),
    ).toBeInTheDocument();
  });
  it("shows the server self-demotion error", async () => {
    setup("/settings?tab=users");
    const role = await screen.findByLabelText("Role Admin");
    fireEvent.change(role, { target: { value: "teacher" } });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Cannot demote yourself",
    );
  });
  it("shows template fields in the live preview", async () => {
    setup("/settings?tab=templates");
    fireEvent.click(await screen.findByRole("button", { name: "School" }));
    expect(screen.getByLabelText("School name")).toHaveValue("School");
    expect(screen.getByText("Read")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("School name"), {
      target: { value: "Updated school" },
    });
    expect(screen.getByText("Updated school")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Logo"), {
      target: {
        files: [new File(["image"], "logo.png", { type: "image/png" })],
      },
    });
    expect(await screen.findByRole("img", { name: "Logo" })).toHaveAttribute(
      "src",
      "/api/v1/assets/logo/image",
    );
  });
  it("invites a user and displays the password", async () => {
    setup("/settings?tab=users");
    fireEvent.change(await screen.findByLabelText("Name"), {
      target: { value: "Teacher" },
    });
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "t@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "password123" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Invite" }));
    expect(await screen.findByText("password123")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy" })).toBeInTheDocument();
  });
  it("does not expose settings to teachers", async () => {
    role = "teacher";
    setup("/settings");
    expect(await screen.findByText("Access denied")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Users" }),
    ).not.toBeInTheDocument();
  });
  it("offers bubble sheets for MCQ exams", async () => {
    questionType = "mcq_single";
    version = true;
    setup("/exams/e/exports");
    expect(
      await screen.findByLabelText("Bubble sheet PDF"),
    ).toBeInTheDocument();
  });
  it("generates versions and polls exports while hiding bubble sheets for essays", async () => {
    setup("/exams/e/exports");
    fireEvent.click(
      await screen.findByRole("button", { name: "Generate versions" }),
    );
    fireEvent.click(await screen.findByLabelText("A"));
    expect(screen.queryByLabelText("Bubble sheet PDF")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Generate exports" }));
    expect(await screen.findByText("Stale")).toBeInTheDocument();
    await waitFor(
      () => {
        expect(
          screen.getByRole("link", { name: "Download" }),
        ).toBeInTheDocument();
      },
      { timeout: 5000 },
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => {
      expect(
        screen.queryByRole("link", { name: "Download" }),
      ).not.toBeInTheDocument();
    });
  });
});
