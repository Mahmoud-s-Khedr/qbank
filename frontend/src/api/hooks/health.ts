import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { components } from "@/api/schema";

export type HealthOut = components["schemas"]["HealthOut"];

export const HEALTH_QUERY_KEY = ["health"] as const;

export async function fetchHealth(): Promise<HealthOut> {
  const { data, error, response } = (await apiClient.GET("/api/v1/health")) as {
    data?: HealthOut;
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined || data === undefined) {
    throw new Error("Failed to fetch health status");
  }
  return data;
}

export function useHealth() {
  return useQuery({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: fetchHealth,
    retry: false,
    refetchInterval: 30_000,
  });
}
