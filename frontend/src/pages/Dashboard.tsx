import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, CheckCircle2, Circle, Clock, FolderGit2, GitCommitHorizontal, GitPullRequest, Lock, Plus, Search, Trash2,
} from "lucide-react";
import { useState, type CSSProperties } from "react";
import { Link, Navigate } from "react-router";
import { toast } from "sonner";

import { NewRepoDialog } from "../components/NewRepoDialog";
import { RepoAvatar } from "../components/RepoAvatar";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorNotice, Skeleton, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { meKey, useSession } from "../lib/auth";
import { reposKey, useRepos } from "../lib/queries";
import type { Limits, Repo } from "../lib/types";
import { cn, commitSpan, formatNumber, INGEST_STAGES, isIngesting, relativeTime } from "../lib/utils";

export function RepoStatusBadge({ repo }: { repo: Repo }) {
  if (repo.status === "ready") return <Badge tone="success">Ready</Badge>;
  if (repo.status === "failed") return <Badge tone="danger">Failed</Badge>;
  return <Badge tone="warning"><span className="size-1.5 animate-pulse rounded-full bg-warning" /> Ingesting</Badge>;
}

const stagger = (i: number) => ({ "--i": i }) as CSSProperties;

function IngestBar({ repo }: { repo: Repo }) {
  const step = Math.max(0, INGEST_STAGES.findIndex((s) => s.status === repo.status));
  const share = (step + 1) / INGEST_STAGES.length;
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="truncate text-warning">{repo.stage_message}</span>
        <span className="shrink-0 text-subtle tabular-nums">step {step + 1} of {INGEST_STAGES.length - 1}</span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div className="progress-sweep h-full rounded-full bg-warning transition-[width] duration-700" style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

function RepoCard({ repo, index, onDelete }: { repo: Repo; index: number; onDelete: () => void }) {
  const [owner, name] = repo.full_name.split("/");
  return (
    <div className="card-in group relative" style={stagger(index)}>
    <Link to={`/app/repos/${repo.id}`} className="block h-full rounded-xl">
      <Card className="card-lift flex h-full flex-col p-5">
        <div className="flex items-start gap-3">
          <RepoAvatar fullName={repo.full_name}
                      className="size-11 rounded-xl transition-transform duration-300 group-hover:scale-105" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs text-subtle">{owner}</p>
            <h3 className="flex items-center gap-1.5 text-[15px] font-semibold">
              <span className="truncate">{name}</span>
              {repo.is_private && <Lock className="size-3.5 shrink-0 text-warning" aria-label="Private repository" />}
            </h3>
          </div>
          <RepoStatusBadge repo={repo} />
        </div>

        {isIngesting(repo.status) ? <IngestBar repo={repo} /> : repo.status === "failed" ? (
          <p className="mt-4 line-clamp-2 text-xs text-danger">{repo.error || "Ingestion failed. Open it to try again."}</p>
        ) : (
          <p className="mt-4 text-xs text-muted">Ingested {relativeTime(repo.ready_at)}</p>
        )}

        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3.5 text-xs text-subtle">
          <span className="inline-flex items-center gap-1"><GitCommitHorizontal className="size-3.5" />{commitSpan(repo)}</span>
          <span className="inline-flex items-center gap-1"><GitPullRequest className="size-3.5" />{formatNumber(repo.pr_count)} PRs</span>
          {repo.expires_at && (
            <span className="inline-flex items-center gap-1" title="Repositories are removed automatically">
              <Clock className="size-3.5" />expires {relativeTime(repo.expires_at)}
            </span>
          )}
          <ArrowRight className="ml-auto mr-9 size-4 -translate-x-1 text-accent opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100" />
        </div>
      </Card>
    </Link>
    {/* Outside the link, so deleting doesn't also open the repository */}
    <button onClick={onDelete} aria-label={`Delete ${repo.full_name}`} title="Delete repository"
            className="absolute right-3 bottom-2.5 rounded-md p-1.5 text-subtle opacity-0 transition-opacity hover:bg-danger-soft hover:text-danger group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100 cursor-pointer">
      <Trash2 className="size-4" />
    </button>
    </div>
  );
}

function AddCard({ index, onClick }: { index: number; onClick: () => void }) {
  return (
    <button onClick={onClick} style={stagger(index)}
            className="card-in group flex min-h-48 flex-col items-center justify-center rounded-xl border-2 border-dashed border-border-strong p-5 text-center transition-colors hover:border-accent hover:bg-accent-soft cursor-pointer">
      <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent transition-transform duration-300 group-hover:scale-110 group-hover:rotate-90">
        <Plus className="size-5" />
      </span>
      <span className="mt-3 text-sm font-semibold">Add a repository</span>
      <span className="mt-0.5 text-xs text-subtle">Paste a GitHub URL or pick one of yours</span>
    </button>
  );
}

function Usage({ limits }: { limits: Limits }) {
  const tiles = [
    { label: "Repositories", used: limits.repos_used, max: limits.max_repos },
    { label: "Ingests in the last 24 hours", used: limits.ingests_today, max: limits.max_ingests_day },
  ];
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-3">
      {tiles.map((t, i) => {
        const full = t.used >= t.max;
        return (
          <div key={t.label} className="card-in rounded-xl border border-border bg-surface px-4 py-3" style={stagger(i)}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs text-muted">{t.label}</span>
              <span className={cn("text-sm font-semibold tabular-nums", full && "text-warning")}>{t.used} / {t.max}</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div className={cn("h-full rounded-full transition-[width] duration-700", full ? "bg-warning" : "bg-accent")}
                   style={{ width: `${Math.min(100, (t.used / Math.max(t.max, 1)) * 100)}%` }} />
            </div>
          </div>
        );
      })}
      <div className="card-in flex items-center rounded-xl border border-border bg-surface px-4 py-3 text-xs text-muted" style={stagger(2)}>
        Up to {formatNumber(limits.max_commits)} commits each. Repositories are removed after {limits.repo_ttl_hours} hours.
      </div>
    </div>
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
    <Card className="card-in p-6">
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

// The demo opens straight into its sample repository
function DemoStart() {
  const repos = useRepos();
  if (repos.data?.length) return <Navigate to={`/app/repos/${repos.data[0].id}`} replace />;
  if (repos.isPending) return <div className="grid h-full place-items-center"><Spinner className="size-5" /></div>;
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
      {repos.error ? <ErrorNotice error={repos.error} /> : (
        <Card>
          <EmptyState icon={<FolderGit2 className="size-5" />} title="The demo isn't available right now"
                      description="Sign up free to connect a repository of your own."
                      action={<Link to="/register"><Button>Sign up free <ArrowRight className="size-4" /></Button></Link>} />
        </Card>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useSession();
  return user.is_demo ? <DemoStart /> : <Workspace />;
}

function Workspace() {
  const { user, limits } = useSession();
  const repos = useRepos();
  const [newOpen, setNewOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [toDelete, setToDelete] = useState<Repo | null>(null);
  const qc = useQueryClient();
  const remove = useMutation({
    mutationFn: (repo: Repo) => api.deleteRepo(repo.id),
    onSuccess: (_, repo) => {
      qc.invalidateQueries({ queryKey: reposKey });
      qc.invalidateQueries({ queryKey: meKey });
      setToDelete(null);
      toast.success(`${repo.full_name} deleted`);
    },
    onError: (e) => toast.error(e.message),
  });
  const hasModel = !!(user.active_provider && user.active_model);
  const all = repos.data ?? [];
  const hasRepo = all.length > 0;
  const q = filter.trim().toLowerCase();
  const shown = all.filter((r) => !q || r.full_name.toLowerCase().includes(q));
  const firstName = (user.name || user.email.split("@")[0]).split(" ")[0];
  const canAdd = limits.unlimited || limits.repos_used < limits.max_repos;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">Welcome back, {firstName}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">
            Your repositories {hasRepo && <span className="font-normal text-subtle">· {all.length}</span>}
          </h1>
        </div>
        {all.length > 3 && (
          <label className="flex h-9 w-full items-center gap-2 rounded-lg border border-border bg-surface px-3 focus-within:border-accent sm:w-64">
            <Search className="size-4 shrink-0 text-subtle" />
            <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter repositories"
                   aria-label="Filter repositories" className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-subtle" />
          </label>
        )}
      </div>

      {!limits.unlimited && <Usage limits={limits} />}

      {(!hasModel || !hasRepo) && !repos.isPending && (
        <div className="mt-6"><SetupChecklist hasModel={hasModel} hasRepo={hasRepo} onNewRepo={() => setNewOpen(true)} /></div>
      )}

      <section className="mt-8">
        {repos.error && <ErrorNotice error={repos.error} />}
        {repos.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[0, 1, 2].map((i) => <Skeleton key={i} className="h-48 rounded-xl" />)}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {shown.map((r, i) => <RepoCard key={r.id} repo={r} index={i} onDelete={() => setToDelete(r)} />)}
            {!q && canAdd && <AddCard index={shown.length} onClick={() => setNewOpen(true)} />}
            {q && shown.length === 0 && <p className="text-sm text-subtle">No repository matches “{filter}”.</p>}
          </div>
        )}
      </section>

      <NewRepoDialog open={newOpen} onClose={() => setNewOpen(false)} />
      <ConfirmDialog open={toDelete !== null} onClose={() => setToDelete(null)}
                     onConfirm={() => toDelete && remove.mutate(toDelete)} loading={remove.isPending}
                     confirmLabel="Delete repository" title={`Delete ${toDelete?.full_name ?? "this repository"}?`}
                     description="It's removed along with all its chats, and you can add another repository in its place. This can't be undone." />
    </div>
  );
}
