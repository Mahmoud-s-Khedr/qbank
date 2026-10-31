import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { setAppLanguage } from "@/i18n";

// findBy*/waitFor default to 1 s, which flakes on loaded machines and CI runners
// (seen with the review workspace tests while several suites ran in parallel).
configure({ asyncUtilTimeout: 5000 });

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

beforeEach(async () => {
  window.localStorage.clear();
  document.cookie = "qbank_csrf=; Max-Age=0; path=/";
  await setAppLanguage("ar");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
