import { useMutation, useQuery } from "@tanstack/react-query";
import { FileClock, Search } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ProviderMark } from "../../components/brand";
import { CommitTypeBadge } from "../../components/CommitType";
import { Markdown } from "../../components/Markdown";
import { Button, Card, CardHeader, EmptyState, ErrorNotice, Input, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { useSession } from "../../lib/auth";
import { tooltipStyle, useThemeColors } from "../../lib/theme";
import type { Repo } from "../../lib/types";
import { formatDate, shortSha } from "../../lib/utils";

export function Timeline({ repo }: { repo: Repo }) {
  const { user } = useSession();
  const [path, setPath] = useState("");
  const files = useQuery({ queryKey: ["repo-data", repo.id, "files"], queryFn: () => api.files(repo.id) });
  const trace = useMutation({ mutationFn: (p: string) => api.timeline(repo.id, p) });
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

  const submit = (e: FormEvent) => { e.preventDefault(); if (path.trim()) trace.mutate(path.trim()); };
  const result = trace.data;

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
            <Input list="repo-files" value={path} onChange={(e) => setPath(e.target.value)}
                   placeholder="File name or path, e.g. sessions.py" className="pl-9 font-mono text-[13px]"
                   aria-label="File to trace" />
            <datalist id="repo-files">
              {files.data?.map((f) => <option key={f} value={f} />)}
            </datalist>
          </div>
          <Button type="submit" loading={trace.isPending} disabled={!path.trim() || !hasModel}>Trace evolution</Button>
        </form>
        <p className="mt-2 text-xs text-subtle">
          Matches any path containing your text. {files.data && `${files.data.length} files were touched in the ingested history.`}
        </p>
      </Card>

      {trace.error && <ErrorNotice error={trace.error} />}
      {trace.isPending && <Skeleton className="h-60 rounded-xl" />}

      {!trace.isPending && !result && (
        <Card>
          <EmptyState icon={<FileClock className="size-5" />} title="Trace how a file evolved"
                      description="Get the phases of change, who drove them and recurring patterns — plus every commit that touched it." />
        </Card>
      )}

      {result && result.entries.length === 0 && (
        <Card><EmptyState icon={<Search className="size-5" />} title={`No commits touched “${result.path}”`}
                          description="Try a shorter name, or pick a file from the suggestions." /></Card>
      )}

      {result && result.entries.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-5">
          <Card className="lg:col-span-3">
            <CardHeader title="Evolution summary" description={<span className="font-mono">{result.path}</span>}
                        action={result.provider && (
                          <span className="flex items-center gap-1.5 text-xs text-subtle">
                            <ProviderMark id={result.provider} className="size-5 text-[8px]" />
                            <span className="font-mono">{result.model}</span>
                          </span>
                        )} />
            <div className="p-5">{result.answer && <Markdown repoUrl={repo.url}>{result.answer}</Markdown>}</div>
          </Card>
          <div className="space-y-4 lg:col-span-2">
            <Card>
              <CardHeader title="Changes per month" />
              <div className="h-40 px-2 pt-3 pb-1">
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
        </div>
      )}
    </div>
  );
}
