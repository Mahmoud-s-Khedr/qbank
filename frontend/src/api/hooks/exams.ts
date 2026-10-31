import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { apiClient, extractApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type ExamDetail = components["schemas"]["ExamDetail"];
export type ExamSummary = components["schemas"]["ExamSummary"];
export type ExamSettings = components["schemas"]["ExamSettings"];
export type ExamHeader = components["schemas"]["ExamHeader"];
export type ExamLayout = components["schemas"]["ExamLayout"];
export type SectionOut = components["schemas"]["SectionOut"];
export type ItemOut = components["schemas"]["ItemOut"];
export type VersionOut = components["schemas"]["VersionOut"];
export type AnswerKey = components["schemas"]["AnswerKey"];
export type Blueprint = components["schemas"]["Blueprint"];
export type BlueprintRow = components["schemas"]["BlueprintRow"];
export type BlueprintResult = components["schemas"]["BlueprintResult"];
export type ExamProposal = components["schemas"]["ExamProposalOut"];
export type ProposalEdits = components["schemas"]["ProposalEdits"];
export type BankQuestion = components["schemas"]["BankQuestionOut"];
export type BankStats = components["schemas"]["BankStatsOut"];
export type SubjectTree = components["schemas"]["SubjectTree"];
export type TemplateOut = components["schemas"]["TemplateOut"];
export type ExamStatus = "draft" | "final" | "archived";

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

export const examKey = (id: string) => ["exam", id] as const;
export const EXAMS_KEY = ["exams"] as const;
export const examListKey = (status: string) => [...EXAMS_KEY, status] as const;

/* ------------------------------ exam list ------------------------------ */

export function useExamList(status: ExamStatus | "") {
  return useQuery({
    queryKey: examListKey(status),
    queryFn: async () =>
      unwrap(
        await apiClient.GET("/api/v1/exams", {
          params: { query: { limit: 100, ...(status ? { status } : {}) } },
        }),
      ),
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: ["templates"],
    queryFn: async () => unwrap(await apiClient.GET("/api/v1/exam-templates")),
  });
}

export function useCreateExam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["ExamIn"]) =>
      unwrap(await apiClient.POST("/api/v1/exams", { body })),
    onSuccess: (exam) => {
      qc.setQueryData(examKey(exam.id), exam);
      void qc.invalidateQueries({ queryKey: EXAMS_KEY });
    },
  });
}

export function useDuplicateExam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/duplicate", {
          params: { path: { id } },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: EXAMS_KEY });
    },
  });
}

export function useArchiveExam() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/archive", {
          params: { path: { id } },
        }),
      ),
    onSuccess: (exam) => {
      qc.setQueryData(examKey(exam.id), exam);
      void qc.invalidateQueries({ queryKey: EXAMS_KEY });
    },
  });
}

/* ------------------------------- one exam ------------------------------ */

export function useExam(id: string) {
  return useQuery({
    queryKey: examKey(id),
    queryFn: async () =>
      unwrap(
        await apiClient.GET("/api/v1/exams/{id}", { params: { path: { id } } }),
      ),
  });
}

function recount(exam: ExamDetail): ExamDetail {
  const items = exam.sections.flatMap((s) => s.items);
  return {
    ...exam,
    question_count: items.length,
    total_points: items.reduce((sum, item) => sum + item.points, 0),
  };
}

function withPoints(exam: ExamDetail, itemId: string, points: number) {
  return recount({
    ...exam,
    sections: exam.sections.map((s) => ({
      ...s,
      items: s.items.map((i) => (i.id === itemId ? { ...i, points } : i)),
    })),
  });
}

function withItemOrder(exam: ExamDetail, sectionId: string, ids: string[]) {
  return {
    ...exam,
    sections: exam.sections.map((s) => {
      if (s.id !== sectionId) return s;
      const byId = new Map(s.items.map((i) => [i.id, i] as const));
      const items = ids.flatMap((id, position) => {
        const item = byId.get(id);
        return item ? [{ ...item, position }] : [];
      });
      return { ...s, items };
    }),
  };
}

function withSectionOrder(exam: ExamDetail, ids: string[]) {
  const byId = new Map(exam.sections.map((s) => [s.id, s] as const));
  return {
    ...exam,
    sections: ids.flatMap((id, position) => {
      const section = byId.get(id);
      return section ? [{ ...section, position }] : [];
    }),
  };
}

