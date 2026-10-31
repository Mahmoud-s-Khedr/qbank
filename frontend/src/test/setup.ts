import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import { setAppLanguage } from "@/i18n";

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
