export type ProviderId = "anthropic" | "openai" | "gemini" | "groq" | "openrouter";

export interface User {
  id: number;
  email: string;
  name: string;
  avatar_url: string | null;
  email_verified: boolean;
  code_resend_in: number;
  github_login: string | null;
  github_connected: boolean;
  google_linked: boolean;
  has_password: boolean;
  is_admin: boolean;
  active_provider: ProviderId | null;
  active_model: string | null;
  created_at: string;
}

export interface Limits {
  max_commits: number;
  commit_options: number[];
  max_repos: number;
  repos_used: number;
  max_ingests_day: number;
  ingests_today: number;
  repo_ttl_hours: number;
  unlimited: boolean;
}

export interface Me {
  user: User;
  limits: Limits;
}

export interface Provider {
  id: ProviderId;
  name: string;
  key_url: string;
  docs_url: string;
  configured: boolean;
  key_hint: string | null;
  model: string | null;
  active: boolean;
}

export interface Model {
  id: string;
  name: string;
  context_window: number | null;
  max_output: number | null;
  description: string | null;
}

export type RepoStatus = "queued" | "cloning" | "extracting" | "fetching_prs" | "embedding" | "ready" | "failed";

export interface AuthConfig {
  github_enabled: boolean;
  google_enabled: boolean;
  email_verification: boolean;
  contact_email: string | null;
}

export interface GitHubInstallation {
  id: number;
  account: string;
  repository_selection: "all" | "selected";
  manage_url: string | null;
}

export interface GitHubStatus {
  enabled: boolean;
  connected: boolean;
  login: string | null;
  install_url: string | null;
  installations: GitHubInstallation[];
  error: string | null;
}

export interface GitHubRepo {
  full_name: string;
  private: boolean;
  html_url: string;
  description: string | null;
  updated_at: string | null;
  default_branch: string | null;
}

export interface Repo {
  id: string;
  url: string;
  full_name: string;
  is_private: boolean;
  status: RepoStatus;
  stage_message: string;
  error: string | null;
  warnings: string[];
  max_commits: number;
  commit_count: number;
  pr_count: number;
  created_at: string;
  ready_at: string | null;
  expires_at: string | null;
}

export type CommitType = "feat" | "fix" | "refactor" | "docs" | "test" | "chore" | "other";

export interface Overview {
  commits: number;
  authors: number;
  files: number;
  prs: number;
  first_commit: string | null;
  last_commit: string | null;
  insertions: number;
  deletions: number;
  types: Partial<Record<CommitType, number>>;
  activity: { week: string; commits: number }[];
}

export interface Commit {
  sha: string;
  author: string;
  timestamp: string;
  message: string;
  type: CommitType;
  files: string[];
  insertions: number;
  deletions: number;
  pr_number: number | null;
}

export interface HotFile { file: string; changes: number }
export interface CoChange { file_a: string; file_b: string; co_changes: number }

export interface Author {
  author: string;
  commits: number;
  insertions: number;
  deletions: number;
  first_commit: string;
  last_commit: string;
  top_files: { file: string; changes: number }[];
}

export interface PullRequest {
  number: number;
  title: string;
  author: string;
  merged_at: string;
  labels: string[];
  commit_sha: string;
  files: string[];
}

export interface Source {
  sha: string;
  author: string;
  timestamp: string;
  files: string[];
  score: number;
  has_pr: boolean;
  pr_number: number | null;
  message: string;
}

export type AskMode = "detailed" | "summary" | "bullets";

export interface QueryResult {
  id: number;
  kind: string;
  conversation_id: number | null;
  question: string;
  search_query: string | null;
  answer: string;
  mode: AskMode;
  provider: ProviderId;
  model: string;
  sources: Source[];
  created_at: string;
}

export interface Chat {
  id: number;
  title: string;
  questions: number;
  created_at: string;
  updated_at: string;
}

export interface RepoFile {
  path: string;
  changes: number;
}

export type TimelineMatch = "contains" | "exact" | "folder";

export interface BugOrigin {
  sha: string;
  message: string;
  author: string;
  timestamp: string;
  lines: number;
  ingested: boolean;
}

export interface BugFix {
  sha: string;
  message: string;
  author: string;
  timestamp: string;
  status: "traced" | "older" | "nothing_to_trace" | "error";
  origins: BugOrigin[];
  older_lines: number;
  days: number | null;
}

export interface OriginsResult {
  computed: boolean;
  summary: {
    fixes: number;
    traced: number;
    older: number;
    nothing_to_trace: number;
    median_days: number | null;
    repeat_origins: (Omit<BugOrigin, "lines"> & { fixes: number })[];
  } | null;
  fixes: BugFix[];
}

export interface Suspect {
  sha: string;
  author: string;
  timestamp: string;
  message: string;
  type: CommitType;
  files: string[];
  pr_number: number | null;
  score: number;
  scores: { search: number; files: number; risk: number };
  reasons: string[];
}

export interface SuspectsResult {
  suspects: Suspect[];
  mentioned_files: string[];
  answer: string | null;
  provider: ProviderId | null;
  model: string | null;
}

export interface TimelineResult {
  path: string;
  answer: string | null;
  provider: ProviderId | null;
  model: string | null;
  entries: Commit[];
}
