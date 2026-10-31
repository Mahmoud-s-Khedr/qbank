import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, extractApiError } from "@/api/client";
import { SUBJECTS_QUERY_KEY } from "@/api/hooks/subjects";
import type { components } from "@/api/schema";

export type SubjectTree = components["schemas"]["SubjectTree"];
export type SubjectIn = components["schemas"]["SubjectIn"];
export type SubjectUpdate = components["schemas"]["SubjectUpdate"];
export type ChapterTree = components["schemas"]["ChapterTree"];
export type ChapterOut = components["schemas"]["ChapterOut"];
export type ChapterMerge = components["schemas"]["ChapterMerge"];
export type LessonOut = components["schemas"]["LessonOut"];
export type LessonUpdate = components["schemas"]["LessonUpdate"];
export type LessonMerge = components["schemas"]["LessonMerge"];
export type ItemIn = components["schemas"]["ItemIn"];
export type TaxonomyItemUpdate =
  components["schemas"]["qbank__schemas__taxonomy__ItemUpdate"];
export type Reorder = components["schemas"]["Reorder"];

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

export const subjectTreeKey = (subjectId?: string | null) =>
  ["subjects", subjectId, "tree"] as const;

export function useSubjectTree(subjectId?: string | null) {
  return useQuery({
    queryKey: subjectTreeKey(subjectId),
    queryFn: async () => {
      if (!subjectId) return null;
      const res = (await apiClient.GET("/api/v1/subjects/{id}/tree", {
        params: { path: { id: subjectId } },
      })) as Envelope<SubjectTree>;
      return unwrap(res);
    },
    enabled: Boolean(subjectId),
  });
}

export function useCreateSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: SubjectIn) => {
      const res = (await apiClient.POST("/api/v1/subjects", {
        body: data,
      })) as Envelope<components["schemas"]["SubjectOut"]>;
      return unwrap(res);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SUBJECTS_QUERY_KEY });
    },
  });
}

export function useUpdateSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, data }: { id: string; data: SubjectUpdate }) => {
      const res = (await apiClient.PATCH("/api/v1/subjects/{id}", {
        params: { path: { id } },
        body: data,
      })) as Envelope<components["schemas"]["SubjectOut"]>;
      return unwrap(res);
    },
    onSuccess: (_, { id }) => {
      void queryClient.invalidateQueries({ queryKey: SUBJECTS_QUERY_KEY });
      void queryClient.invalidateQueries({ queryKey: subjectTreeKey(id) });
    },
  });
}

export function useDeleteSubject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const res = (await apiClient.DELETE("/api/v1/subjects/{id}", {
        params: { path: { id } },
      })) as { error?: unknown; response: Response };
      if (!res.response.ok) {
        throw extractApiError(res.response.status, res.error);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SUBJECTS_QUERY_KEY });
    },
  });
}

export function useCreateChapter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      subjectId,
      data,
    }: {
      subjectId: string;
      data: ItemIn;
    }) => {
      const res = (await apiClient.POST("/api/v1/subjects/{id}/chapters", {
        params: { path: { id: subjectId } },
        body: data,
      })) as Envelope<ChapterOut>;
      return unwrap(res);
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
    },
  });
}

export function useUpdateChapter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      subjectId?: string;
      data: TaxonomyItemUpdate;
    }) => {
      const res = (await apiClient.PATCH("/api/v1/chapters/{id}", {
        params: { path: { id } },
        body: data,
      })) as Envelope<ChapterOut>;
      return unwrap(res);
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
      void queryClient.invalidateQueries({ queryKey: ["subjects"] });
    },
  });
}

export function useDeleteChapter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id }: { id: string; subjectId?: string }) => {
      const res = (await apiClient.DELETE("/api/v1/chapters/{id}", {
        params: { path: { id } },
      })) as { error?: unknown; response: Response };
      if (!res.response.ok) {
        throw extractApiError(res.response.status, res.error);
      }
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
      void queryClient.invalidateQueries({ queryKey: ["subjects"] });
    },
  });
}

export function useReorderChapters() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      subjectId,
      ids,
    }: {
      subjectId: string;
      ids: string[];
    }) => {
      const res = (await apiClient.POST(
        "/api/v1/subjects/{id}/chapters/reorder",
        {
          params: { path: { id: subjectId } },
          body: { ids },
        },
      )) as { error?: unknown; response: Response };
      if (!res.response.ok) {
        throw extractApiError(res.response.status, res.error);
      }
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
    },
  });
}

export function useMergeChapter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      subjectId?: string;
      data: ChapterMerge;
    }) => {
      const res = (await apiClient.POST("/api/v1/chapters/{id}/merge", {
        params: { path: { id } },
        body: data,
      })) as Envelope<ChapterOut>;
      return unwrap(res);
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
      void queryClient.invalidateQueries({ queryKey: ["bank"] });
    },
  });
}

export function useCreateLesson() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      chapterId,
      data,
    }: {
      chapterId: string;
      subjectId?: string;
      data: ItemIn;
    }) => {
      const res = (await apiClient.POST("/api/v1/chapters/{id}/lessons", {
        params: { path: { id: chapterId } },
        body: data,
      })) as Envelope<LessonOut>;
      return unwrap(res);
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
    },
  });
}

export function useUpdateLesson() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      subjectId?: string;
      data: LessonUpdate;
    }) => {
      const res = (await apiClient.PATCH("/api/v1/lessons/{id}", {
        params: { path: { id } },
        body: data,
      })) as Envelope<LessonOut>;
      return unwrap(res);
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
      void queryClient.invalidateQueries({ queryKey: ["subjects"] });
    },
  });
}

export function useDeleteLesson() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id }: { id: string; subjectId?: string }) => {
      const res = (await apiClient.DELETE("/api/v1/lessons/{id}", {
        params: { path: { id } },
      })) as { error?: unknown; response: Response };
      if (!res.response.ok) {
        throw extractApiError(res.response.status, res.error);
      }
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
      void queryClient.invalidateQueries({ queryKey: ["subjects"] });
    },
  });
}

export function useReorderLessons() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      chapterId,
      ids,
    }: {
      chapterId: string;
      subjectId?: string;
      ids: string[];
    }) => {
      const res = (await apiClient.POST(
        "/api/v1/chapters/{id}/lessons/reorder",
        {
          params: { path: { id: chapterId } },
          body: { ids },
        },
      )) as { error?: unknown; response: Response };
      if (!res.response.ok) {
        throw extractApiError(res.response.status, res.error);
      }
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
    },
  });
}

export function useMergeLesson() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      data,
    }: {
      id: string;
      subjectId?: string;
      data: LessonMerge;
    }) => {
      const res = (await apiClient.POST("/api/v1/lessons/{id}/merge", {
        params: { path: { id } },
        body: data,
      })) as Envelope<LessonOut>;
      return unwrap(res);
    },
    onSuccess: (_, { subjectId }) => {
      void queryClient.invalidateQueries({
        queryKey: subjectTreeKey(subjectId),
      });
      void queryClient.invalidateQueries({ queryKey: ["bank"] });
    },
  });
}
