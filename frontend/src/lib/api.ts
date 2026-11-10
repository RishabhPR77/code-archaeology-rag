import type {
  AskMode, AuthConfig, Profile, RangePreview, Author, Chat, CoChange, Commit, GitHubRepo, GitHubStatus, HotFile, Me, Model,
  OriginsResult, Overview, Provider, ProviderId, PullRequest, QueryResult, Repo, RepoFile, Source, SuspectsResult,
  TimelineMatch, TimelineResult,
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

export interface AskStreamHandlers {
  // What the search found, before the model starts writing
  onSources?: (found: { sources: Source[]; search_query: string | null }) => void;
  // Each new piece of the answer
  onText?: (text: string) => void;
}

/** Ask a question and receive the answer as server-sent events while the model writes it.
 *  Resolves with the saved exchange; rejects with ApiError, or with an AbortError if `signal` aborts. */
async function askStream(repoId: string, body: object, handlers: AskStreamHandlers,
                         signal?: AbortSignal): Promise<QueryResult> {
  let res: Response;
  try {
    res = await fetch(`/api/repos/${repoId}/ask/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
  } catch (e) {
    if (signal?.aborted) throw e;
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  // Setup problems (no model, bad key, unknown chat) come back as ordinary JSON errors
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => null);
    throw new ApiError(res.status, detailMessage(data) ?? `Request failed (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch (e) {
      if (signal?.aborted) throw e;
      throw new ApiError(0, "The connection dropped before the answer finished. Try again.");
    }
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, "\n");
    // Events are separated by a blank line: "event: name\ndata: {json}\n\n"
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let name = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) name = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (name === "sources") handlers.onSources?.(payload);
      else if (name === "delta") handlers.onText?.(payload.text);
      else if (name === "done") return payload as QueryResult;
      else if (name === "error") throw new ApiError(502, payload.message);
    }
  }
  throw new ApiError(0, "The answer stopped before it finished. Try again.");
}

const get = <T,>(p: string) => request<T>("GET", p);
const post = <T,>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T,>(p: string, b: unknown) => request<T>("PUT", p, b);
const del = (p: string) => request<void>("DELETE", p);

export const api = {
  // Auth
  authConfig: () => get<AuthConfig>("/auth/config"),
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
  demo: () => post<Me>("/auth/demo"),
  profile: () => get<Profile>("/auth/profile"),
  rename: (name: string) => request<Me>("PATCH", "/auth/me", { name }),
  verifyEmail: (code: string) => post<Me>("/auth/verify-email", { code }),
  resendCode: () => post<void>("/auth/resend-code"),

  // GitHub App
  githubStatus: () => get<GitHubStatus>("/github/status"),
  githubRepos: () => get<GitHubRepo[]>("/github/repos"),
  disconnectGitHub: () => del("/github"),

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
  createRepo: (url: string, maxCommits: number, skipCommits = 0) =>
    post<Repo>("/repos", { url, max_commits: maxCommits, skip_commits: skipCommits }),
  rangePreview: (url: string, skip: number, count: number) =>
    get<RangePreview>(`/repos/range-preview?${new URLSearchParams({ url, skip: String(skip), count: String(count) })}`),
  resync: (id: string) => post<Repo>(`/repos/${id}/resync`),
  deleteRepo: (id: string) => del(`/repos/${id}`),
  // Admins: show a repository, with its chats, in the public demo
  makeDemo: (id: string) => post<void>(`/repos/${id}/make-demo`),
  demoRepos: () => get<Repo[]>("/admin/demo"),
  stopSharing: (id: string) => del(`/admin/demo/${id}`),
  overview: (id: string) => get<Overview>(`/repos/${id}/overview`),
  commits: (id: string) => get<Commit[]>(`/repos/${id}/commits`),
  files: (id: string) => get<RepoFile[]>(`/repos/${id}/files`),
  hotfiles: (id: string, limit: number) => get<HotFile[]>(`/repos/${id}/hotfiles?limit=${limit}`),
  origins: (id: string) => get<OriginsResult>(`/repos/${id}/origins`),
  cochange: (id: string, limit: number) => get<CoChange[]>(`/repos/${id}/cochange?limit=${limit}`),
  authors: (id: string) => get<Author[]>(`/repos/${id}/authors`),
  pulls: (id: string) => get<PullRequest[]>(`/repos/${id}/pulls`),
  chats: (id: string) => get<Chat[]>(`/repos/${id}/chats`),
  chat: (id: string, chatId: number) => get<QueryResult[]>(`/repos/${id}/chats/${chatId}`),
  deleteChat: (id: string, chatId: number) => del(`/repos/${id}/chats/${chatId}`),
  deleteAllChats: (id: string) => del(`/repos/${id}/queries`),
  // chatId null starts a new chat; the answer says which chat it landed in
  ask: (id: string, question: string, mode: AskMode, onlyPr: boolean, chatId: number | null,
        handlers: AskStreamHandlers = {}, signal?: AbortSignal) =>
    askStream(id, { question, mode, only_pr: onlyPr, conversation_id: chatId }, handlers, signal),
  // Keep an answer the user stopped part-way; the reply is the saved exchange, marked as stopped
  saveStopped: (id: string, stopped: {
    question: string; mode: AskMode; only_pr: boolean; conversation_id: number | null;
    answer: string; search_query: string | null; sources: Source[];
  }) => post<QueryResult>(`/repos/${id}/ask/stopped`, stopped),
  suspects: (id: string, description: string, since: string | null) =>
    post<SuspectsResult>(`/repos/${id}/suspects`, { description, since }),
  timeline: (id: string, path: string, match: TimelineMatch) =>
    post<TimelineResult>(`/repos/${id}/timeline`, { path, match }),
};
