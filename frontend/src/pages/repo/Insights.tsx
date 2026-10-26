import { useQuery } from "@tanstack/react-query";
import { ArrowLeftRight, Minus, Plus } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardHeader, EmptyState, ErrorNotice, Segmented, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { tooltipStyle, useThemeColors } from "../../lib/theme";
import type { Repo } from "../../lib/types";
import { basename, formatDate, formatNumber } from "../../lib/utils";

export function HotFiles({ repo }: { repo: Repo }) {
  const [limit, setLimit] = useState(15);
  const hot = useQuery({ queryKey: ["repo-data", repo.id, "hotfiles", limit], queryFn: () => api.hotfiles(repo.id, limit) });
  const c = useThemeColors();

  if (hot.error) return <ErrorNotice error={hot.error} />;
  const data = (hot.data ?? []).map((h) => ({ ...h, name: basename(h.file) }));
  const max = data[0]?.changes ?? 1;

  return (
    <Card>
      <CardHeader title="Hot files" description="Files changed most often — where complexity and history concentrate."
                  action={<Segmented size="sm" value={limit} onChange={setLimit}
                                     options={[10, 15, 25].map((v) => ({ value: v, label: v }))} />} />
      <div className="grid gap-6 p-5 lg:grid-cols-2">
        <div style={{ height: Math.max(240, data.length * 28) }}>
          {hot.isPending ? <Skeleton className="h-full" /> : (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ left: 0, right: 16 }}>
                <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: c.subtle }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11, fill: c.muted }} axisLine={false} tickLine={false} />
                <Tooltip {...tooltipStyle(c)} labelFormatter={(_, p) => p?.[0]?.payload?.file ?? ""} />
                <Bar dataKey="changes" radius={[0, 4, 4, 0]}>
                  {data.map((d) => <Cell key={d.file} fill={c.accent} fillOpacity={0.35 + 0.65 * (d.changes / max)} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-border text-left text-xs text-subtle">
              <th className="pb-2 font-medium">#</th><th className="pb-2 font-medium">File</th><th className="pb-2 text-right font-medium">Changes</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d, i) => (
              <tr key={d.file} className="border-b border-border last:border-0">
                <td className="py-2 pr-3 text-xs text-subtle">{i + 1}</td>
                <td className="max-w-0 truncate py-2 font-mono text-xs" title={d.file}>{d.file}</td>
                <td className="py-2 text-right font-mono text-xs">{d.changes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function CoChange({ repo }: { repo: Repo }) {
  const [limit, setLimit] = useState(15);
  const pairs = useQuery({ queryKey: ["repo-data", repo.id, "cochange", limit], queryFn: () => api.cochange(repo.id, limit) });

  if (pairs.error) return <ErrorNotice error={pairs.error} />;
  const max = pairs.data?.[0]?.co_changes ?? 1;

  return (
    <Card>
      <CardHeader title="Co-change analysis"
                  description="File pairs that are usually modified in the same commit — coupling static analysis misses."
                  action={<Segmented size="sm" value={limit} onChange={setLimit}
                                     options={[10, 15, 30].map((v) => ({ value: v, label: v }))} />} />
      {pairs.isPending ? <div className="p-5"><Skeleton className="h-64" /></div> :
        pairs.data?.length === 0 ? (
          <EmptyState icon={<ArrowLeftRight className="size-5" />} title="No files changed together"
                      description="Every commit in this history touched a single file." />
        ) : (
          <ul className="divide-y divide-border">
            {pairs.data?.map((p) => (
              <li key={`${p.file_a}|${p.file_b}`} className="flex items-center gap-4 px-5 py-3">
                <div className="grid min-w-0 flex-1 items-center gap-1 sm:grid-cols-[1fr_auto_1fr] sm:gap-3">
                  <span className="truncate font-mono text-xs" title={p.file_a}>{p.file_a}</span>
                  <ArrowLeftRight className="hidden size-3.5 text-subtle sm:block" />
                  <span className="truncate font-mono text-xs" title={p.file_b}>{p.file_b}</span>
                </div>
                <div className="flex w-36 shrink-0 items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                    <div className="h-full rounded-full bg-success" style={{ width: `${(p.co_changes / max) * 100}%` }} />
                  </div>
                  <span className="w-8 text-right font-mono text-xs">{p.co_changes}×</span>
                </div>
              </li>
            ))}
          </ul>
        )}
    </Card>
  );
}

export function Authors({ repo }: { repo: Repo }) {
  const authors = useQuery({ queryKey: ["repo-data", repo.id, "authors"], queryFn: () => api.authors(repo.id) });
  if (authors.error) return <ErrorNotice error={authors.error} />;
  if (!authors.data) return <div className="grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-52 rounded-xl" />)}</div>;
  const total = authors.data.reduce((s, a) => s + a.commits, 0) || 1;

  return (
    <div>
      <p className="mb-4 text-[13px] text-muted">
        Who built what — and what knowledge would walk out the door if they left.
      </p>
      <div className="grid gap-4 md:grid-cols-2">
        {authors.data.map((a) => (
          <Card key={a.author} className="p-5">
            <div className="flex items-start gap-3">
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-accent-soft text-sm font-semibold text-accent">
                {a.author[0]?.toUpperCase()}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{a.author}</p>
                <p className="text-xs text-subtle">{formatDate(a.first_commit)} – {formatDate(a.last_commit)}</p>
              </div>
              <div className="text-right">
                <p className="text-lg font-semibold leading-none">{a.commits}</p>
                <p className="mt-1 text-[11px] text-subtle">{Math.round((a.commits / total) * 100)}% of commits</p>
              </div>
            </div>
            <div className="mt-3 flex gap-3 text-xs">
              <span className="inline-flex items-center text-success"><Plus className="size-3" />{formatNumber(a.insertions)}</span>
              <span className="inline-flex items-center text-danger"><Minus className="size-3" />{formatNumber(a.deletions)}</span>
            </div>
            <ul className="mt-4 space-y-1.5 border-t border-border pt-3">
              {a.top_files.map((f) => (
                <li key={f.file} className="flex items-center justify-between gap-3 text-xs">
                  <span className="truncate font-mono text-muted" title={f.file}>{f.file}</span>
                  <span className="shrink-0 font-mono text-subtle">{f.changes}×</span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  );
}
