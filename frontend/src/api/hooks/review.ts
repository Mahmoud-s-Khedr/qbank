import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { apiClient, extractApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type QuestionOut = components["schemas"]["QuestionOut"];
export type QuestionPatch = components["schemas"]["QuestionPatch"];
export type QuestionCreate = components["schemas"]["QuestionCreate"];
export type QuestionType = QuestionCreate["type"];
export type ChoiceIn = components["schemas"]["ChoiceIn"];
export type QueueItem = components["schemas"]["QueueItem"];
export type ReviewQueue = components["schemas"]["ReviewQueue"];
export type StimulusOut = components["schemas"]["StimulusOut"];
export type IssueOut = components["schemas"]["ValidationIssueOut"];
export type BulkIn = components["schemas"]["BulkIn"];
export type BulkOut = components["schemas"]["BulkOut"];
export type AssetOut = components["schemas"]["AssetOut"];
export type ProposalDetail = components["schemas"]["ProposalDetail"];
export type AcceptOut = components["schemas"]["AcceptOut"];
export type QuestionEventOut = components["schemas"]["QuestionEventOut"];
export type JobOut = components["schemas"]["JobOut"];
export type SplitOut = components["schemas"]["SplitOut"];
export type SplitIn = components["schemas"]["SplitIn"];
export type DraftQuestion = components["schemas"]["DraftQuestion"];
export type PageDetail = components["schemas"]["PageDetail"];

export const REVIEW_KEY = ["review"] as const;

export type QueueStatusFilter =
  "" | "draft" | "needs_review" | "approved" | "rejected";
export type QueueSeverityFilter = "" | "error" | "warning";
export type QueueSort = "page" | "severity" | "confidence";

export interface QueueFilters {
  status: QueueStatusFilter;
  severity: QueueSeverityFilter;
  sort: QueueSort;
}

interface Envelope<T> {
  data?: T | undefined;
  error?: unknown;
  response: Response;
}

function unwrap<T>(result: Envelope<T>): T {
  if (
    !result.response.ok ||
    result.error !== undefined ||
    result.data === undefined
  ) {
    throw extractApiError(result.response.status, result.error);
  }
  return result.data;
}

function unwrapVoid(result: Envelope<unknown>): void {
  if (!result.response.ok || result.error !== undefined) {
    throw extractApiError(result.response.status, result.error);
  }
}

export const queueKey = (sourceId: string, filters: QueueFilters) =>
  [...REVIEW_KEY, "queue", sourceId, filters] as const;
export const questionKey = (id: string) =>
  [...REVIEW_KEY, "question", id] as const;
export const sourceQuestionsKey = (sourceId: string) =>
  [...REVIEW_KEY, "questions", sourceId] as const;
export const sourceStimuliKey = (sourceId: string) =>
  [...REVIEW_KEY, "stimuli", sourceId] as const;
export const pageDetailKey = (sourceId: string, n: number) =>
  [...REVIEW_KEY, "page", sourceId, n] as const;

export function fetchReviewQueue(
  sourceId: string,
  filters: QueueFilters,
): Promise<ReviewQueue> {
  return apiClient
    .GET("/api/v1/sources/{id}/review-queue", {
      params: {
        path: { id: sourceId },
        query: {
          sort: filters.sort,
          ...(filters.status ? { status: filters.status } : {}),
          ...(filters.severity ? { severity: filters.severity } : {}),
        },
      },
    })
    .then((r) => unwrap<ReviewQueue>(r as Envelope<ReviewQueue>));
}

export function useReviewQueue(sourceId: string, filters: QueueFilters) {
  return useQuery({
    queryKey: queueKey(sourceId, filters),
    queryFn: () => fetchReviewQueue(sourceId, filters),
    enabled: Boolean(sourceId),
  });
}

export function fetchQuestion(id: string): Promise<QuestionOut> {
  return apiClient
    .GET("/api/v1/questions/{id}", { params: { path: { id } } })
    .then((r) => unwrap<QuestionOut>(r as Envelope<QuestionOut>));
}

export function useQuestion(id: string | undefined) {
  return useQuery({
    queryKey: questionKey(id ?? ""),
    queryFn: () => fetchQuestion(id ?? ""),
    enabled: Boolean(id),
  });
}

export function prefetchQuestion(queryClient: QueryClient, id: string) {
  void queryClient
    .query({
      queryKey: questionKey(id),
      queryFn: () => fetchQuestion(id),
      staleTime: 30_000,
    })
    .catch(() => undefined);
}

export function useSourceQuestions(sourceId: string) {
  return useQuery({
    queryKey: sourceQuestionsKey(sourceId),
    queryFn: () =>
      apiClient
        .GET("/api/v1/sources/{id}/questions", {
          params: { path: { id: sourceId } },
        })
        .then((r) => unwrap<QuestionOut[]>(r as Envelope<QuestionOut[]>)),
    enabled: Boolean(sourceId),
  });
}

export function useSourceStimuli(sourceId: string) {
  return useQuery({
    queryKey: sourceStimuliKey(sourceId),
    queryFn: () =>
      apiClient
        .GET("/api/v1/sources/{id}/stimuli", {
          params: { path: { id: sourceId } },
        })
        .then((r) => unwrap<StimulusOut[]>(r as Envelope<StimulusOut[]>)),
    enabled: Boolean(sourceId),
  });
}

export function usePageDetail(
  sourceId: string,
  pageNumber: number | undefined,
) {
  return useQuery({
    queryKey: pageDetailKey(sourceId, pageNumber ?? 0),
    queryFn: () =>
      apiClient
        .GET("/api/v1/sources/{id}/pages/{number}", {
          params: { path: { id: sourceId, number: pageNumber ?? 0 } },
        })
        .then((r) => unwrap<PageDetail>(r as Envelope<PageDetail>)),
    enabled: Boolean(sourceId) && pageNumber !== undefined,
  });
}

export function useQuestionHistory(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: [...REVIEW_KEY, "history", id ?? ""],
    queryFn: () =>
      apiClient
        .GET("/api/v1/questions/{id}/history", {
          params: { path: { id: id ?? "" } },
        })
        .then((r) =>
          unwrap<QuestionEventOut[]>(r as Envelope<QuestionEventOut[]>),
        ),
    enabled: Boolean(id) && enabled,
  });
}

