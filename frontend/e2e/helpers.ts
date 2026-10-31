import { expect, type Page } from "@playwright/test";
import ar from "../src/i18n/ar.json" with { type: "json" };

export const PASSWORD = "demo1234";
export const SUBJECT_NAME = "Biology / الأحياء";

/** Look up an Arabic UI string so the suite never hard-codes copy that i18n owns. */
export function t(
  key: string,
  params: Record<string, string | number> = {},
): string {
  let node: unknown = ar;
  for (const part of key.split(".")) {
    if (typeof node !== "object" || node === null || !(part in node)) {
      throw new Error(`Missing i18n key: ${key}`);
    }
    node = (node as Record<string, unknown>)[part];
  }
  if (typeof node !== "string") {
    throw new Error(`i18n key is not a string: ${key}`);
  }
  return node.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
    String(params[name] ?? ""),
  );
}

export type DemoRole = "admin" | "editor" | "teacher";

export async function login(page: Page, role: DemoRole): Promise<void> {
  await page.goto("/login");
  await page.getByLabel(t("auth.login.emailLabel")).fill(`${role}@demo.local`);
  await page.getByLabel(t("auth.login.passwordLabel")).fill(PASSWORD);
  await page
    .getByRole("button", { name: t("auth.login.submit"), exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: t("pages.sources.title") }),
  ).toBeVisible();
}

export async function logout(page: Page): Promise<void> {
  await page.getByRole("button", { name: t("auth.userMenu") }).click();
  await page.getByRole("menuitem", { name: t("auth.logout") }).click();
  await expect(page).toHaveURL(/\/login/);
}

/** Western digits to Arabic-Indic digits, as the exam pane shows them once digits=arabic. */
export function arabicDigits(value: number): string {
  return String(value).replace(/\d/g, (digit) =>
    String.fromCharCode(0x0660 + Number(digit)),
  );
}
