import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect } from "react";
import {
  apiClient,
  CSRF_COOKIE_NAME,
  CSRF_HEADER_NAME,
  extractApiError,
  notifyUnauthorized,
  readCookie,
} from "@/api/client";
import type { components, paths } from "@/api/schema";

export type SourceOut = components["schemas"]["SourceOut"];
export type SourceDetail = components["schemas"]["SourceDetail"];
export type SourceStatus = components["schemas"]["SourceStatus"];
export type SourceListPage = components["schemas"]["Page_SourceOut_"];
export type PageOut = components["schemas"]["PageOut"];
export type PageStatus = components["schemas"]["PageStatus"];
export type PageKind = components["schemas"]["PageKind"];
export type UploadResult = components["schemas"]["UploadResult"];
export type SourcesQueryParams = NonNullable<
  paths["/api/v1/sources"]["get"]["parameters"]["query"]
>;

export const SOURCES_QUERY_KEY = ["sources"] as const;

export function sourceListQueryKey(filters: {
  subjectId?: string | undefined;
  status?: SourceStatus | undefined;
}) {
  return [
    ...SOURCES_QUERY_KEY,
    "list",
    {
      subject_id: filters.subjectId ?? null,
      status: filters.status ?? null,
    },
  ] as const;
}

export function sourceDetailQueryKey(id: string) {
  return [...SOURCES_QUERY_KEY, "detail", id] as const;
}

export function sourcePagesQueryKey(id: string) {
  return [...SOURCES_QUERY_KEY, "pages", id] as const;
}

export const TERMINAL_SOURCE_STATUSES: ReadonlySet<SourceStatus> = new Set([
  "ready",
  "failed",
  "paused",
]);

export function isTerminalSourceStatus(
  status: SourceStatus | null | undefined,
): boolean {
  return status !== null && status !== undefined
    ? TERMINAL_SOURCE_STATUSES.has(status)
    : false;
}

export async function fetchSourcesPage(
  params: SourcesQueryParams,
): Promise<SourceListPage> {
  const { data, error, response } = (await apiClient.GET("/api/v1/sources", {
    params: {
      query: params,
    },
  })) as {
    data?: SourceListPage;
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined || data === undefined) {
    throw extractApiError(response.status, error);
  }
  return data;
}

export function useSources(filters: {
  subjectId?: string | undefined;
  status?: SourceStatus | undefined;
}) {
  return useInfiniteQuery({
    queryKey: sourceListQueryKey(filters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      fetchSourcesPage({
        ...(filters.subjectId ? { subject_id: filters.subjectId } : {}),
        ...(filters.status ? { status: filters.status } : {}),
        ...(pageParam ? { cursor: pageParam } : {}),
      }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

export async function fetchSourceDetail(id: string): Promise<SourceDetail> {
  const { data, error, response } = (await apiClient.GET(
    "/api/v1/sources/{id}",
    {
      params: { path: { id } },
    },
  )) as {
    data?: SourceDetail;
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined || data === undefined) {
    throw extractApiError(response.status, error);
  }
  return data;
}

export function useSourceDetail(id: string) {
  return useQuery({
    queryKey: sourceDetailQueryKey(id),
    queryFn: () => fetchSourceDetail(id),
    enabled: Boolean(id),
  });
}

export async function fetchSourcePages(id: string): Promise<PageOut[]> {
  const { data, error, response } = (await apiClient.GET(
    "/api/v1/sources/{id}/pages",
    {
      params: { path: { id } },
    },
  )) as {
    data?: PageOut[];
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined || data === undefined) {
    throw extractApiError(response.status, error);
  }
  return data;
}

export function useSourcePages(id: string) {
  return useQuery({
    queryKey: sourcePagesQueryKey(id),
    queryFn: () => fetchSourcePages(id),
    enabled: Boolean(id),
  });
}

export async function deleteSourceRequest(id: string): Promise<void> {
  const { error, response } = (await apiClient.DELETE("/api/v1/sources/{id}", {
    params: { path: { id } },
  })) as {
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined) {
    throw extractApiError(response.status, error);
  }
}

export function useDeleteSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteSourceRequest,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SOURCES_QUERY_KEY });
    },
  });
}

export interface UploadSourceInput {
  file: File;
  subject_id: string;
  title: string;
  grade?: string | undefined;
  onProgress?: ((percent: number) => void) | undefined;
}

/**
 * Uploads a workbook PDF via `XMLHttpRequest` instead of `openapi-fetch`.
 *
 * Why this bypasses `openapi-fetch`:
 * `openapi-fetch` wraps the standard Fetch API (`globalThis.fetch`), which does not expose
 * upload byte progress events (`upload.onprogress`) in browsers. Using `XMLHttpRequest`
 * directly enables real-time upload progress reporting for large PDF workbooks (up to 300 MB)
 * while still sending session cookies (`withCredentials = true`) and the double-submit
 * `X-CSRF-Token` header read from the `qbank_csrf` cookie.
 */