interface Snapshot {
  previous: ExamDetail | undefined;
}

/** All the write operations on one exam. Each returns the fresh ExamDetail. */
export function useExamMutations(examId: string) {
  const qc = useQueryClient();
  const key = examKey(examId);

  const store = (exam: ExamDetail) => {
    qc.setQueryData(key, exam);
    void qc.invalidateQueries({ queryKey: EXAMS_KEY });
    // Any edit bumps the revision, which makes the exam's exports stale (see ExamExportsPanel).
    void qc.invalidateQueries({ queryKey: ["exports", examId] });
  };

  const optimistic = <V>(apply: (exam: ExamDetail, vars: V) => ExamDetail) => ({
    onMutate: async (vars: V): Promise<Snapshot> => {
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<ExamDetail>(key);
      if (previous) qc.setQueryData(key, apply(previous, vars));
      return { previous };
    },
    onError: (_error: Error, _vars: V, context: Snapshot | undefined) => {
      if (context?.previous) qc.setQueryData(key, context.previous);
    },
  });

  const rename = useMutation({
    mutationFn: async (title: string) =>
      unwrap(
        await apiClient.PATCH("/api/v1/exams/{id}", {
          params: { path: { id: examId } },
          body: { title },
        }),
      ),
    onSuccess: store,
  });

  const saveSettings = useMutation({
    mutationFn: async (settings: ExamSettings) =>
      unwrap(
        await apiClient.PATCH("/api/v1/exams/{id}", {
          params: { path: { id: examId } },
          body: { settings },
        }),
      ),
    onSuccess: store,
  });

  const addSection = useMutation({
    mutationFn: async (body: components["schemas"]["SectionIn"]) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/sections", {
          params: { path: { id: examId } },
          body,
        }),
      ),
    onSuccess: store,
  });

  const editSection = useMutation({
    mutationFn: async (vars: {
      id: string;
      body: components["schemas"]["SectionUpdate"];
    }) =>
      unwrap(
        await apiClient.PATCH("/api/v1/exam-sections/{id}", {
          params: { path: { id: vars.id } },
          body: vars.body,
        }),
      ),
    onSuccess: store,
  });

  const deleteSection = useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await apiClient.DELETE("/api/v1/exam-sections/{id}", {
          params: { path: { id } },
        }),
      ),
    onSuccess: store,
  });

  const reorderSections = useMutation({
    mutationFn: async (ids: string[]) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/sections/reorder", {
          params: { path: { id: examId } },
          body: { ids },
        }),
      ),
    ...optimistic<string[]>(withSectionOrder),
    onSuccess: store,
  });

  const addItems = useMutation({
    mutationFn: async (body: components["schemas"]["ItemsIn"]) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/items", {
          params: { path: { id: examId } },
          body,
        }),
      ),
    onSuccess: store,
  });

  const editPoints = useMutation({
    mutationFn: async (vars: { id: string; points: number }) =>
      unwrap(
        await apiClient.PATCH("/api/v1/exam-items/{id}", {
          params: { path: { id: vars.id } },
          body: { points: vars.points },
        }),
      ),
    ...optimistic<{ id: string; points: number }>((exam, v) =>
      withPoints(exam, v.id, v.points),
    ),
    onSuccess: store,
  });

  const moveItem = useMutation({
    mutationFn: async (vars: { id: string; sectionId: string }) =>
      unwrap(
        await apiClient.PATCH("/api/v1/exam-items/{id}", {
          params: { path: { id: vars.id } },
          body: { section_id: vars.sectionId },
        }),
      ),
    onSuccess: store,
  });

  const reorderItems = useMutation({
    mutationFn: async (vars: { sectionId: string; ids: string[] }) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/items/reorder", {
          params: { path: { id: examId } },
          body: { section_id: vars.sectionId, ids: vars.ids },
        }),
      ),
    ...optimistic<{ sectionId: string; ids: string[] }>((exam, v) =>
      withItemOrder(exam, v.sectionId, v.ids),
    ),
    onSuccess: store,
  });

  const removeItem = useMutation({
    mutationFn: async (vars: { id: string; group: boolean }) =>
      unwrap(
        await apiClient.DELETE("/api/v1/exam-items/{id}", {
          params: { path: { id: vars.id }, query: { group: vars.group } },
        }),
      ),
    onSuccess: store,
  });

  const applyBlueprint = useMutation({
    mutationFn: async (body: Blueprint) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/blueprint/apply", {
          params: { path: { id: examId } },
          body,
        }),
      ),
    onSuccess: store,
  });

  const applyProposal = useMutation({
    mutationFn: async (vars: { id: string; edits: ProposalEdits }) =>
      unwrap(
        await apiClient.POST("/api/v1/exam-proposals/{id}/apply", {
          params: { path: { id: vars.id } },
          body: { edits: vars.edits },
        }),
      ),
    onSuccess: (exam) => {
      store(exam);
      void qc.invalidateQueries({ queryKey: proposalsKey(examId) });
    },
  });

  const discardProposal = useMutation({
    mutationFn: async (id: string) =>
      unwrap(
        await apiClient.POST("/api/v1/exam-proposals/{id}/discard", {
          params: { path: { id } },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: proposalsKey(examId) });
    },
  });

  return {
    rename,
    saveSettings,
    addSection,
    editSection,
    deleteSection,
    reorderSections,
    addItems,
    editPoints,
    moveItem,
    reorderItems,
    removeItem,
    applyBlueprint,
    applyProposal,
    discardProposal,
  };
}

