import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, extractApiError } from "@/api/client";
import type { components } from "@/api/schema";

export type UserOut = components["schemas"]["UserOut"];
export type LoginIn = components["schemas"]["Login"];
export type Role = components["schemas"]["Role"];

export const ME_QUERY_KEY = ["auth", "me"] as const;

export async function fetchMe(): Promise<UserOut | null> {
  const { data, error, response } = (await apiClient.GET(
    "/api/v1/auth/me",
  )) as {
    data?: UserOut;
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined || data === undefined) {
    throw extractApiError(response.status, error);
  }
  return data;
}

export function useMe() {
  return useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: fetchMe,
    retry: false,
  });
}

export async function loginRequest(credentials: LoginIn): Promise<UserOut> {
  const { data, error, response } = (await apiClient.POST(
    "/api/v1/auth/login",
    {
      body: credentials,
    },
  )) as {
    data?: UserOut;
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined || data === undefined) {
    throw extractApiError(response.status, error);
  }
  return data;
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: loginRequest,
    onSuccess: (user) => {
      queryClient.setQueryData(ME_QUERY_KEY, user);
    },
  });
}

export async function logoutRequest(): Promise<void> {
  const { error, response } = (await apiClient.POST("/api/v1/auth/logout")) as {
    error?: unknown;
    response: Response;
  };
  if (!response.ok || error !== undefined) {
    throw extractApiError(response.status, error);
  }
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logoutRequest,
    onSuccess: () => {
      queryClient.setQueryData(ME_QUERY_KEY, null);
    },
  });
}