export function uploadSourceWithProgress(
  input: UploadSourceInput,
): Promise<UploadResult> {
  return new Promise<UploadResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/v1/sources", true);
    xhr.withCredentials = true;

    const csrfToken = readCookie(CSRF_COOKIE_NAME);
    if (csrfToken) {
      xhr.setRequestHeader(CSRF_HEADER_NAME, csrfToken);
    }

    const handleProgress = (event: ProgressEvent) => {
      if (event.lengthComputable && event.total > 0) {
        const percent = Math.min(
          100,
          Math.max(0, Math.round((event.loaded / event.total) * 100)),
        );
        input.onProgress?.(percent);
      }
    };

    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- XHR mocks in tests may omit upload
    if (xhr.upload) {
      xhr.upload.onprogress = handleProgress;
    }

    let settled = false;

    const handleLoad = () => {
      if (settled) {
        return;
      }
      settled = true;

      let parsedBody: unknown = undefined;
      if (xhr.responseText) {
        try {
          parsedBody = JSON.parse(xhr.responseText) as unknown;
        } catch {
          parsedBody = undefined;
        }
      }

      if (xhr.status === 401) {
        notifyUnauthorized("/api/v1/sources");
      }

      if (xhr.status >= 200 && xhr.status < 300 && parsedBody !== undefined) {
        input.onProgress?.(100);
        resolve(parsedBody as UploadResult);
        return;
      }

      reject(extractApiError(xhr.status || 500, parsedBody));
    };

    const handleError = () => {
      if (settled) {
        return;
      }
      settled = true;
      reject(extractApiError(xhr.status || 0, undefined));
    };

    xhr.onload = handleLoad;
    xhr.onerror = handleError;
    xhr.onabort = handleError;

    const formData = new FormData();
    formData.append("file", input.file);
    formData.append("subject_id", input.subject_id);
    formData.append("title", input.title);
    if (input.grade && input.grade.trim().length > 0) {
      formData.append("grade", input.grade.trim());
    }

    xhr.send(formData);
  });
}

export function useUploadSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: uploadSourceWithProgress,
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: SOURCES_QUERY_KEY });
      queryClient.setQueryData(sourceDetailQueryKey(result.source.id), {
        ...result.source,
        page_counts: {},
      } satisfies SourceDetail);
    },
  });
}

export function getPageImageUrl(
  sourceId: string,
  pageNumber: number,
  variant: NonNullable<
    paths["/api/v1/sources/{id}/pages/{number}/image"]["get"]["parameters"]["query"]
  >["variant"] = "display",
): string {
  return `/api/v1/sources/${encodeURIComponent(sourceId)}/pages/${String(pageNumber)}/image?variant=${variant}`;
}

interface SseProgressPayload {
  status?: SourceStatus;
  stage?: string | null;
  page_counts?: Record<string, number>;
  cost_usd?: number;
  page_count?: number | null;
  error?: string | null;
}

const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30_000;

export function useSourceEvents(
  sourceId: string | undefined,
  currentStatus: SourceStatus | null | undefined,
): void {
  const queryClient = useQueryClient();
  const isTerminal = isTerminalSourceStatus(currentStatus);

  useEffect(() => {
    if (!sourceId || isTerminal || typeof EventSource === "undefined") {
      return;
    }

    let disposed = false;
    let eventSource: EventSource | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const clearTimer = () => {
      if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
    };

    const closeStream = () => {
      clearTimer();
      if (eventSource !== null) {
        eventSource.close();
        eventSource = null;
      }
    };

    const handleEvent = (event: MessageEvent) => {
      if (disposed || typeof event.data !== "string") {
        return;
      }

      let payload: SseProgressPayload;
      try {
        payload = JSON.parse(event.data) as SseProgressPayload;
      } catch {
        return;
      }

      attempt = 0;

      queryClient.setQueryData<SourceDetail>(
        sourceDetailQueryKey(sourceId),
        (prev) => {
          if (!prev) {
            return prev;
          }
          return {
            ...prev,
            ...(payload.status !== undefined ? { status: payload.status } : {}),
            ...(payload.stage !== undefined ? { stage: payload.stage } : {}),
            ...(payload.page_counts !== undefined
              ? { page_counts: payload.page_counts }
              : {}),
            ...(payload.cost_usd !== undefined
              ? { cost_usd: payload.cost_usd }
              : {}),
            ...(payload.page_count !== undefined
              ? { page_count: payload.page_count }
              : {}),
            ...(payload.error !== undefined ? { error: payload.error } : {}),
          };
        },
      );

      if (isTerminalSourceStatus(payload.status)) {
        disposed = true;
        closeStream();
      }
    };

    const connect = () => {
      if (disposed) {
        return;
      }

      const es = new EventSource(
        `/api/v1/sources/${encodeURIComponent(sourceId)}/events`,
        { withCredentials: true },
      );
      eventSource = es;

      es.onmessage = handleEvent;
      if (typeof es.addEventListener === "function") {
        es.addEventListener("progress", handleEvent as EventListener);
        es.addEventListener("message", handleEvent as EventListener);
      }

      es.onerror = () => {
        if (disposed) {
          return;
        }
        if (eventSource !== null) {
          eventSource.close();
          eventSource = null;
        }
        const delay = Math.min(
          INITIAL_BACKOFF_MS * 2 ** attempt,
          MAX_BACKOFF_MS,
        );
        attempt += 1;
        clearTimer();
        reconnectTimer = setTimeout(() => {
          connect();
        }, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      closeStream();
    };
  }, [isTerminal, queryClient, sourceId]);
}
