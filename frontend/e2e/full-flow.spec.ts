import { expect, test } from "@playwright/test";
import { arabicDigits, login, SUBJECT_NAME, t } from "./helpers";

const EDITED_STEM = "ما وظيفة الميتوكوندريا الرئيسية في الخَلِيَّةِ؟";
const QUESTION_COUNT = 8;
const EXAM_TITLE = "امتحان الأحياء النهائي";
const SCHOOL_NAME = "مدرسة النور النموذجية";
const VERSION_A = "أ";

test.describe.configure({ mode: "serial" });

test("editor uploads the workbook and extraction finishes", async ({
  page,
}) => {
  await login(page, "editor");
  await page
    .getByRole("button", { name: t("sources.uploadWorkbook") })
    .first()
    .click();
  const dialog = page.getByRole("dialog", {
    name: t("sources.upload.dialogTitle"),
  });
  await dialog
    .getByLabel(t("sources.upload.fileLabel"), { exact: true })
    .setInputFiles(process.env.E2E_WORKBOOK ?? "");
  await dialog
    .getByLabel(t("sources.upload.subjectLabel"))
    .selectOption({ label: SUBJECT_NAME });
  await dialog
    .getByRole("button", { name: t("sources.upload.submit") })
    .click();
  await expect(
    page.getByText(t("sources.status.ready"), { exact: true }),
  ).toBeVisible({
    timeout: 120_000,
  });
  // Every page was rendered, extracted and validated, and the grid shows them without a reload.
  for (const stage of ["rendered", "extracted", "validated"]) {
    await expect(
      page.getByRole("progressbar", {
        name: t(`sources.detail.stages.${stage}`),
      }),
    ).toHaveAttribute("aria-valuenow", "2");
  }
  await expect(
    page.getByRole("button", {
      name: t("sources.detail.pageNumber", { number: 2 }),
    }),
  ).toBeVisible();
});

test("editor reviews, edits and approves every question", async ({ page }) => {
  await login(page, "editor");
  await page.getByRole("link", { name: "workbook" }).click();
  await page
    .getByRole("link", { name: t("sources.detail.review"), exact: true })
    .click();

  const queue = page.getByRole("listbox", { name: t("review.queue.label") });
  await expect(queue.getByRole("option")).toHaveCount(QUESTION_COUNT);

  // Open a question from page 2 and check that its regions are drawn on the page canvas.
  await queue.getByRole("option", { name: /^7 / }).click();
  await expect(
    page.getByRole("heading", { name: "7", level: 2 }),
  ).toBeVisible();
  const canvas = page.getByRole("img", { name: t("pageCanvas.pageAlt") });
  await expect(canvas).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^question \d/ }).first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^stimulus / })).toBeVisible();

  // Edit the first stem (keeps its tashkeel for the bank search) and save.
  await queue.getByRole("option", { name: /^1 / }).click();
  await expect(page.getByRole("button", { name: /^figure / })).toBeVisible();
  await page
    .getByRole("textbox", { name: t("review.fields.stem") })
    .fill(EDITED_STEM);
  await page.getByRole("button", { name: t("review.editor.save") }).click();
  await expect(
    page.getByText(t("review.editor.version", { version: 2 })),
  ).toBeVisible();

  // Select all eight and approve them in one go.
  for (let n = 1; n <= QUESTION_COUNT; n++) {
    await page
      .getByRole("checkbox", { name: t("review.bulk.select", { label: n }) })
      .check();
  }
  await page
    .getByTestId("bulk-bar")
    .getByRole("button", { name: t("review.actions.approve") })
    .click();
  await expect(
    page.getByText(t("review.bulk.result", { ok: QUESTION_COUNT, failed: 0 })),
  ).toBeVisible();
  await expect(
    queue.getByRole("option", {
      name: new RegExp(t("review.status.approved")),
    }),
  ).toHaveCount(QUESTION_COUNT);
});

test("teacher finds a question in the bank ignoring tashkeel", async ({
  page,
}) => {
  await login(page, "teacher");
  await page.goto("/bank");
  await page
    .getByLabel(t("bank.search.subjectSelect"))
    .selectOption({ label: SUBJECT_NAME });
  await page.getByPlaceholder(t("bank.search.placeholder")).fill("الخلية");
  const result = page.getByRole("article").filter({ hasText: "الميتوكوندريا" });
  await expect(result).toBeVisible();
  await result.click();
  await expect(page.getByRole("dialog")).toContainText("الميتوكوندريا");
});

