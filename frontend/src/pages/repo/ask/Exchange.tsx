import type { AskMode, QueryResult } from "../../../lib/types";
import { ChevronDown, GitPullRequest, Square } from "lucide-react";
import { useState } from "react";
import { ProviderMark } from "../../../components/brand";
import { Markdown } from "../../../components/Markdown";
import { Card } from "../../../components/ui";
import { cn, formatDate, relativeTime, shortSha } from "../../../lib/utils";

export const SUGGESTIONS = [
  "What are the most significant changes made recently?",
  "Which bugs were fixed, and what caused them?",
  "Were there any major refactors? Why were they done?",
  "Summarize what each contributor worked on.",
  "Which parts of the codebase are the most fragile?",
  "What new features were added and why?",
];
// The answer being written: text so far, what the search found, and whether the user pressed Stop
export interface Draft { text: string; searchQuery: string | null; found: boolean; stopped: boolean }
// The user pressed Stop
export const isAbort = (e: unknown) => e instanceof DOMException && e.name === "AbortError";
export const MODES: { value: AskMode; label: string }[] = [
  { value: "detailed", label: "Detailed" },
  { value: "summary", label: "Summary" },
  { value: "bullets", label: "Bullets" },
];
export function Sources({ result, repoUrl }: { result: QueryResult; repoUrl: string }) {
  const [open, setOpen] = useState(false);
  if (!result.sources.length) return null;
  return (
    <div className="mt-4 border-t border-border pt-3">
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
              className="flex items-center gap-1.5 text-xs font-medium text-muted hover:text-text cursor-pointer">
        <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
        {result.sources.length} source commits
      </button>
      {open && (
        <ul className="mt-3 grid gap-2 sm:grid-cols-2">
          {result.sources.map((s) => (
            <li key={s.sha}>
              <a href={`${repoUrl}/commit/${s.sha}`} target="_blank" rel="noopener noreferrer"
                 className="block rounded-lg border border-border bg-surface-2/60 p-3 transition-colors hover:border-border-strong">
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="font-mono font-semibold text-accent">{shortSha(s.sha)}</span>
                  <span className="truncate text-muted">{s.author}</span>
                  <span className="ml-auto shrink-0 text-subtle">{formatDate(s.timestamp)}</span>
                </div>
                <p className="mt-1.5 line-clamp-2 text-[12px] leading-snug">{s.message}</p>
                <div className="mt-2 flex items-center gap-2 text-[11px] text-subtle">
                  {s.pr_number && <span className="inline-flex items-center gap-1"><GitPullRequest className="size-3" />#{s.pr_number}</span>}
                  <span className="truncate font-mono">{s.files.slice(0, 2).join(", ")}{s.files.length > 2 && ` +${s.files.length - 2}`}</span>
                  <span className="ml-auto shrink-0 font-mono">{s.score.toFixed(2)}</span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
export function StoppedNote() {
  return (
    <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-subtle">
      <Square className="size-2.5 fill-current" /> You stopped this answer
    </p>
  );
}
export function Exchange({ q, repoUrl }: { q: QueryResult; repoUrl: string }) {
  return (
    <div className="space-y-3 animate-fade-up">
      <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-fg">
        {q.question}
      </div>
      {q.search_query && (
        // A follow-up was rewritten to stand on its own; showing it explains which commits came back
        <p className="ml-auto w-fit max-w-[85%] text-right text-xs text-subtle">
          Searched for: <span className="text-muted">{q.search_query}</span>
        </p>
      )}
      <Card className="p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-subtle">
          <ProviderMark id={q.provider} className="size-5 text-[8px]" />
          <span className="font-mono">{q.model}</span>
          <span>·</span>
          <span className="capitalize">{q.mode}</span>
          <span className="ml-auto">{relativeTime(q.created_at)}</span>
        </div>
        <Markdown repoUrl={repoUrl}>{q.answer}</Markdown>
        {q.stopped && <StoppedNote />}
        <Sources result={q} repoUrl={repoUrl} />
      </Card>
    </div>
  );
}
