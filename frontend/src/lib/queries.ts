import { useQuery } from "@tanstack/react-query";

import { api } from "./api";
import { isIngesting } from "./utils";

export const reposKey = ["repos"] as const;
export const providersKey = ["providers"] as const;

export function useRepos() {
  return useQuery({
    queryKey: reposKey,
    queryFn: api.repos,
    // Keep polling while anything is still ingesting
    refetchInterval: (q) => (q.state.data?.some((r) => isIngesting(r.status)) ? 2000 : false),
  });
}

export function useProviders() {
  return useQuery({ queryKey: providersKey, queryFn: api.providers });
}

export const authConfigKey = ["auth-config"] as const;
export const githubStatusKey = ["github-status"] as const;

export function useAuthConfig() {
  return useQuery({ queryKey: authConfigKey, queryFn: api.authConfig, staleTime: Infinity });
}

export function useGitHubStatus(enabled = true) {
  return useQuery({ queryKey: githubStatusKey, queryFn: api.githubStatus, enabled, staleTime: 60_000 });
}
