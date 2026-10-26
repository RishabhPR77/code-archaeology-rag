import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { Me } from "./types";

export const meKey = ["me"] as const;

export function useMe() {
  return useQuery({ queryKey: meKey, queryFn: api.me, staleTime: 30_000 });
}

/** The signed-in user — only call inside routes guarded by RequireAuth. */
export function useSession(): Me {
  const { data } = useMe();
  if (!data) throw new Error("useSession used outside an authenticated route");
  return data;
}

export function useSignOut() {
  const qc = useQueryClient();
  return async () => {
    await api.logout().catch(() => undefined);
    qc.clear();
    qc.setQueryData(meKey, null);
  };
}
