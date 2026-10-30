import clsx, { type ClassValue } from "clsx";

import type { CommitType, ProviderId, RepoStatus } from "./types";

export const cn = (...inputs: ClassValue[]) => clsx(inputs);

export function formatDate(iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = {}) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric", ...opts });
}

export function relativeTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const diff = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000_000], ["month", 2_592_000_000], ["week", 604_800_000],
    ["day", 86_400_000], ["hour", 3_600_000], ["minute", 60_000],
  ];
  for (const [unit, ms] of units) if (abs >= ms) return rtf.format(Math.round(diff / ms), unit);
  return diff < 0 ? "just now" : "in a moment";
}

export const formatNumber = (n: number) => new Intl.NumberFormat().format(n);

export function compactTokens(n: number | null) {
  if (!n) return null;
  if (n >= 1_000_000) return `${+(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`;
  return String(n);
}

export const shortSha = (sha: string) => sha.slice(0, 7);
export const basename = (path: string) => path.split("/").pop() ?? path;

export const COMMIT_TYPES: Record<CommitType, { label: string; color: string }> = {
  feat: { label: "Feature", color: "#1a9a6c" },
  fix: { label: "Fix", color: "#d9483b" },
  refactor: { label: "Refactor", color: "#2f7fd6" },
  docs: { label: "Docs", color: "#cc8f1f" },
  test: { label: "Test", color: "#16a3a3" },
  chore: { label: "Chore", color: "#84919e" },
  other: { label: "Other", color: "#6b7fa3" },
};

export const PROVIDER_STYLE: Record<ProviderId, { mono: string; color: string }> = {
  anthropic: { mono: "A", color: "#d97757" },
  openai: { mono: "O", color: "#10a37f" },
  gemini: { mono: "G", color: "#4f8ef7" },
  groq: { mono: "Gq", color: "#f55036" },
  openrouter: { mono: "OR", color: "#6467f2" },
};

export const PROVIDER_NAMES: Record<ProviderId, string> = {
  anthropic: "Anthropic", openai: "OpenAI", gemini: "Google Gemini", groq: "Groq", openrouter: "OpenRouter",
};

export const INGEST_STAGES: { status: RepoStatus; label: string }[] = [
  { status: "queued", label: "Queued" },
  { status: "cloning", label: "Cloning repository" },
  { status: "extracting", label: "Reading commits" },
  { status: "fetching_prs", label: "Fetching pull requests" },
  { status: "embedding", label: "Embedding history" },
  { status: "ready", label: "Ready" },
];

export const isIngesting = (s: RepoStatus) => s !== "ready" && s !== "failed";
