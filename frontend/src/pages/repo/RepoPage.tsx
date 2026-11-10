import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Eye, Loader2, Lock, RefreshCw, Trash2, TriangleAlert, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { Badge, Button, Card, ConfirmDialog, ErrorNotice, Skeleton } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { meKey, useSession } from "../../lib/auth";
import { authConfigKey, demoReposKey, reposKey } from "../../lib/queries";
import type { Repo } from "../../lib/types";
import { cn, formatNumber, INGEST_STAGES, isIngesting, relativeTime } from "../../lib/utils";
import { RepoStatusBadge } from "../Dashboard";
import { Ask } from "./Ask";
import { BugOrigins } from "./BugOrigins";
import { Authors, CoChange, HotFiles } from "./Insights";
import { Commits } from "./Commits";
import { Overview } from "./Overview";
import { PullRequests } from "./PullRequests";
import { Suspects } from "./Suspects";
import { Timeline } from "./Timeline";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "ask", label: "Ask" },
  { id: "timeline", label: "File timeline" },
  { id: "origins", label: "Bug origins" },
  { id: "suspects", label: "Who broke it?" },
  { id: "hotfiles", label: "Hot files" },
  { id: "cochange", label: "Co-change" },
  { id: "authors", label: "Authors" },
  { id: "pulls", label: "Pull requests" },
  { id: "commits", label: "Commits" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function IngestProgress({ repo }: { repo: Repo }) {
  const current = INGEST_STAGES.findIndex((s) => s.status === repo.status);
  return (
    <Card className="mx-auto mt-8 max-w-xl p-6 sm:p-8">
      <div className="flex items-center gap-3">
        <Loader2 className="size-5 animate-spin text-accent" />
        <div>
          <h2 className="text-sm font-semibold">Ingesting {repo.full_name}</h2>
          <p className="text-[13px] text-muted">{repo.stage_message}…</p>
        </div>
      </div>
      <ol className="mt-7 space-y-0">
        {INGEST_STAGES.map((stage, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li key={stage.status} className="relative flex gap-3 pb-5 last:pb-0">
              {i < INGEST_STAGES.length - 1 && (
                <span className={cn("absolute top-6 left-[11px] h-[calc(100%-1.25rem)] w-px", done ? "bg-accent" : "bg-border")} />
              )}
              <span className={cn("relative grid size-6 shrink-0 place-items-center rounded-full border text-[11px]",
                done && "border-accent bg-accent text-accent-fg",
                active && "border-accent bg-accent-soft text-accent",
                !done && !active && "border-border bg-surface text-subtle")}>
                {done ? <Check className="size-3.5" strokeWidth={3} /> : active ? <span className="size-1.5 animate-pulse rounded-full bg-accent" /> : i + 1}
              </span>
              <span className={cn("pt-0.5 text-[13px]", active ? "font-medium text-text" : done ? "text-muted" : "text-subtle")}>
                {stage.label}
              </span>
            </li>
          );
        })}
      </ol>
      <p className="mt-6 text-xs text-subtle">You can leave this page — ingestion keeps running in the background.</p>
    </Card>
  );
}

function FailedState({ repo, onRetry, retrying }: { repo: Repo; onRetry: () => void; retrying: boolean }) {
  return (
    <Card className="mx-auto mt-8 max-w-xl p-6 sm:p-8">
      <div className="flex gap-3">
        <XCircle className="mt-0.5 size-5 shrink-0 text-danger" />
        <div>
          <h2 className="text-sm font-semibold">Ingestion failed</h2>
          <p className="mt-1 text-[13px] text-muted">{repo.error}</p>
          <Button size="sm" className="mt-5" onClick={onRetry} loading={retrying}><RefreshCw className="size-3.5" /> Try again</Button>
        </div>
      </div>
    </Card>
  );
}

