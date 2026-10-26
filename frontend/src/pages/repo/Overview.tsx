import { useQuery } from "@tanstack/react-query";
import { FileCode2, GitCommitHorizontal, GitPullRequest, Minus, Plus, Users } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardHeader, ErrorNotice, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { tooltipStyle, useThemeColors } from "../../lib/theme";
import type { CommitType, Repo } from "../../lib/types";
import { basename, COMMIT_TYPES, formatDate, formatNumber } from "../../lib/utils";

function Stat({ icon, label, value, sub }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs text-muted">{icon}{label}</div>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-subtle">{sub}</p>}
    </Card>
  );
}

export function Overview({ repo }: { repo: Repo }) {
  const overview = useQuery({ queryKey: ["repo-data", repo.id, "overview"], queryFn: () => api.overview(repo.id) });
  const hot = useQuery({ queryKey: ["repo-data", repo.id, "hotfiles", 6], queryFn: () => api.hotfiles(repo.id, 6) });
  const authors = useQuery({ queryKey: ["repo-data", repo.id, "authors"], queryFn: () => api.authors(repo.id) });
  const c = useThemeColors();

  if (overview.error) return <ErrorNotice error={overview.error} />;
  if (!overview.data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px] rounded-xl" />)}
        <Skeleton className="h-72 rounded-xl sm:col-span-2 lg:col-span-4" />
      </div>
    );
  }
  const o = overview.data;
  const types = (Object.entries(o.types) as [CommitType, number][])
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => ({ type, count, ...COMMIT_TYPES[type] }));
  const maxAuthor = authors.data?.[0]?.commits ?? 1;
  const maxHot = hot.data?.[0]?.changes ?? 1;

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={<GitCommitHorizontal className="size-3.5" />} label="Commits" value={formatNumber(o.commits)}
              sub={`${formatDate(o.first_commit)} → ${formatDate(o.last_commit)}`} />
        <Stat icon={<Users className="size-3.5" />} label="Contributors" value={formatNumber(o.authors)} />
        <Stat icon={<FileCode2 className="size-3.5" />} label="Files touched" value={formatNumber(o.files)}
              sub={<span className="inline-flex items-center gap-2">
                <span className="inline-flex items-center text-success"><Plus className="size-3" />{formatNumber(o.insertions)}</span>
                <span className="inline-flex items-center text-danger"><Minus className="size-3" />{formatNumber(o.deletions)}</span>
              </span>} />
        <Stat icon={<GitPullRequest className="size-3.5" />} label="Linked pull requests" value={formatNumber(o.prs)}
              sub={o.prs ? "with descriptions & reviews" : "none matched these commits"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Commit activity" description="Commits per week" />
          <div className="h-64 px-2 pt-4 pb-2">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={o.activity} margin={{ left: -18, right: 12, top: 4 }}>
                <defs>
                  <linearGradient id="activityFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c.accent} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={c.accent} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="week" tick={{ fontSize: 11, fill: c.subtle }} axisLine={false} tickLine={false} minTickGap={24} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: c.subtle }} axisLine={false} tickLine={false} />
                <Tooltip {...tooltipStyle(c)} cursor={{ stroke: c.border }} />
                <Area type="monotone" dataKey="commits" stroke={c.accent} strokeWidth={2} fill="url(#activityFill)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <CardHeader title="Change types" description="Classified from commit messages" />
          <div className="flex items-center gap-4 p-5">
            <div className="size-32 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={types} dataKey="count" nameKey="label" innerRadius={38} outerRadius={60} paddingAngle={2} stroke="none">
                    {types.map((t) => <Cell key={t.type} fill={t.color} />)}
                  </Pie>
                  <Tooltip {...tooltipStyle(c)} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <ul className="min-w-0 flex-1 space-y-1.5 text-[13px]">
              {types.map((t) => (
                <li key={t.type} className="flex items-center gap-2">
                  <span className="size-2 rounded-full" style={{ background: t.color }} />
                  <span className="flex-1 text-muted">{t.label}</span>
                  <span className="font-mono text-xs">{t.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Hottest files" action={<Link to={`/app/repos/${repo.id}/hotfiles`} className="text-xs text-accent hover:underline">View all</Link>} />
          <ul className="space-y-3 p-5">
            {hot.data?.map((h) => (
              <li key={h.file}>
                <div className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="truncate font-mono text-xs" title={h.file}>{h.file}</span>
                  <span className="shrink-0 text-xs text-muted">{h.changes}×</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-accent" style={{ width: `${(h.changes / maxHot) * 100}%` }} />
                </div>
              </li>
            ))}
            {!hot.data && <Skeleton className="h-40" />}
          </ul>
        </Card>
        <Card>
          <CardHeader title="Top contributors" action={<Link to={`/app/repos/${repo.id}/authors`} className="text-xs text-accent hover:underline">View all</Link>} />
          <ul className="space-y-3 p-5">
            {authors.data?.slice(0, 6).map((a) => (
              <li key={a.author}>
                <div className="flex items-center justify-between gap-3 text-[13px]">
                  <span className="truncate">{a.author}</span>
                  <span className="shrink-0 text-xs text-muted" title={a.top_files[0]?.file}>
                    {a.commits} commits{a.top_files[0] && <> · mostly {basename(a.top_files[0].file)}</>}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full rounded-full bg-success" style={{ width: `${(a.commits / maxAuthor) * 100}%` }} />
                </div>
              </li>
            ))}
            {!authors.data && <Skeleton className="h-40" />}
          </ul>
        </Card>
      </div>
    </div>
  );
}
