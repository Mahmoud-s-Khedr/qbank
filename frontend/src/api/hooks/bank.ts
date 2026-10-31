import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { apiClient, extractApiError } from "@/api/client";
import type { components, operations } from "@/api/schema";

export type BankQuestionOut = components["schemas"]["BankQuestionOut"];
export type BankSearchOut = components["schemas"]["BankSearchOut"];
export type BankFacets = components["schemas"]["BankFacets"];
export type BankStatsOut = components["schemas"]["BankStatsOut"];
export type TagCount = components["schemas"]["TagCount"];
export type ChapterFacet = components["schemas"]["ChapterFacet"];
export type LessonFacet = components["schemas"]["LessonFacet"];
export type SourceFacet = components["schemas"]["SourceFacet"];
export type QuestionOut = components["schemas"]["QuestionOut"];
export type QuestionEventOut = components["schemas"]["QuestionEventOut"];
export type BulkIn = components["schemas"]["BulkIn"];
export type BulkOut = components["schemas"]["BulkOut"];
export type BulkResult = components["schemas"]["BulkResult"];
export type BulkMetadata = components["schemas"]["BulkMetadata"];
export type QuestionsMove = components["schemas"]["QuestionsMove"];
export type QuestionsMoveOut = components["schemas"]["QuestionsMoveOut"];
export type ExamSummary = components["schemas"]["ExamSummary"];
export type Page_ExamSummary_ = components["schemas"]["Page_ExamSummary_"];
export type ItemsIn = components["schemas"]["ItemsIn"];
export type ExamDetail = components["schemas"]["ExamDetail"];

export type BankSort = "relevance" | "newest" | "difficulty" | "source_order";