/* ------------------------- blueprint / bank / tree ---------------------- */

export function useBlueprintPreview(examId: string) {
  return useMutation({
    mutationFn: async (body: Blueprint) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/blueprint/preview", {
          params: { path: { id: examId } },
          body,
        }),
      ),
  });
}

export interface BankSearchParams {
  q: string;
  subjectId: string;
  chapterId: string;
  lessonId: string;
  type: string;
  difficulty: string;
}

export function useBankSearch(params: BankSearchParams) {
  return useQuery({
    queryKey: ["bank-search", params],
    queryFn: async () => {
      const difficulty = params.difficulty ? Number(params.difficulty) : null;
      return unwrap(
        await apiClient.GET("/api/v1/bank/questions", {
          params: {
            query: {
              subject_id: params.subjectId,
              statuses: ["approved"],
              limit: 30,
              ...(params.q ? { q: params.q } : {}),
              ...(params.chapterId ? { chapter_ids: [params.chapterId] } : {}),
              ...(params.lessonId ? { lesson_ids: [params.lessonId] } : {}),
              ...(params.type ? { types: [params.type] } : {}),
              ...(difficulty === null
                ? {}
                : { difficulty_min: difficulty, difficulty_max: difficulty }),
            },
          },
        }),
      );
    },
  });
}

export function useBankStats(subjectId: string) {
  return useQuery({
    queryKey: ["bank-stats", subjectId],
    queryFn: async () =>
      unwrap(
        await apiClient.GET("/api/v1/bank/stats", {
          params: { query: { subject_id: subjectId } },
        }),
      ),
  });
}

export function useSubjectTree(subjectId: string) {
  return useQuery({
    queryKey: ["subject-tree", subjectId],
    queryFn: async () =>
      unwrap(
        await apiClient.GET("/api/v1/subjects/{id}/tree", {
          params: { path: { id: subjectId } },
        }),
      ),
  });
}

/* ----------------------------- AI assistant ----------------------------- */

export const proposalsKey = (examId: string) =>
  ["exam-proposals", examId] as const;

export function useCompose(examId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: components["schemas"]["ComposeIn"]) =>
      unwrap(
        await apiClient.POST("/api/v1/exams/{id}/compose", {
          params: { path: { id: examId } },
          body,
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: proposalsKey(examId) });
    },
  });
}

export function useProposals(examId: string) {
  return useQuery({
    queryKey: proposalsKey(examId),
    queryFn: async () =>
      unwrap(
        await apiClient.GET("/api/v1/exams/{id}/proposals", {
          params: { path: { id: examId } },
        }),
      ),
  });
}

/* ------------------------------- versions ------------------------------- */

export function useAnswerKey(examId: string, label: string | undefined) {
  return useQuery({
    queryKey: ["answer-key", examId, label],
    enabled: Boolean(label),
    queryFn: async () =>
      unwrap(
        await apiClient.GET("/api/v1/exams/{id}/versions/{label}/answer-key", {
          params: { path: { id: examId, label: label ?? "" } },
        }),
      ),
  });
}

export function invalidateExam(qc: QueryClient, examId: string) {
  void qc.invalidateQueries({ queryKey: examKey(examId) });
}