/** A mutation that refreshes every review query when it settles. */
function useReviewMutation<V, R>(fn: (variables: V) => Promise<R>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (result: R) => {
      if (isQuestionOut(result)) {
        queryClient.setQueryData(questionKey(result.id), result);
      }
      void queryClient.invalidateQueries({ queryKey: REVIEW_KEY });
    },
  });
}

export function isQuestionOut(value: unknown): value is QuestionOut {
  return (
    typeof value === "object" &&
    value !== null &&
    "stem" in value &&
    "version" in value &&
    "id" in value
  );
}

export interface PatchVariables {
  id: string;
  patch: QuestionPatch;
}

export function usePatchQuestion() {
  return useReviewMutation(({ id, patch }: PatchVariables) =>
    apiClient
      .PATCH("/api/v1/questions/{id}", {
        params: { path: { id } },
        body: patch,
      })
      .then((r) => unwrap<QuestionOut>(r as Envelope<QuestionOut>)),
  );
}

export interface ApproveVariables {
  id: string;
  version?: number | undefined;
  force?: boolean | undefined;
}

export function useApproveQuestion() {
  return useReviewMutation(({ id, version, force }: ApproveVariables) =>
    apiClient
      .POST("/api/v1/questions/{id}/approve", {
        params: { path: { id } },
        body: {
          force: force ?? false,
          ...(version !== undefined ? { version } : {}),
        },
      })
      .then((r) => unwrap<QuestionOut>(r as Envelope<QuestionOut>)),
  );
}

export interface RejectVariables {
  id: string;
  version?: number | undefined;
  reason?: string | undefined;
}

export function useRejectQuestion() {
  return useReviewMutation(({ id, version, reason }: RejectVariables) =>
    apiClient
      .POST("/api/v1/questions/{id}/reject", {
        params: { path: { id } },
        body: {
          ...(reason ? { reason } : {}),
          ...(version !== undefined ? { version } : {}),
        },
      })
      .then((r) => unwrap<QuestionOut>(r as Envelope<QuestionOut>)),
  );
}

export function useReopenQuestion() {
  return useReviewMutation(
    ({ id, version }: { id: string; version?: number }) =>
      apiClient
        .POST("/api/v1/questions/{id}/reopen", {
          params: { path: { id } },
          body: version !== undefined ? { version } : {},
        })
        .then((r) => unwrap<QuestionOut>(r as Envelope<QuestionOut>)),
  );
}

export function useBulkQuestions() {
  return useReviewMutation((body: BulkIn) =>
    apiClient
      .POST("/api/v1/questions/bulk", { body })
      .then((r) => unwrap<BulkOut>(r as Envelope<BulkOut>)),
  );
}

export function useSplitQuestion() {
  return useReviewMutation(({ id, body }: { id: string; body: SplitIn }) =>
    apiClient
      .POST("/api/v1/questions/{id}/split", {
        params: { path: { id } },
        body,
      })
      .then((r) => unwrap<SplitOut>(r as Envelope<SplitOut>)),
  );
}

export function useMergeQuestions() {
  return useReviewMutation((ids: string[]) =>
    apiClient
      .POST("/api/v1/questions/merge", { body: { ids } })
      .then((r) => unwrap<QuestionOut>(r as Envelope<QuestionOut>)),
  );
}

