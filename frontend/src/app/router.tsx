import {
  createBrowserRouter,
  createMemoryRouter,
  Navigate,
  type RouteObject,
} from "react-router";
import { AppShell } from "@/app/app-shell";
import { AuthGuard } from "@/app/auth-guard";
import { NotFoundPage } from "@/app/not-found-page";
import { DevComponentsPage } from "@/dev/dev-components-page";
import { LoginPage } from "@/features/auth/login-page";
import { BankPage } from "@/features/bank/bank-page";
import { ExamsPage } from "@/features/exams/exams-page";
import { ReviewPage } from "@/features/review/review-page";
import { ReviewWorkspacePage } from "@/features/review/review-workspace-page";
import { SettingsPage } from "@/features/settings/settings-page";
import { SourceDetailPage } from "@/features/sources/source-detail-page";
import { SourcesPage } from "@/features/sources/sources-page";

export const routes: RouteObject[] = [
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          {
            index: true,
            element: <Navigate to="/sources" replace />,
          },
          {
            path: "sources",
            element: <SourcesPage />,
          },
          {
            path: "sources/:id",
            element: <SourceDetailPage />,
          },
          {
            path: "sources/:id/review",
            element: <ReviewWorkspacePage />,
          },
          {
            path: "sources/:id/pages/:pageNumber",
            element: <SourceDetailPage />,
          },
          {
            path: "review",
            element: <ReviewPage />,
          },
          {
            path: "bank",
            element: <BankPage />,
          },
          {
            path: "exams",
            element: <ExamsPage />,
          },
          {
            path: "settings",
            element: <SettingsPage />,
          },
          ...(import.meta.env.DEV
            ? [
                {
                  path: "dev/components",
                  element: <DevComponentsPage />,
                },
              ]
            : []),
          {
            path: "*",
            element: <NotFoundPage />,
          },
        ],
      },
    ],
  },
];

export function createAppRouter(initialEntries?: string[]) {
  if (initialEntries) {
    return createMemoryRouter(routes, { initialEntries });
  }
  return createBrowserRouter(routes);
}
