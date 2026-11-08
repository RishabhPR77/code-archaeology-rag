import { useQuery } from "@tanstack/react-query";
import { Bug, Clock, History, Search, Wrench } from "lucide-react";
import { useState } from "react";

import { CommitTypeBadge } from "../../components/CommitType";
import { Badge, Card, CardHeader, EmptyState, ErrorNotice, Segmented, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import type { BugFix, Repo } from "../../lib/types";
import { formatDate } from "../../lib/utils";
import { Stat } from "./Overview";

type Filter = "all" | "traced" | "untraced";

const UNTRACED: Record<Exclude<BugFix["status"], "traced">, string> = {
  older: "The lines it changed were written before the oldest ingested commit, so their origin is out of reach.",
  nothing_to_trace: "It only added new code, or only changed docs and tests, so there's no earlier line to trace back.",
  error: "Git couldn't compare this commit with the one before it.",
};

function lifetime(days: number) {
  const d = Math.round(days);
  return d === 0 ? "under a day" : d === 1 ? "1 day" : `${d} days`;
}

function CommitLink({ repo, sha }: { repo: Repo; sha: string }) {
  return (
    <a href={`${repo.url}/commit/${sha}`} target="_blank" rel="noopener noreferrer"
       className="font-mono text-[12px] font-semibold text-accent hover:underline">{sha}</a>
  );
}

function FixRow({ fix, repo }: { fix: BugFix; repo: Repo }) {
  return (
    <li className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <CommitTypeBadge type="fix" />
        <CommitLink repo={repo} sha={fix.sha} />
        <span className="min-w-0 flex-1 basis-60 text-[13px] font-medium">{fix.message}</span>
        <span className="text-xs text-subtle">{fix.author} · {formatDate(fix.timestamp)}</span>
      </div>
      {fix.status === "traced" ? (
        <>
          <ul className="mt-3 space-y-2 border-l-2 border-border pl-4 sm:ml-2">
            {fix.origins.map((o, i) => (
              <li key={o.sha} className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[13px]">
                <span className={i === 0 ? "text-xs font-semibold text-danger" : "text-xs font-medium text-muted"}>
                  {i === 0 ? "Likely cause" : "Also involved"}
                </span>
                <CommitLink repo={repo} sha={o.sha} />
                <span className="min-w-0 flex-1 basis-48">{o.message}</span>
                <span className="text-xs text-subtle">
                  {o.author} · {formatDate(o.timestamp)} · {o.lines} {o.lines === 1 ? "line" : "lines"}
                </span>
                {!o.ingested && <Badge>before the ingested commits</Badge>}
              </li>
            ))}
          </ul>
          {fix.days !== null && <p className="mt-2 text-xs text-muted sm:ml-2">The bug lived about {lifetime(fix.days)}.</p>}
        </>
      ) : (
        <p className="mt-2 text-xs text-muted">{UNTRACED[fix.status]}</p>
      )}
    </li>
  );
}

export function BugOrigins({ repo }: { repo: Repo }) {
  const origins = useQuery({ queryKey: ["repo-data", repo.id, "origins"], queryFn: () => api.origins(repo.id) });
  const [filter, setFilter] = useState<Filter>("all");

  if (origins.error) return <ErrorNotice error={origins.error} />;
  if (!origins.data) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px] rounded-xl" />)}
        <Skeleton className="h-72 rounded-xl sm:col-span-2 lg:col-span-4" />
      </div>
    );
  }
  const { summary: s, fixes } = origins.data;
  if (!origins.data.computed || !s) {
    return (
      <Card>
        <EmptyState icon={<History className="size-5" />} title="Bug origins haven't been traced yet"
                    description="This repository was ingested before Bug origins existed. Use Re-sync at the top of the page to trace them." />
      </Card>
    );
  }
  if (fixes.length === 0) {
    return (
      <Card>
        <EmptyState icon={<Bug className="size-5" />} title="No bug fixes in the ingested history"
                    description="Bug origins start from commits whose message mentions a fix, bug, error or crash." />
      </Card>
    );
  }

  const shown = fixes.filter((f) => filter === "all" || (filter === "traced") === (f.status === "traced"));
  return (
    <div className="space-y-4">
      <p className="max-w-3xl text-[13px] text-muted">
        Each bug fix is traced back to the commits that last wrote the lines it fixed, using git blame (the SZZ method).
        These are likely causes worth checking, not proof. Blank lines, comments, docs and tests are ignored.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat icon={<Wrench className="size-3.5" />} label="Bug fixes" value={s.fixes} sub="commits that mention a fix" />
        <Stat icon={<Bug className="size-3.5" />} label="Traced to a likely cause" value={s.traced}
              sub={`${Math.round((s.traced / s.fixes) * 100)}% of fixes`} />
        <Stat icon={<Clock className="size-3.5" />} label="Median time a bug lived"
              value={s.median_days === null ? "—" : lifetime(s.median_days)} sub="from the cause to the fix" />
        <Stat icon={<History className="size-3.5" />} label="Older than this history" value={s.older}
              sub="cause predates the ingested commits" />
      </div>

      {s.repeat_origins.length > 0 && (
        <Card>
          <CardHeader title="Commits behind more than one fix"
                      description="Changes that later needed several fixes are worth a second look." />
          <ul className="divide-y divide-border">
            {s.repeat_origins.map((o) => (
              <li key={o.sha} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3 text-[13px]">
                <CommitLink repo={repo} sha={o.sha} />
                <span className="min-w-0 flex-1 basis-60">{o.message}</span>
                <span className="text-xs text-subtle">{o.author} · {formatDate(o.timestamp)}</span>
                <Badge tone="warning">{o.fixes} fixes</Badge>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CardHeader title="Every fix, traced back" description="Newest fix first"
                    action={<Segmented size="sm" value={filter} onChange={setFilter} options={[
                      { value: "all", label: "All" }, { value: "traced", label: "Traced" },
                      { value: "untraced", label: "Not traced" },
                    ]} />} />
        {shown.length === 0 ? (
          <EmptyState icon={<Search className="size-5" />} title="Nothing in this view" description="Try another filter." />
        ) : (
          <ol className="divide-y divide-border">
            {shown.map((f) => <FixRow key={f.sha} fix={f} repo={repo} />)}
          </ol>
        )}
      </Card>
    </div>
  );
}