export function useSetIssueResolved() {
  return useReviewMutation(
    ({ id, resolved }: { id: string; resolved: boolean }) =>
      (resolved
        ? apiClient.POST("/api/v1/issues/{id}/resolve", {
            params: { path: { id } },
          })
        : apiClient.POST("/api/v1/issues/{id}/unresolve", {
            params: { path: { id } },
          })
      ).then((r) => unwrap<IssueOut>(r as Envelope<IssueOut>)),
  );
}

export function useAddFigure() {
  return useReviewMutation(
    ({ id, pageId, box }: { id: string; pageId: string; box: number[] }) =>
      apiClient
        .POST("/api/v1/questions/{id}/figures", {
          params: { path: { id } },
          body: { page_id: pageId, box },
        })
        .then((r) => unwrap<AssetOut>(r as Envelope<AssetOut>)),
  );
}

export function useRecropFigure() {
  return useReviewMutation(
    ({ assetId, box }: { assetId: string; box: number[] }) =>
      apiClient
        .PUT("/api/v1/assets/{id}/region", {
          params: { path: { id: assetId } },
          body: { box },
        })
        .then((r) => unwrap<AssetOut>(r as Envelope<AssetOut>)),
  );
}

export function useDeleteFigure() {
  return useReviewMutation(({ id, assetId }: { id: string; assetId: string }) =>
    apiClient
      .DELETE("/api/v1/questions/{id}/figures/{asset_id}", {
        params: { path: { id, asset_id: assetId } },
      })
      .then((r) => {
        unwrapVoid(r);
      }),
  );
}

export function usePatchStimulus() {
  return useReviewMutation(({ id, content }: { id: string; content: string }) =>
    apiClient
      .PATCH("/api/v1/stimuli/{id}", {
        params: { path: { id } },
        body: { content },
      })
      .then((r) => unwrap<StimulusOut>(r as Envelope<StimulusOut>)),
  );
}

export function useCreateQuestion() {
  return useReviewMutation((body: QuestionCreate) =>
    apiClient
      .POST("/api/v1/questions", { body })
      .then((r) => unwrap<QuestionOut>(r as Envelope<QuestionOut>)),
  );
}

export function useExtractRegion() {
  return useMutation({
    mutationFn: ({
      sourceId,
      pageNumber,
      box,
    }: {
      sourceId: string;
      pageNumber: number;
      box: number[];
    }) =>
      apiClient
        .POST("/api/v1/sources/{id}/pages/{number}/extract-region", {
          params: { path: { id: sourceId, number: pageNumber } },
          body: { box },
        })
        .then((r) => unwrap<DraftQuestion>(r as Envelope<DraftQuestion>)),
  });
}

export function useStartReextract() {
  return useMutation({
    mutationFn: ({
      sourceId,
      pageNumber,
      model,
    }: {
      sourceId: string;
      pageNumber: number;
      model?: string | undefined;
    }) =>
      apiClient
        .POST("/api/v1/sources/{id}/pages/{number}/reextract", {
          params: { path: { id: sourceId, number: pageNumber } },
          body: model ? { model } : {},
        })
        .then((r) =>
          unwrap<components["schemas"]["ReextractOut"]>(
            r as Envelope<components["schemas"]["ReextractOut"]>,
          ),
        ),
  });
}

export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: [...REVIEW_KEY, "job", jobId ?? ""],
    queryFn: () =>
      apiClient
        .GET("/api/v1/jobs/{id}", { params: { path: { id: jobId ?? "" } } })
        .then((r) => unwrap<JobOut>(r as Envelope<JobOut>)),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ready" || status === "failed" ? false : 1500;
    },
  });
}

export function useProposal(proposalId: string | undefined) {
  return useQuery({
    queryKey: [...REVIEW_KEY, "proposal", proposalId ?? ""],
    queryFn: () =>
      apiClient
        .GET("/api/v1/page-proposals/{id}", {
          params: { path: { id: proposalId ?? "" } },
        })
        .then((r) => unwrap<ProposalDetail>(r as Envelope<ProposalDetail>)),
    enabled: Boolean(proposalId),
  });
}

export function useAcceptProposal() {
  return useReviewMutation(
    ({ id, numberLabels }: { id: string; numberLabels: string[] }) =>
      apiClient
        .POST("/api/v1/page-proposals/{id}/accept", {
          params: { path: { id } },
          body: { number_labels: numberLabels },
        })
        .then((r) => unwrap<AcceptOut>(r as Envelope<AcceptOut>)),
  );
}

export function useDiscardProposal() {
  return useReviewMutation((id: string) =>
    apiClient
      .POST("/api/v1/page-proposals/{id}/discard", {
        params: { path: { id } },
      })
      .then((r) =>
        unwrap<components["schemas"]["ProposalOut"]>(
          r as Envelope<components["schemas"]["ProposalOut"]>,
        ),
      ),
  );
}

export function assetImageUrl(assetId: string, version?: string): string {
  const base = `/api/v1/assets/${encodeURIComponent(assetId)}/image`;
  return version ? `${base}?v=${encodeURIComponent(version)}` : base;
}
