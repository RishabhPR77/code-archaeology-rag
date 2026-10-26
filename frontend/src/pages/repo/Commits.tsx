import { useQuery } from "@tanstack/react-query";
import { GitPullRequest, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { CommitTypeBadge } from "../../components/CommitType";
import { Card, EmptyState, ErrorNotice, Input, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import type { CommitType, Repo } from "../../lib/types";
import { cn, COMMIT_TYPES, formatDate, shortSha } from "../../lib/utils";

export function Commits({ repo }: { repo: Repo }) {
  const commits = useQuery({ queryKey: ["repo-data", repo.id, "commits"], queryFn: () => api.commits(repo.id) });
  const [q, setQ] = useState("");
  const [type, setType] = useState<CommitType | null>(null);

  const counts = useMemo(() => {
    const m = new Map<CommitType, number>();
    for (const c of commits.data ?? []) m.set(c.type, (m.get(c.type) ?? 0) + 1);
    return m;
  }, [commits.data]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (commits.data ?? []).filter((c) =>
      (!type || c.type === type) &&
      (!needle || `${c.sha} ${c.message} ${c.author} ${c.files.join(" ")}`.toLowerCase().includes(needle)));
  }, [commits.data, q, type]);

  if (commits.error) return <ErrorNotice error={commits.error} />;
  if (!commits.data) return <Skeleton className="h-96 rounded-xl" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative lg:w-80">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search message, author, file or SHA"
                 className="pl-9 text-[13px]" aria-label="Search commits" />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(COMMIT_TYPES) as CommitType[]).filter((t) => counts.get(t)).map((t) => (
            <button key={t} onClick={() => setType(type === t ? null : t)} aria-pressed={type === t}
                    className={cn("inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors cursor-pointer",
                      type === t ? "border-accent bg-accent-soft text-text" : "border-border text-muted hover:text-text")}>
              <span className="size-1.5 rounded-full" style={{ background: COMMIT_TYPES[t].color }} />
              {COMMIT_TYPES[t].label} <span className="text-subtle">{counts.get(t)}</span>
            </button>
          ))}
        </div>
        <span className="text-xs text-subtle lg:ml-auto">{filtered.length} of {commits.data.length} commits</span>
      </div>

      <Card className="overflow-hidden">
        {filtered.length === 0 ? (
          <EmptyState icon={<Search className="size-5" />} title="No commits match" description="Try a different search or filter." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-[13px]">
              <thead>
                <tr className="border-b border-border bg-surface-2/50 text-left text-xs text-subtle">
                  <th className="px-4 py-2.5 font-medium">Commit</th>
                  <th className="px-4 py-2.5 font-medium">Message</th>
                  <th className="px-4 py-2.5 font-medium">Author</th>
                  <th className="px-4 py-2.5 font-medium">Date</th>
                  <th className="px-4 py-2.5 text-right font-medium">Lines</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.sha} className="border-b border-border last:border-0 hover:bg-surface-2/40">
                    <td className="px-4 py-3 align-top">
                      <a href={`${repo.url}/commit/${c.sha}`} target="_blank" rel="noopener noreferrer"
                         className="font-mono text-xs font-semibold text-accent hover:underline">{shortSha(c.sha)}</a>
                    </td>
                    <td className="max-w-md px-4 py-3 align-top">
                      <div className="flex items-start gap-2">
                        <CommitTypeBadge type={c.type} />
                        <span className="leading-snug">{c.message}</span>
                      </div>
                      <p className="mt-1 truncate font-mono text-[11px] text-subtle" title={c.files.join("\n")}>
                        {c.pr_number && <span className="mr-2 inline-flex items-center gap-0.5 text-muted"><GitPullRequest className="size-3" />#{c.pr_number}</span>}
                        {c.files.slice(0, 3).join(", ")}{c.files.length > 3 && ` +${c.files.length - 3}`}
                      </p>
                    </td>
                    <td className="px-4 py-3 align-top text-muted">{c.author}</td>
                    <td className="px-4 py-3 align-top whitespace-nowrap text-muted">{formatDate(c.timestamp)}</td>
                    <td className="px-4 py-3 text-right align-top font-mono text-xs whitespace-nowrap">
                      <span className="text-success">+{c.insertions}</span> <span className="text-danger">−{c.deletions}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