export default function RepoPage() {
  const { repoId = "", tab } = useParams();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { user } = useSession();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmShare, setConfirmShare] = useState(false);

  const repo = useQuery({
    queryKey: ["repo", repoId],
    queryFn: () => api.repo(repoId),
    refetchInterval: (q) => (q.state.data && isIngesting(q.state.data.status) ? 1500 : false),
  });

  // Refresh the sidebar and analytics once an ingest finishes
  const prevStatus = useRef<string | undefined>(undefined);
  useEffect(() => {
    const status = repo.data?.status;
    if (prevStatus.current && prevStatus.current !== status && (status === "ready" || status === "failed")) {
      qc.invalidateQueries({ queryKey: reposKey });
      qc.invalidateQueries({ queryKey: ["repo-data", repoId] });
      if (status === "ready") toast.success(`${repo.data?.full_name} is ready`, { description: "Start asking questions." });
    }
    prevStatus.current = status;
  }, [repo.data?.status, repo.data?.full_name, qc, repoId]);

  const resync = useMutation({
    mutationFn: () => api.resync(repoId),
    onSuccess: (r) => {
      qc.setQueryData(["repo", repoId], r);
      qc.invalidateQueries({ queryKey: reposKey });
      qc.invalidateQueries({ queryKey: meKey });
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteRepo(repoId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: reposKey });
      qc.invalidateQueries({ queryKey: meKey });
      toast.success("Repository deleted");
      navigate("/app");
    },
  });

  // Admins: hand the repository, with its chats, to the public demo
  const share = useMutation({
    mutationFn: () => api.makeDemo(repoId),
    onSuccess: () => {
      for (const key of [reposKey, demoReposKey, authConfigKey, meKey]) qc.invalidateQueries({ queryKey: key });
      toast.success("Shared in the public demo", { description: "Manage it under Settings, Public demo." });
      navigate("/app/settings");
    },
    onError: (e) => { setConfirmShare(false); toast.error(e.message); },
  });

  if (repo.error instanceof ApiError && repo.error.status === 404) return <Navigate to="/app" replace />;
  const activeTab: TabId = TABS.some((t) => t.id === tab) ? (tab as TabId) : "overview";
  const r = repo.data;

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      {repo.error && <ErrorNotice error={repo.error} />}
      {!r ? <Skeleton className="h-24 rounded-xl" /> : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="truncate font-mono text-xl font-semibold tracking-tight">{r.full_name}</h1>
                {r.is_private && <Badge tone="warning"><Lock className="size-3" /> Private</Badge>}
                <RepoStatusBadge repo={r} />
              </div>
              <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-text">
                  github.com/{r.full_name} <ExternalLink className="size-3" />
                </a>
                {r.status === "ready" && <>
                  <span>·</span><span>{formatNumber(r.commit_count)} commits</span>
                  <span>·</span><span>{formatNumber(r.pr_count)} linked PRs</span>
                  {r.expires_at && <><span>·</span><span title="Repositories are removed automatically">expires {relativeTime(r.expires_at)}</span></>}
                </>}
              </p>
            </div>
            {!user.is_demo && <div className="flex flex-wrap gap-2">
              {user.is_admin && !r.is_private && r.status === "ready" && (
                <Button variant="secondary" size="sm" onClick={() => setConfirmShare(true)}
                        title="Let anyone explore this repository from the home page">
                  <Eye className="size-3.5" /> Use as public demo
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={() => resync.mutate()} loading={resync.isPending}
                      disabled={isIngesting(r.status)} title="Re-ingest the latest history">
                <RefreshCw className="size-3.5" /> Re-sync
              </Button>
              <Button variant="ghost" size="sm" className="hover:text-danger" onClick={() => setConfirmDelete(true)}>
                <Trash2 className="size-3.5" /> Delete
              </Button>
            </div>}
          </div>

          {r.warnings.length > 0 && r.status === "ready" && (
            <div className="mt-4 flex gap-2 rounded-lg border border-warning/25 bg-warning-soft px-3.5 py-2.5 text-[13px] text-warning">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <div>{r.warnings.map((w) => <p key={w}>{w}</p>)}</div>
            </div>
          )}

          {isIngesting(r.status) && <IngestProgress repo={r} />}
          {r.status === "failed" && !user.is_demo && <FailedState repo={r} onRetry={() => resync.mutate()} retrying={resync.isPending} />}

          {r.status === "ready" && (
            <>
              <nav className="-mx-4 mt-6 overflow-x-auto border-b border-border px-4 [scrollbar-width:none] sm:mx-0 sm:px-0" aria-label="Repository sections">
                <div className="flex min-w-max gap-1">
                  {TABS.map((t) => (
                    <Link key={t.id} to={`/app/repos/${repoId}/${t.id === "overview" ? "" : t.id}`}
                          aria-current={activeTab === t.id ? "page" : undefined}
                          className={cn("-mb-px border-b-2 px-3 py-2.5 text-[13px] font-medium transition-colors",
                            activeTab === t.id ? "border-accent text-text" : "border-transparent text-muted hover:text-text")}>
                      {t.label}
                    </Link>
                  ))}
                </div>
              </nav>
              <div className="mt-6 animate-fade-up" key={activeTab}>
                {activeTab === "overview" && <Overview repo={r} />}
                {activeTab === "ask" && <Ask repo={r} />}
                {activeTab === "timeline" && <Timeline repo={r} />}
                {activeTab === "origins" && <BugOrigins repo={r} />}
                {activeTab === "suspects" && <Suspects repo={r} />}
                {activeTab === "hotfiles" && <HotFiles repo={r} />}
                {activeTab === "cochange" && <CoChange repo={r} />}
                {activeTab === "authors" && <Authors repo={r} />}
                {activeTab === "pulls" && <PullRequests repo={r} />}
                {activeTab === "commits" && <Commits repo={r} />}
              </div>
            </>
          )}

          <ConfirmDialog open={confirmDelete} onClose={() => setConfirmDelete(false)} onConfirm={() => remove.mutate()}
                         loading={remove.isPending} confirmLabel="Delete repository" title={`Delete ${r.full_name}?`}
                         description="Its indexed history and your question history for it are permanently removed." />
          <ConfirmDialog open={confirmShare} onClose={() => setConfirmShare(false)} onConfirm={() => share.mutate()}
                         loading={share.isPending} confirmLabel="Share in the demo" danger={false}
                         title={`Use ${r.full_name} as the public demo?`}
                         description={<>
                           Anyone will be able to open it from the home page without signing up, including its chats.
                           Visitors can read everything and use Who broke it?, but can't change anything.
                           It moves out of your repositories while it's shared; Stop sharing in Settings brings it back.
                         </>} />
        </>
      )}
    </div>
  );
}
