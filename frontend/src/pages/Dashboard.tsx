import { ArrowRight, CheckCircle2, Circle, Clock, FolderGit2, GitCommitHorizontal, GitPullRequest, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { NewRepoDialog } from "../components/NewRepoDialog";
import { Badge, Button, Card, EmptyState, ErrorNotice, Skeleton } from "../components/ui";
import { useSession } from "../lib/auth";
import { useRepos } from "../lib/queries";
import type { Repo } from "../lib/types";
import { cn, formatNumber, isIngesting, relativeTime } from "../lib/utils";

export function RepoStatusBadge({ repo }: { repo: Repo }) {
  if (repo.status === "ready") return <Badge tone="success">Ready</Badge>;
  if (repo.status === "failed") return <Badge tone="danger">Failed</Badge>;
  return <Badge tone="warning"><span className="size-1.5 animate-pulse rounded-full bg-warning" /> Ingesting</Badge>;
}

function RepoCard({ repo }: { repo: Repo }) {
  return (
    <Link to={`/app/repos/${repo.id}`} className="group">
      <Card className="flex h-full flex-col p-5 transition-colors group-hover:border-border-strong">
        <div className="flex items-start justify-between gap-3">
          <div className="grid size-9 place-items-center rounded-lg bg-surface-2 text-muted">
            <FolderGit2 className="size-4" />
          </div>
          <RepoStatusBadge repo={repo} />
        </div>
        <h3 className="mt-4 truncate font-mono text-[13px] font-semibold">{repo.full_name}</h3>
        <p className="mt-1 line-clamp-1 text-xs text-muted">
          {isIngesting(repo.status) ? repo.stage_message : repo.status === "failed" ? repo.error : `Ingested ${relativeTime(repo.ready_at)}`}
        </p>
        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 pt-5 text-xs text-subtle">
          <span className="inline-flex items-center gap-1"><GitCommitHorizontal className="size-3.5" />{formatNumber(repo.commit_count)} commits</span>
          <span className="inline-flex items-center gap-1"><GitPullRequest className="size-3.5" />{formatNumber(repo.pr_count)} PRs</span>
          {repo.expires_at && (
            <span className="inline-flex items-center gap-1" title="Repositories are removed automatically">
              <Clock className="size-3.5" />expires {relativeTime(repo.expires_at)}
            </span>
          )}
        </div>
      </Card>
    </Link>
  );
}

function SetupChecklist({ hasModel, hasRepo, onNewRepo }: { hasModel: boolean; hasRepo: boolean; onNewRepo: () => void }) {
  const steps = [
    { done: hasModel, title: "Connect a model provider", body: "Add your Anthropic, OpenAI, Gemini, Groq or OpenRouter key and pick a model.",
      action: <Link to="/app/settings"><Button size="sm" variant={hasModel ? "secondary" : "primary"}>Open settings</Button></Link> },
    { done: hasRepo, title: "Ingest a repository", body: "Paste a public GitHub URL. Commits, PRs and reviews are indexed in a few minutes.",
      action: <Button size="sm" variant={hasModel && !hasRepo ? "primary" : "secondary"} onClick={onNewRepo}>New repository</Button> },
    { done: false, title: "Ask why", body: "Open a repository and ask about any change in plain English.", action: null },
  ];
  return (
    <Card className="p-6">
      <h2 className="text-sm font-semibold">Get set up</h2>
      <p className="mt-0.5 text-[13px] text-muted">Two quick steps and you're ready to ask questions.</p>
      <ol className="mt-5 space-y-4">
        {steps.map((s, i) => (
          <li key={s.title} className="flex gap-3">
            {s.done ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" /> : <Circle className="mt-0.5 size-5 shrink-0 text-border-strong" />}
            <div className="min-w-0 flex-1">
              <p className={cn("text-[13px] font-medium", s.done && "text-muted line-through")}>{i + 1}. {s.title}</p>
              <p className="mt-0.5 text-xs text-muted">{s.body}</p>
            </div>
            {!s.done && s.action}
          </li>
        ))}
      </ol>
    </Card>
  );
}

export default function Dashboard() {
  const { user, limits } = useSession();
  const repos = useRepos();
  const [newOpen, setNewOpen] = useState(false);
  const hasModel = !!(user.active_provider && user.active_model);
  const hasRepo = (repos.data?.length ?? 0) > 0;
  const firstName = (user.name || user.email.split("@")[0]).split(" ")[0];

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back, {firstName}</h1>
          <p className="mt-1 text-sm text-muted">Your repositories and what's happening with them.</p>
        </div>
        {!limits.unlimited && (
          <div className="flex gap-6 text-right text-xs text-subtle">
            <div><p className="text-lg font-semibold text-text">{limits.repos_used}/{limits.max_repos}</p>repositories</div>
            <div><p className="text-lg font-semibold text-text">{limits.ingests_today}/{limits.max_ingests_day}</p>ingests · 24h</div>
          </div>
        )}
      </div>

      {(!hasModel || !hasRepo) && !repos.isPending && (
        <div className="mt-8"><SetupChecklist hasModel={hasModel} hasRepo={hasRepo} onNewRepo={() => setNewOpen(true)} /></div>
      )}

      <section className="mt-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Repositories</h2>
          {hasRepo && <Button size="sm" variant="secondary" onClick={() => setNewOpen(true)}><Plus className="size-3.5" /> Add</Button>}
        </div>
        {repos.error && <ErrorNotice error={repos.error} />}
        {repos.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-44 rounded-xl" />)}
          </div>
        ) : hasRepo ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {repos.data!.map((r) => <RepoCard key={r.id} repo={r} />)}
          </div>
        ) : (
          <Card>
            <EmptyState icon={<FolderGit2 className="size-5" />} title="No repositories yet"
                        description="Ingest a public GitHub repository to start asking questions about its history."
                        action={<Button onClick={() => setNewOpen(true)}>Ingest a repository <ArrowRight className="size-4" /></Button>} />
          </Card>
        )}
      </section>

      <NewRepoDialog open={newOpen} onClose={() => setNewOpen(false)} />
    </div>
  );
}
