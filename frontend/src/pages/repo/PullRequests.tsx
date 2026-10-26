import { useQuery } from "@tanstack/react-query";
import { ExternalLink, GitMerge, GitPullRequest } from "lucide-react";

import { Badge, Card, EmptyState, ErrorNotice, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import type { Repo } from "../../lib/types";
import { formatDate, shortSha } from "../../lib/utils";

export function PullRequests({ repo }: { repo: Repo }) {
  const pulls = useQuery({ queryKey: ["repo-data", repo.id, "pulls"], queryFn: () => api.pulls(repo.id) });
  if (pulls.error) return <ErrorNotice error={pulls.error} />;
  if (!pulls.data) return <Skeleton className="h-80 rounded-xl" />;

  if (pulls.data.length === 0) {
    return (
      <Card>
        <EmptyState icon={<GitPullRequest className="size-5" />} title="No pull requests matched these commits"
                    description="The repository may commit straight to its default branch, or GitHub's API limit was reached during ingest. Re-sync to try again." />
      </Card>
    );
  }

  return (
    <div>
      <p className="mb-4 text-[13px] text-muted">
        {pulls.data.length} merged pull requests linked to ingested commits. Their descriptions and reviews feed every answer.
      </p>
      <Card className="divide-y divide-border">
        {pulls.data.map((pr) => (
          <a key={pr.number} href={`${repo.url}/pull/${pr.number}`} target="_blank" rel="noopener noreferrer"
             className="group flex items-start gap-3 px-5 py-4 transition-colors hover:bg-surface-2/50">
            <GitMerge className="mt-0.5 size-4 shrink-0 text-accent" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-medium group-hover:text-accent">{pr.title}</span>
                {pr.labels.map((l) => <Badge key={l}>{l}</Badge>)}
              </div>
              <p className="mt-1 text-xs text-subtle">
                #{pr.number} by <span className="text-muted">{pr.author}</span> · merged {formatDate(pr.merged_at)} ·
                commit <span className="font-mono">{shortSha(pr.commit_sha)}</span> · {pr.files.length} files
              </p>
            </div>
            <ExternalLink className="size-3.5 shrink-0 text-subtle opacity-0 transition-opacity group-hover:opacity-100" />
          </a>
        ))}
      </Card>
    </div>
  );
}
