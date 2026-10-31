import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "@/api/schema";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
export const CSRF_COOKIE_NAME = "qbank_csrf";
export const CSRF_HEADER_NAME = "X-CSRF-Token";

export function readCookie(name: string): string | null {
  if (typeof document === "undefined" || !document.cookie) {
    return null;
  }
  const parts = document.cookie.split(";");
  for (const part of parts) {
    const trimmed = part.trim();
    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex === -1) {
      continue;
    }
    const cookieName = trimmed.slice(0, separatorIndex);
    if (cookieName === name) {
      return decodeURIComponent(trimmed.slice(separatorIndex + 1));
    }
  }
  return null;
}

export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    if (UNSAFE_METHODS.has(request.method.toUpperCase())) {
      const csrfToken = readCookie(CSRF_COOKIE_NAME);
      if (csrfToken) {
        request.headers.set(CSRF_HEADER_NAME, csrfToken);
      }
    }
    return request;
  },
};

class RelativeAwareRequest extends globalThis.Request {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    if (typeof input === "string" && input.startsWith("/")) {
      const origin =
        typeof window !== "undefined" && window.location.origin
          ? window.location.origin
          : "http://localhost";
      super(new URL(input, origin), init);
      return;
    }
    super(input, init);
  }
}

export const apiClient = createClient<paths>({
  baseUrl: "/",
  credentials: "include",
  Request: RelativeAwareRequest,
  fetch: (input: Request) => globalThis.fetch(input),
});

apiClient.use(csrfMiddleware);
