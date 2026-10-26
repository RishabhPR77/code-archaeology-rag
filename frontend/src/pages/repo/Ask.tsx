import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, ChevronDown, GitPullRequest, MessageSquareText, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { ProviderMark } from "../../components/brand";
import { Markdown } from "../../components/Markdown";
import { Button, Card, ConfirmDialog, ErrorNotice, Segmented, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/auth";
import type { AskMode, QueryResult, Repo } from "../../lib/types";
import { cn, formatDate, relativeTime, shortSha } from "../../lib/utils";

const SUGGESTIONS = [
  "What are the most significant changes made recently?",
  "Which bugs were fixed, and what caused them?",
  "Were there any major refactors? Why were they done?",
  "Summarize what each contributor worked on.",
  "Which parts of the codebase are the most fragile?",
  "What new features were added and why?",
];

const MODES: { value: AskMode; label: string }[] = [
  { value: "detailed", label: "Detailed" },
  { value: "summary", label: "Summary" },
  { value: "bullets", label: "Bullets" },
];

function Sources({ result, repoUrl }: { result: QueryResult; repoUrl: string }) {
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

function Exchange({ q, repoUrl }: { q: QueryResult; repoUrl: string }) {
  return (
    <div className="space-y-3 animate-fade-up">
      <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-fg">
        {q.question}
      </div>
      <Card className="p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-subtle">
          <ProviderMark id={q.provider} className="size-5 text-[8px]" />
          <span className="font-mono">{q.model}</span>
          <span>·</span>
          <span className="capitalize">{q.mode}</span>
          <span className="ml-auto">{relativeTime(q.created_at)}</span>
        </div>
        <Markdown repoUrl={repoUrl}>{q.answer}</Markdown>
        <Sources result={q} repoUrl={repoUrl} />
      </Card>
    </div>
  );
}

export function Ask({ repo }: { repo: Repo }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const key = ["repo-data", repo.id, "queries"];
  const history = useQuery({ queryKey: key, queryFn: () => api.queries(repo.id) });
  const [question, setQuestion] = useState("");
  const [mode, setMode] = useState<AskMode>("detailed");
  const [onlyPr, setOnlyPr] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const hasModel = !!(user.active_provider && user.active_model);

  const ask = useMutation({
    mutationFn: (q: string) => api.ask(repo.id, q, mode, onlyPr),
    onSuccess: (result) => {
      qc.setQueryData<QueryResult[]>(key, (old) => [...(old ?? []), result]);
      setQuestion("");
    },
  });
  const clear = useMutation({
    mutationFn: () => api.clearQueries(repo.id),
    onSuccess: () => { qc.setQueryData(key, []); setConfirmClear(false); toast.success("History cleared"); },
  });

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.data?.length, ask.isPending]);

  const submit = (q = question) => {
    if (q.trim().length >= 3 && !ask.isPending) ask.mutate(q.trim());
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  const items = history.data ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      {!hasModel && (
        <div className="mb-5 rounded-lg border border-warning/25 bg-warning-soft px-4 py-3 text-[13px] text-warning">
          Connect a model provider to ask questions. <Link to="/app/settings" className="font-medium underline">Open settings</Link>
        </div>
      )}

      {history.isPending && <Skeleton className="h-40 rounded-xl" />}

      {!history.isPending && items.length === 0 && !ask.isPending && (
        <div className="py-6 text-center">
          <div className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><Sparkles className="size-5" /></div>
          <h2 className="mt-4 text-base font-semibold">Ask about {repo.full_name}</h2>
          <p className="mt-1 text-[13px] text-muted">Answers come only from this repository's commits, PRs and reviews, with citations.</p>
          <div className="mt-6 grid gap-2 sm:grid-cols-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => submit(s)} disabled={!hasModel || ask.isPending}
                      className="rounded-xl border border-border bg-surface p-3 text-left text-[13px] text-muted transition-colors hover:border-border-strong hover:text-text disabled:opacity-50 cursor-pointer">
                {s}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-8">
        {items.map((q) => <Exchange key={q.id} q={q} repoUrl={repo.url} />)}
        {ask.isPending && (
          <div className="space-y-3">
            <div className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-[14px] text-accent-fg">{ask.variables}</div>
            <Card className="p-5">
              <div className="flex items-center gap-2 text-xs text-muted">
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-bounce rounded-full bg-accent" style={{ animationDelay: `${i * 120}ms` }} />)}
                </span>
                Searching history and asking <span className="font-mono">{user.active_model}</span>…
              </div>
              <div className="mt-4 space-y-2"><Skeleton className="h-3 w-11/12" /><Skeleton className="h-3 w-9/12" /><Skeleton className="h-3 w-10/12" /></div>
            </Card>
          </div>
        )}
      </div>

      {ask.error && <ErrorNotice error={ask.error} className="mt-4" />}
      <div ref={bottom} />

      <div className="sticky bottom-0 mt-8 bg-gradient-to-t from-bg via-bg to-transparent pt-6 pb-4">
        <Card className="p-2 focus-within:border-accent">
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKey}
            rows={2}
            maxLength={2000}
            disabled={!hasModel}
            placeholder={hasModel ? "Why was the auth module refactored?" : "Connect a model provider first"}
            aria-label="Your question"
            className="block w-full resize-none bg-transparent px-2 py-1.5 text-[14px] outline-none placeholder:text-subtle disabled:opacity-60"
          />
          <div className="flex flex-wrap items-center gap-2 px-1 pt-1">
            <Segmented size="sm" value={mode} onChange={setMode} options={MODES} />
            <label className="flex cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-muted hover:text-text">
              <input type="checkbox" checked={onlyPr} onChange={(e) => setOnlyPr(e.target.checked)} className="accent-[var(--accent)]" />
              Only commits with PRs
            </label>
            <div className="flex-1" />
            {items.length > 0 && (
              <button onClick={() => setConfirmClear(true)} title="Clear history" aria-label="Clear history"
                      className="rounded-md p-1.5 text-subtle hover:text-danger cursor-pointer">
                <Trash2 className="size-3.5" />
              </button>
            )}
            <Button size="icon" className="size-8" onClick={() => submit()} loading={ask.isPending}
                    disabled={!hasModel || question.trim().length < 3} aria-label="Ask">
              {!ask.isPending && <ArrowUp className="size-4" />}
            </Button>
          </div>
        </Card>
        <p className="mt-2 flex items-center justify-center gap-1.5 text-[11px] text-subtle">
          <MessageSquareText className="size-3" /> Enter to send · Shift+Enter for a new line · uses your own API key
        </p>
      </div>

      <ConfirmDialog open={confirmClear} onClose={() => setConfirmClear(false)} onConfirm={() => clear.mutate()}
                     loading={clear.isPending} confirmLabel="Clear history" title="Clear question history?"
                     description="All questions and answers for this repository are removed." />
    </div>
  );
}
