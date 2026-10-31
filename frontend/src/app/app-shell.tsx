import {
  BookOpen,
  ClipboardCheck,
  FileText,
  Library,
  LogOut,
  type LucideIcon,
  Menu,
  Settings,
  User,
} from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router";
import { type Role, useLogout, useMe } from "@/api/hooks/auth";
import { HealthStatusDot } from "@/app/health-status-dot";
import { LanguageSwitch } from "@/app/language-switch";
import { ThemeToggle } from "@/app/theme-toggle";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

interface NavItemConfig {
  to: string;
  labelKey:
    "nav.sources" | "nav.review" | "nav.bank" | "nav.exams" | "nav.settings";
  icon: LucideIcon;
  roles: readonly Role[];
}

const NAV_ITEMS: readonly NavItemConfig[] = [
  {
    to: "/sources",
    labelKey: "nav.sources",
    icon: BookOpen,
    roles: ["admin", "editor"],
  },
  {
    to: "/review",
    labelKey: "nav.review",
    icon: ClipboardCheck,
    roles: ["admin", "editor"],
  },
  {
    to: "/bank",
    labelKey: "nav.bank",
    icon: Library,
    roles: ["admin", "editor", "teacher"],
  },
  {
    to: "/exams",
    labelKey: "nav.exams",
    icon: FileText,
    roles: ["admin", "editor", "teacher"],
  },
  {
    to: "/settings",
    labelKey: "nav.settings",
    icon: Settings,
    roles: ["admin"],
  },
];

function isValidRole(value: unknown): value is Role {
  return value === "admin" || value === "editor" || value === "teacher";
}

export function AppShell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { data: user } = useMe();
  const logoutMutation = useLogout();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const userRole = isValidRole(user?.role) ? user.role : undefined;
  const visibleNavItems = userRole
    ? NAV_ITEMS.filter((item) => item.roles.includes(userRole))
    : NAV_ITEMS;

  const handleLogout = async () => {
    try {
      await logoutMutation.mutateAsync();
    } finally {
      await navigate("/login", { replace: true });
    }
  };

  return (
    <div className="bg-background text-foreground flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="focus:bg-primary focus:text-primary-foreground focus-visible:ring-ring sr-only focus:not-sr-only focus:fixed focus:start-2 focus:top-2 focus:z-50 focus:rounded-md focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:shadow-md focus:outline-none"
      >
        {t("app.skipToContent")}
      </a>

      <header className="bg-card border-border sticky top-0 z-30 flex h-14 items-center gap-3 border-b px-4">
        <div className="flex items-center gap-2">
          <Sheet open={isMobileMenuOpen} onOpenChange={setIsMobileMenuOpen}>
            <SheetTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="md:hidden"
                aria-label={t("app.sidebar.openMenu")}
              >
                <Menu className="size-5" aria-hidden="true" />
              </Button>
            </SheetTrigger>
            <SheetContent side="start" className="w-64 p-0">
              <SheetHeader className="border-b px-4 py-3">
                <SheetTitle>{t("app.brand")}</SheetTitle>
                <SheetDescription className="sr-only">
                  {t("app.sidebar.mobileTitle")}
                </SheetDescription>
              </SheetHeader>
              <nav
                aria-label={t("app.sidebar.label")}
                className="flex flex-col gap-1 p-3"
              >
                {visibleNavItems.map((item) => {
                  const Icon = item.icon;
                  const label = t(item.labelKey);
                  return (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      onClick={() => {
                        setIsMobileMenuOpen(false);
                      }}
                      className={({ isActive }) =>
                        cn(
                          "focus-visible:ring-ring/50 flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px]",
                          isActive
                            ? "bg-primary text-primary-foreground"
                            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                        )
                      }
                    >
                      <Icon className="size-4 shrink-0" aria-hidden="true" />
                      <span>{label}</span>
                    </NavLink>
                  );
                })}
              </nav>
            </SheetContent>
          </Sheet>

          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="hidden md:inline-flex"
            aria-label={
              isSidebarCollapsed
                ? t("app.sidebar.expand")
                : t("app.sidebar.collapse")
            }
            aria-expanded={!isSidebarCollapsed}
            onClick={() => {
              setIsSidebarCollapsed((prev) => !prev);
            }}
          >
            <Menu className="size-5" aria-hidden="true" />
          </Button>

          <span className="text-base font-semibold tracking-tight">
            {t("app.brand")}
          </span>
        </div>

        <div className="ms-auto flex items-center gap-2">
          <HealthStatusDot />
          <Separator orientation="vertical" className="h-5" />
          <LanguageSwitch />
          <ThemeToggle />
          {user?.name && userRole ? (
            <>
              <Separator orientation="vertical" className="h-5" />
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    data-testid="user-menu-trigger"
                    aria-label={t("auth.userMenu")}
                    className="flex items-center gap-2"
                  >
                    <User className="size-4 shrink-0" aria-hidden="true" />
                    <span className="max-w-36 truncate font-medium">
                      {user.name}
                    </span>
                    <Badge variant="secondary" className="text-xs">
                      {t(`roles.${userRole}`)}
                    </Badge>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56">
                  <DropdownMenuLabel className="flex flex-col gap-0.5">
                    <span className="font-semibold">{user.name}</span>
                    <span
                      dir="ltr"
                      className="text-muted-foreground truncate text-xs font-normal"
                    >
                      {user.email}
                    </span>
                  </DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    data-testid="logout-button"
                    onClick={() => {
                      void handleLogout();
                    }}
                  >
                    <LogOut className="size-4" aria-hidden="true" />
                    <span>{t("auth.logout")}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          ) : null}
        </div>
      </header>

      <div className="flex flex-1">
        <aside
          aria-label={t("app.sidebar.label")}
          data-collapsed={isSidebarCollapsed}
          className={cn(
            "bg-card border-border hidden shrink-0 flex-col border-e transition-[width] duration-200 md:flex",
            isSidebarCollapsed ? "w-16" : "w-60",
          )}
        >
          <nav
            aria-label={t("app.sidebar.label")}
            className="flex flex-col gap-1 p-3"
          >
            {visibleNavItems.map((item) => {
              const Icon = item.icon;
              const label = t(item.labelKey);
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  aria-label={label}
                  className={({ isActive }) =>
                    cn(
                      "focus-visible:ring-ring/50 flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-[3px]",
                      isSidebarCollapsed && "justify-center px-2",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
                    )
                  }
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span className={cn(isSidebarCollapsed && "sr-only")}>
                    {label}
                  </span>
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 p-6 outline-none"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
