import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "@/api/schema";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
export const CSRF_COOKIE_NAME = "qbank_csrf";
export const CSRF_HEADER_NAME = "X-CSRF-Token";

export interface ProblemDetails {
  type?: string | undefined;
  title?: string | undefined;
  status?: number | undefined;
  detail?: string | undefined;
  code?: string | undefined;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string | undefined;
  readonly detail?: string | undefined;
  /** The full problem+json body, for extras such as `current` or `issues`. */
  readonly body?: Record<string, unknown> | undefined;

  constructor(
    status: number,
    message: string,
    code?: string,
    detail?: string,
    body?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.body = body;
  }
}

export function extractApiError(status: number, errorBody: unknown): ApiError {
  if (typeof errorBody === "object" && errorBody !== null) {
    const record = errorBody as Record<string, unknown>;
    const code = typeof record.code === "string" ? record.code : undefined;
    const detail =
      typeof record.detail === "string" ? record.detail : undefined;
    const title = typeof record.title === "string" ? record.title : undefined;
    const message = detail ?? title ?? `Request failed (${String(status)})`;
    return new ApiError(status, message, code, detail, record);
  }
  return new ApiError(status, `Request failed (${String(status)})`);
}

type UnauthorizedListener = (path?: string) => void;
const unauthorizedListeners = new Set<UnauthorizedListener>();

export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => {
    unauthorizedListeners.delete(listener);
  };
}

export function notifyUnauthorized(path?: string): void {
  for (const listener of unauthorizedListeners) {
    listener(path);
  }
}

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
  onResponse({ response, schemaPath }) {
    if (response.status === 401 && schemaPath !== "/api/v1/auth/login") {
      notifyUnauthorized(schemaPath);
    }
    return response;
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
