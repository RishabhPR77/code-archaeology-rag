import { useMutation } from "@tanstack/react-query";
import { Check, FileSearch, GitPullRequest, SearchX } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { ProviderMark } from "../../components/brand";
import { CommitTypeBadge } from "../../components/CommitType";
import { Markdown } from "../../components/Markdown";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorNotice, Label, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/auth";
import type { Repo, Suspect } from "../../lib/types";
import { formatDate } from "../../lib/utils";

const RANK_LABEL = ["Most likely", "Second", "Third"];

function SuspectCard({ s, rank, repo }: { s: Suspect; rank: number; repo: Repo }) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <Badge tone={rank === 0 ? "danger" : "neutral"}>#{rank + 1} {RANK_LABEL[rank]}</Badge>
        <a href={`${repo.url}/commit/${s.sha}`} target="_blank" rel="noopener noreferrer"
           className="font-mono text-[12px] font-semibold text-accent hover:underline">{s.sha}</a>
        <CommitTypeBadge type={s.type} />
        {s.pr_number && (
          <a href={`${repo.url}/pull/${s.pr_number}`} target="_blank" rel="noopener noreferrer"
             className="inline-flex items-center gap-1 text-xs text-muted hover:text-text">
            <GitPullRequest className="size-3" />#{s.pr_number}
          </a>
        )}
        <span className="ml-auto text-xs text-subtle">{s.author} · {formatDate(s.timestamp)}</span>
      </div>
      <p className="mt-2 text-[14px] font-medium">{s.message}</p>
      <div className="mt-3 flex items-center gap-3">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2" role="meter" aria-valuemin={0}
             aria-valuemax={100} aria-valuenow={Math.round(s.score * 100)} aria-label="Suspicion score">
          <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(s.score * 100)}%` }} />
        </div>
        <span className="w-24 text-right text-xs text-muted tabular-nums">score {Math.round(s.score * 100)}/100</span>
      </div>
      <ul className="mt-3 space-y-1">
        {s.reasons.map((why) => (
          <li key={why} className="flex gap-2 text-[13px] text-muted">
            <Check className="mt-0.5 size-3.5 shrink-0 text-accent" /> {why}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function Suspects({ repo }: { repo: Repo }) {
  const { user } = useSession();
  const hasModel = !!(user.active_provider && user.active_model);
  const [description, setDescription] = useState("");
  const [since, setSince] = useState("");
  const find = useMutation({
    mutationFn: () => api.suspects(repo.id, description.trim(), since || null),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (description.trim().length >= 10) find.mutate();
  };
  const result = find.data;

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label htmlFor="bug-report" hint="An error message or stack trace helps most">Describe the bug</Label>
            <textarea id="bug-report" value={description} onChange={(e) => setDescription(e.target.value)} rows={5}
                      maxLength={5000} placeholder={"What went wrong, and any error or stack trace. For example:\n" +
                        "Payments are charged twice when a retry happens after the session expires\n" +
                        'File "src/checkout/session.py", line 42, in pay'}
                      className="block w-full resize-y rounded-lg border border-border bg-surface px-3 py-2 text-[13px] text-text outline-none transition-colors placeholder:text-subtle focus:border-accent focus:ring-3 focus:ring-accent-soft" />
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <Label htmlFor="bug-since">It worked before (optional)</Label>
              <input id="bug-since" type="date" value={since} onChange={(e) => setSince(e.target.value)}
                     className="h-10 rounded-lg border border-border bg-surface px-3 text-[13px] text-text outline-none focus:border-accent focus:ring-3 focus:ring-accent-soft" />
            </div>
            <Button type="submit" loading={find.isPending} disabled={description.trim().length < 10}>Find suspects</Button>
          </div>
          <p className="text-xs text-subtle">
            Commits are ranked by how well they match your report, whether they changed the files or code it names,
            how big they were, and whether they caused earlier bugs. Changes to only docs or tests are left out. With
            a date, only commits from that day on are considered.
          </p>
        </form>
      </Card>

      {find.error && <ErrorNotice error={find.error} />}
      {find.isPending && <Skeleton className="h-64 rounded-xl" />}

      {!find.isPending && !result && (
        <Card>
          <EmptyState icon={<FileSearch className="size-5" />} title="Find the commit that likely broke something"
                      description="Describe a bug and get the three most likely culprit commits, each with the reasons it was flagged." />
        </Card>
      )}

      {result && !find.isPending && (
        <>
          {result.mentioned_files.length > 0 && (
            <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted">
              Files named in your report:
              {result.mentioned_files.map((f) => <code key={f} className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-[11px]">{f}</code>)}
            </p>
          )}
          {result.suspects.length === 0 ? (
            <Card>
              <EmptyState icon={<SearchX className="size-5" />} title="No commit matches this report"
                          description="Try different words, include a file name or error message, or remove the date." />
            </Card>
          ) : (
            <>
              <div className="grid gap-4">
                {result.suspects.map((s, i) => <SuspectCard key={s.sha} s={s} rank={i} repo={repo} />)}
              </div>
              {result.answer ? (
                <Card>
                  <CardHeader title="What your model thinks" description="Based only on the suspect commits above"
                              action={result.provider && (
                                <span className="flex items-center gap-1.5 text-xs text-subtle">
                                  <ProviderMark id={result.provider} className="size-5 text-[8px]" />
                                  <span className="font-mono">{result.model}</span>
                                </span>
                              )} />
                  <div className="p-5"><Markdown repoUrl={repo.url}>{result.answer}</Markdown></div>
                </Card>
              ) : user.is_demo ? (
                <p className="rounded-lg border border-border bg-surface-2 px-4 py-3 text-[13px] text-muted">
                  The ranking above needs no model. With your own account and API key, your model also explains
                  each suspect. <Link to="/register" className="font-medium text-text underline">Sign up free</Link>
                </p>
              ) : !hasModel && (
                <div className="rounded-lg border border-warning/25 bg-warning-soft px-4 py-3 text-[13px] text-warning">
                  Connect a model to get an explanation of each suspect. <Link to="/app/settings" className="font-medium underline">Open settings</Link>
                </div>
              )}
            </>
          )}
          <p className="text-xs text-subtle">
            These are likely suspects, not proof. Confirm by testing the commit just before a suspect, or with git bisect.
          </p>
        </>
      )}
    </div>
  );
}
