import { useQuery } from "@tanstack/react-query";
import { apiClient, extractApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type SubjectOut = components["schemas"]["SubjectOut"];
export type SubjectPage = components["schemas"]["Page_SubjectOut_"];

export const SUBJECTS_QUERY_KEY = ["subjects"] as const;

export async function fetchSubjects(): Promise<SubjectPage> {
  const { data, error, response } = (await apiClient.GET("/api/v1/subjects", {
    params: {
      query: { limit: 100 },
    },
  })) as {
    data?: SubjectPage;
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined || data === undefined) {
    throw extractApiError(response.status, error);
  }
  return data;
}

export function useSubjects() {
  return useQuery({
    queryKey: SUBJECTS_QUERY_KEY,
    queryFn: fetchSubjects,
  });
}
