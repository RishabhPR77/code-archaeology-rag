export type ProviderId = "anthropic" | "openai" | "gemini" | "groq" | "openrouter";

export interface User {
  id: number;
  email: string;
  name: string;
  avatar_url: string | null;
  github_login: string | null;
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

export interface Repo {
  id: string;
  url: string;
  full_name: string;
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
  question: string;
  answer: string;
  mode: AskMode;
  provider: ProviderId;
  model: string;
  sources: Source[];
  created_at: string;
}

export interface TimelineResult {
  path: string;
  answer: string | null;
  provider: ProviderId | null;
  model: string | null;
  entries: Commit[];
}
