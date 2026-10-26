import type {
  AskMode, Author, CoChange, Commit, HotFile, Me, Model, Overview, Provider, ProviderId,
  PullRequest, QueryResult, Repo, TimelineResult,
} from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function detailMessage(data: unknown): string | null {
  if (!data || typeof data !== "object" || !("detail" in data)) return null;
  const detail = (data as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  // FastAPI validation errors: [{ loc, msg }]
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => String(d?.msg ?? "").replace(/^Value error, /, ""))
      .filter(Boolean)
      .join(" ");
  }
  return null;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      credentials: "include",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, detailMessage(data) ?? `Request failed (${res.status})`);
  return data as T;
}

const get = <T,>(p: string) => request<T>("GET", p);
const post = <T,>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T,>(p: string, b: unknown) => request<T>("PUT", p, b);
const del = (p: string) => request<void>("DELETE", p);

export const api = {
  // Auth
  authConfig: () => get<{ github_enabled: boolean }>("/auth/config"),
  me: async (): Promise<Me | null> => {
    try {
      return await get<Me>("/auth/me");
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  },
  login: (email: string, password: string) => post<Me>("/auth/login", { email, password }),
  register: (email: string, password: string, name: string) =>
    post<Me>("/auth/register", { email, password, name }),
  logout: () => post<void>("/auth/logout"),

  // Providers
  providers: () => get<Provider[]>("/providers"),
  saveKey: (id: ProviderId, apiKey: string) =>
    put<{ provider: Provider; models: Model[] }>(`/providers/${id}/key`, { api_key: apiKey }),
  deleteKey: (id: ProviderId) => del(`/providers/${id}/key`),
  models: (id: ProviderId, refresh = false) =>
    get<Model[]>(`/providers/${id}/models${refresh ? "?refresh=true" : ""}`),
  selectModel: (id: ProviderId, model: string) => put<Provider>(`/providers/${id}/model`, { model }),
  setActive: (id: ProviderId) => put<Provider>("/providers/active", { provider: id }),

  // Repos
  repos: () => get<Repo[]>("/repos"),
  repo: (id: string) => get<Repo>(`/repos/${id}`),
  createRepo: (url: string, maxCommits: number) => post<Repo>("/repos", { url, max_commits: maxCommits }),
  resync: (id: string) => post<Repo>(`/repos/${id}/resync`),
  deleteRepo: (id: string) => del(`/repos/${id}`),
  overview: (id: string) => get<Overview>(`/repos/${id}/overview`),
  commits: (id: string) => get<Commit[]>(`/repos/${id}/commits`),
  files: (id: string) => get<string[]>(`/repos/${id}/files`),
  hotfiles: (id: string, limit: number) => get<HotFile[]>(`/repos/${id}/hotfiles?limit=${limit}`),
  cochange: (id: string, limit: number) => get<CoChange[]>(`/repos/${id}/cochange?limit=${limit}`),
  authors: (id: string) => get<Author[]>(`/repos/${id}/authors`),
  pulls: (id: string) => get<PullRequest[]>(`/repos/${id}/pulls`),
  queries: (id: string) => get<QueryResult[]>(`/repos/${id}/queries`),
  clearQueries: (id: string) => del(`/repos/${id}/queries`),
  ask: (id: string, question: string, mode: AskMode, onlyPr: boolean) =>
    post<QueryResult>(`/repos/${id}/ask`, { question, mode, only_pr: onlyPr }),
  timeline: (id: string, path: string) => post<TimelineResult>(`/repos/${id}/timeline`, { path }),
};