test("teacher builds an exam, exports it and sees it go stale", async ({
  page,
}) => {
  await login(page, "teacher");

  // Create the exam.
  await page.goto("/exams");
  await page
    .getByRole("button", { name: t("exams.list.create"), exact: true })
    .first()
    .click();
  const create = page.getByRole("dialog", {
    name: t("exams.list.createTitle"),
  });
  await create
    .getByLabel(t("exams.list.subject"))
    .selectOption({ label: SUBJECT_NAME });
  await create.getByLabel(t("exams.list.examTitle")).fill(EXAM_TITLE);
  await create
    .getByRole("button", { name: t("exams.list.createSubmit") })
    .click();
  const removeButtons = page.getByRole("button", { name: /^إزالة السؤال / });
  await expect(
    page.getByRole("tablist", { name: t("exams.builder.toolsPane") }),
  ).toBeVisible();

  // Bank tab: a tashkeel-free search finds the stem written with tashkeel; add three questions.
  const bankSearch = page.getByRole("searchbox", {
    name: t("exams.bank.search"),
  });
  await bankSearch.fill("الخلية");
  await expect(
    page.getByText(t("exams.bank.resultCount", { count: 1 })),
  ).toBeVisible();
  await page
    .getByRole("button", { name: /^إضافة السؤال: .*الميتوكوندريا/ })
    .click();
  await bankSearch.clear();
  await page
    .getByRole("button", { name: /^إضافة السؤال: .*العضيات التالية/ })
    .click();
  await page
    .getByRole("button", { name: /^إضافة السؤال: .*يمثل الشكل المقابل/ })
    .click();
  await expect(removeButtons).toHaveCount(3);
  // The figure question renders its image for a teacher too (no "image unavailable" box).
  await expect(
    page.getByRole("img", { name: t("qmd.missingAsset") }),
  ).toHaveCount(0);

  // Blueprint tab: one more row of two questions.
  await page.getByRole("tab", { name: t("exams.tabs.blueprint") }).click();
  await page
    .getByRole("spinbutton", { name: t("exams.blueprint.count") })
    .fill("2");
  const panel = page.getByRole("tabpanel");
  await panel
    .getByRole("button", { name: t("exams.blueprint.preview"), exact: true })
    .click();
  await panel
    .getByRole("button", { name: t("exams.blueprint.apply"), exact: true })
    .click();
  const confirm = page.getByRole("dialog", {
    name: t("exams.blueprint.confirmTitle"),
  });
  await confirm
    .getByRole("button", { name: t("exams.blueprint.apply"), exact: true })
    .click();
  await expect(confirm).toBeHidden();
  await expect.poll(() => removeButtons.count()).toBeGreaterThanOrEqual(5);
  const afterBlueprint = await removeButtons.count();

  // AI tab: the scripted fake LLM answers with a plan and a selection.
  await page.getByRole("tab", { name: t("exams.tabs.ai") }).click();
  await page
    .getByRole("textbox", { name: t("exams.ai.promptLabel") })
    .fill("امتحان قصير بسؤالين متنوعين");
  await page
    .getByRole("button", { name: t("exams.ai.compose"), exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: t("exams.ai.proposal") }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: t("exams.ai.apply"), exact: true })
    .click();
  await expect(page.getByText(t("exams.ai.applied"))).toBeVisible();
  await expect
    .poll(() => removeButtons.count())
    .toBeGreaterThan(afterBlueprint);

  // Settings tab: school name and Arabic-Indic digits.
  await page.getByRole("tab", { name: t("exams.tabs.settings") }).click();
  await page
    .getByRole("textbox", { name: t("exams.settings.schoolName") })
    .fill(SCHOOL_NAME);
  await page
    .getByRole("combobox", { name: t("exams.settings.digits") })
    .selectOption({ label: t("exams.settings.digitsArabic") });
  await expect(page.getByText(t("exams.settings.saved"))).toBeVisible();

  // Versions & export tab: two versions, then version A as exam PDF, answer key PDF and DOCX.
  await page.getByRole("tab", { name: t("exams.tabs.versions") }).click();
  await page.getByRole("spinbutton", { name: t("exports.count") }).fill("2");
  await page
    .getByRole("button", { name: t("exports.generateVersions") })
    .click();
  const versions = page.getByRole("group", { name: t("exports.versions") });
  await versions.getByRole("checkbox", { name: VERSION_A }).check();
  const kinds = page.getByRole("group", { name: t("exports.kinds") });
  await kinds
    .getByRole("checkbox", { name: t("exports.answer_key_pdf") })
    .check();
  await kinds.getByRole("checkbox", { name: t("exports.docx") }).check();
  await page.getByRole("button", { name: t("exports.generate") }).click();

  const downloads: Record<string, { type: RegExp; magic: string }> = {
    pdf: { type: /^application\/pdf/, magic: "%PDF" },
    answer_key_pdf: { type: /^application\/pdf/, magic: "%PDF" },
    docx: {
      type: /^application\/vnd\.openxmlformats-officedocument\.wordprocessingml\.document/,
      magic: "PK",
    },
  };
  for (const [kind, expected] of Object.entries(downloads)) {
    const row = page
      .getByRole("listitem")
      .filter({ hasText: t(`exports.${kind}`) })
      .filter({ hasText: VERSION_A });
    await expect(
      row.getByText(t("exports.ready"), { exact: false }),
    ).toBeVisible({ timeout: 120_000 });
    const href = await row
      .getByRole("link", { name: t("exports.download") })
      .getAttribute("href");
    expect(href).toBeTruthy();
    const response = await page.request.get(href ?? "");
    expect(response.ok()).toBe(true);
    expect(response.headers()["content-type"] ?? "").toMatch(expected.type);
    const body = await response.body();
    expect(body.length).toBeGreaterThan(1000);
    expect(body.subarray(0, expected.magic.length).toString("latin1")).toBe(
      expected.magic,
    );
  }

  // Editing the exam makes versions and exports stale.
  const points = page.getByRole("spinbutton", {
    name: t("exams.builder.pointsFor", { n: arabicDigits(1) }),
  });
  await points.fill("3");
  await points.blur();
  await expect(page.getByText(t("exams.builder.staleWarning"))).toBeVisible();
  await expect(
    page
      .getByRole("listitem")
      .filter({ hasText: t("exports.pdf") })
      .getByText(t("exports.stale")),
  ).toBeVisible();

  // The exam list shows the two versions with the stale badge.
  // (Applying the AI proposal also renames the exam to the proposed title.)
  const finalTitle = await page
    .getByRole("textbox", { name: t("exams.builder.examTitle") })
    .inputValue();
  await page.getByRole("link", { name: t("exams.builder.back") }).click();
  const row = page.getByRole("row").filter({ hasText: finalTitle });
  await expect(row.getByText(t("exams.versions.stale"))).toBeVisible();
  await expect(row.getByRole("cell").nth(5)).toHaveText(/2/);
});