export interface BankSearchParams {
  q?: string | null;
  subject_id?: string | null;
  chapter_ids?: string[] | null;
  lesson_ids?: string[] | null;
  types?: string[] | null;
  difficulty_min?: number | null;
  difficulty_max?: number | null;
  statuses?: string[] | null;
  source_ids?: string[] | null;
  tags?: string[] | null;
  has_figure?: boolean | null;
  has_answer?: boolean | null;
  exam_title?: string | null;
  exclude_duplicates?: boolean;
  facets?: boolean;
  sort?: BankSort | null;
  limit?: number;
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

export const BANK_SEARCH_KEY = ["bank", "search"] as const;
export const BANK_STATS_KEY = ["bank", "stats"] as const;
export const BANK_TAGS_KEY = ["bank", "tags"] as const;
export const EXAMS_DRAFT_KEY = ["exams", "draft"] as const;

export async function fetchBankSearch(
  params: BankSearchParams,
  cursor?: string | null,
): Promise<BankSearchOut> {
  const query: operations["search_questions_api_v1_bank_questions_get"]["parameters"]["query"] =
    {
      q: params.q ?? null,
      subject_id: params.subject_id ?? null,
      chapter_ids:
        params.chapter_ids && params.chapter_ids.length > 0
          ? params.chapter_ids
          : null,
      lesson_ids:
        params.lesson_ids && params.lesson_ids.length > 0
          ? params.lesson_ids
          : null,
      types: params.types && params.types.length > 0 ? params.types : null,
      difficulty_min: params.difficulty_min ?? null,
      difficulty_max: params.difficulty_max ?? null,
      statuses:
        params.statuses && params.statuses.length > 0 ? params.statuses : null,
      source_ids:
        params.source_ids && params.source_ids.length > 0
          ? params.source_ids
          : null,
      tags: params.tags && params.tags.length > 0 ? params.tags : null,
      has_figure: params.has_figure ?? null,
      has_answer: params.has_answer ?? null,
      exam_title: params.exam_title ?? null,
      exclude_duplicates: params.exclude_duplicates ?? true,
      facets: params.facets ?? true,
      sort: params.sort ?? (params.q ? "relevance" : "newest"),
      cursor: cursor ?? null,
      limit: params.limit ?? 20,
    };

  const res = (await apiClient.GET("/api/v1/bank/questions", {
    params: { query },
  })) as Envelope<BankSearchOut>;
  return unwrap(res);
}

export function useBankSearch(params: BankSearchParams) {
  return useInfiniteQuery({
    queryKey: [...BANK_SEARCH_KEY, params],
    queryFn: ({ pageParam }) =>
      fetchBankSearch(params, pageParam as string | null | undefined),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  });
}

const EMPTY_STATS: BankStatsOut = {
  total: 0,
  by_status: {},
  by_type: {},
  by_difficulty: {},
  approved_by_chapter: [],
  approved_by_lesson: [],
};

export function useBankStats(subjectId?: string | null) {
  return useQuery({
    queryKey: [...BANK_STATS_KEY, subjectId ?? "all"],
    queryFn: async () => {
      const res = (await apiClient.GET("/api/v1/bank/stats", {
        params: {
          query: {
            subject_id: subjectId ?? null,
          },
        },
      })) as Envelope<BankStatsOut>;
      const rawData = unwrap(res) as unknown;
      if (
        !rawData ||
        typeof (rawData as { total?: unknown }).total !== "number"
      ) {
        return EMPTY_STATS;
      }
      return rawData as BankStatsOut;
    },
  });
}

export function useBankTags(subjectId?: string | null, q?: string) {
  return useQuery({
    queryKey: [...BANK_TAGS_KEY, subjectId ?? "all", q ?? ""],
    queryFn: async () => {
      const res = (await apiClient.GET("/api/v1/bank/tags", {
        params: {
          query: {
            subject_id: subjectId ?? null,
            q: q ?? null,
            limit: 30,
          },
        },
      })) as Envelope<TagCount[]>;
      const data = unwrap(res);
      if (!Array.isArray(data)) {
        return [] as TagCount[];
      }
      return data;
    },
  });
}

export function useQuestion(id: string | null) {
  return useQuery({
    queryKey: ["questions", id],
    queryFn: async () => {
      if (!id) throw new Error("No question ID");
      const res = (await apiClient.GET("/api/v1/questions/{id}", {
        params: { path: { id } },
      })) as Envelope<QuestionOut>;
      return unwrap(res);
    },
    enabled: Boolean(id),
  });
}

export function useQuestionHistory(id: string | null) {
  return useQuery({
    queryKey: ["questions", id, "history"],
    queryFn: async () => {
      if (!id) return [];
      const res = (await apiClient.GET("/api/v1/questions/{id}/history", {
        params: { path: { id } },
      })) as Envelope<QuestionEventOut[]>;
      return unwrap(res);
    },
    enabled: Boolean(id),
  });
}

export function useBulkQuestions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: BulkIn) => {
      const res = (await apiClient.POST("/api/v1/questions/bulk", {
        body: data,
      })) as Envelope<BulkOut>;
      return unwrap(res);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BANK_SEARCH_KEY });
      void queryClient.invalidateQueries({ queryKey: BANK_STATS_KEY });
      void queryClient.invalidateQueries({ queryKey: ["questions"] });
    },
  });
}

export function useMoveQuestions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: QuestionsMove) => {
      const res = (await apiClient.POST("/api/v1/questions/move", {
        body: data,
      })) as Envelope<QuestionsMoveOut>;
      return unwrap(res);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: BANK_SEARCH_KEY });
      void queryClient.invalidateQueries({ queryKey: BANK_STATS_KEY });
      void queryClient.invalidateQueries({ queryKey: ["subjects"] });
    },
  });
}

export function useDraftExams() {
  return useQuery({
    queryKey: EXAMS_DRAFT_KEY,
    queryFn: async () => {
      const res = (await apiClient.GET("/api/v1/exams", {
        params: {
          query: {
            status: "draft",
            limit: 100,
          },
        },
      })) as Envelope<Page_ExamSummary_>;
      return unwrap(res);
    },
  });
}

export function useAddItemsToExam() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ examId, data }: { examId: string; data: ItemsIn }) => {
      const res = (await apiClient.POST("/api/v1/exams/{id}/items", {
        params: { path: { id: examId } },
        body: data,
      })) as Envelope<ExamDetail>;
      return unwrap(res);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: EXAMS_DRAFT_KEY });
    },
  });
}
