import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, Outlet, useLocation } from "react-router";
import { ApiError, onUnauthorized } from "@/api/client";
import { ME_QUERY_KEY, useMe } from "@/api/hooks/auth";

export function AuthGuard() {
  const location = useLocation();
  const queryClient = useQueryClient();
  const meQuery = useMe();
  const [unauthorized, setUnauthorized] = useState(false);

  useEffect(() => {
    return onUnauthorized((path) => {
      setUnauthorized(true);
      queryClient.setQueryData(ME_QUERY_KEY, null);
      if (path !== "/api/v1/auth/me") {
        void queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY });
      }
    });
  }, [queryClient]);

  const isMeUnauthorized =
    unauthorized ||
    meQuery.data === null ||
    (meQuery.error instanceof ApiError && meQuery.error.status === 401);

  if (isMeUnauthorized) {
    const currentPath = `${location.pathname}${location.search}`;
    const loginUrl = `/login?next=${encodeURIComponent(currentPath)}`;
    return <Navigate to={loginUrl} replace />;
  }

  return <Outlet />;
}
