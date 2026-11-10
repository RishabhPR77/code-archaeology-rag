import { useMutation, useQuery } from "@tanstack/react-query";
import { FileClock, Search } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ProviderMark } from "../../components/brand";
import { CommitTypeBadge } from "../../components/CommitType";
import { choiceLabel, FilePicker, type FileChoice } from "../../components/FilePicker";
import { Markdown } from "../../components/Markdown";
import { Button, Card, CardHeader, EmptyState, ErrorNotice, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/auth";
import { tooltipStyle, useThemeColors } from "../../lib/theme";
import type { Repo } from "../../lib/types";
import { formatDate, shortSha } from "../../lib/utils";

function describe(c: FileChoice) {
  if (c.match === "exact") return <span className="font-mono">{c.path}</span>;
  if (c.match === "folder") return <>Every file in <span className="font-mono">{c.path}/</span></>;
  return <>Every path containing <span className="font-mono">“{c.path}”</span></>;
}

export function Timeline({ repo }: { repo: Repo }) {
  const { user } = useSession();
  const [query, setQuery] = useState("");
  const [choice, setChoice] = useState<FileChoice | null>(null);
  const files = useQuery({ queryKey: ["repo-data", repo.id, "files"], queryFn: () => api.files(repo.id) });
  const trace = useMutation({ mutationFn: (c: FileChoice) => api.timeline(repo.id, c.path, c.match) });
  const c = useThemeColors();
  const hasModel = !!(user.active_provider && user.active_model);

  const monthly = useMemo(() => {
    const counts = new Map<string, number>();
    for (const e of trace.data?.entries ?? []) {
      const m = e.timestamp.slice(0, 7);
      counts.set(m, (counts.get(m) ?? 0) + 1);
    }
    return [...counts].map(([month, commits]) => ({ month, commits }));
  }, [trace.data]);

  const run = (next: FileChoice) => {
    setChoice(next);
    setQuery(choiceLabel(next));
    trace.mutate(next);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    // Keep a picked file or folder; anything typed by hand searches every path containing it
    run(choice && choiceLabel(choice) === q ? choice : { path: q, match: "contains" });
  };
  const result = trace.data;
  const traced = trace.variables;

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
          <FilePicker files={files.data} loading={files.isPending} query={query}
                      onQueryChange={(q) => { setQuery(q); setChoice(null); }} onPick={run} />
          <Button type="submit" loading={trace.isPending} disabled={!query.trim()}>Trace evolution</Button>
        </form>
        <p className="mt-2 text-xs text-subtle">
          Pick a file or folder from the list, or press Enter to trace every path containing your text.
          {files.data && ` ${files.data.length} files were touched in the ingested history.`}
        </p>
      </Card>

      {files.error && <ErrorNotice error={files.error} />}
      {trace.error && <ErrorNotice error={trace.error} />}
      {trace.isPending && <Skeleton className="h-60 rounded-xl" />}

      {!trace.isPending && !result && (
        <Card>
          <EmptyState icon={<FileClock className="size-5" />} title="Trace how a file evolved"
                      description={hasModel
                        ? "Get the phases of change, who drove them and recurring patterns, plus every commit that touched it."
                        : user.is_demo ? "See every commit that touched it, month by month."
                        : "See every commit that touched it, month by month. Connect a model to also get a written summary."} />
        </Card>
      )}

      {result && traced && result.entries.length === 0 && (
        <Card><EmptyState icon={<Search className="size-5" />} title="No commits found"
                          description={<>Nothing in the ingested history touched {describe(traced)}. Try picking a file from the list.</>} /></Card>
      )}

      {result && traced && result.entries.length > 0 && (
        <>
          {result.answer ? (
            <Card>
              <CardHeader title="Evolution summary" description={describe(traced)}
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
              Showing every commit that touched {describe(traced)}. With your own account and API key, your model also
              writes a summary of how it evolved. <Link to="/register" className="font-medium text-text underline">Sign up free</Link>
            </p>
          ) : (
            <div className="rounded-lg border border-warning/25 bg-warning-soft px-4 py-3 text-[13px] text-warning">
              Connect a model to get a written summary of how {describe(traced)} evolved.{" "}
              <Link to="/app/settings" className="font-medium underline">Open settings</Link>
            </div>
          )}
          <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
            <Card>
              <CardHeader title="Changes per month" />
              <div className="h-56 px-2 pt-3 pb-1">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={monthly} margin={{ left: -24, right: 8 }}>
                    <XAxis dataKey="month" tick={{ fontSize: 10, fill: c.subtle }} axisLine={false} tickLine={false} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: c.subtle }} axisLine={false} tickLine={false} />
                    <Tooltip {...tooltipStyle(c)} />
                    <Bar dataKey="commits" fill={c.accent} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card>
              <CardHeader title={`${result.entries.length} commits`} description="Oldest first" />
              <ol className="max-h-[420px] overflow-y-auto p-5">
                {result.entries.map((e, i) => (
                  <li key={e.sha} className="relative flex gap-3 pb-5 last:pb-0">
                    {i < result.entries.length - 1 && <span className="absolute top-3 left-[5px] h-full w-px bg-border" />}
                    <span className="relative mt-1.5 size-[11px] shrink-0 rounded-full border-2 border-accent bg-surface" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <a href={`${repo.url}/commit/${e.sha}`} target="_blank" rel="noopener noreferrer"
                           className="font-mono font-semibold text-accent hover:underline">{shortSha(e.sha)}</a>
                        <CommitTypeBadge type={e.type} />
                        <span className="text-subtle">{formatDate(e.timestamp)}</span>
                      </div>
                      <p className="mt-1 text-[13px] leading-snug">{e.message}</p>
                      <p className="mt-0.5 text-xs text-muted">{e.author}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
