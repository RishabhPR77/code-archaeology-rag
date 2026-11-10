import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight, CalendarDays, Check, FolderGit2, GitCommitHorizontal, GitPullRequest, MessageSquareText, MessagesSquare,
  Pencil, ShieldCheck, X,
} from "lucide-react";
import { useState, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { Link, Navigate } from "react-router";
import { toast } from "sonner";

import { GitHubIcon, GoogleIcon, ProviderMark } from "../components/brand";
import { CountUp } from "../components/CountUp";
import { RepoAvatar } from "../components/RepoAvatar";
import { Badge, Button, Card, CardHeader, ErrorNotice, Input, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { meKey, useSession } from "../lib/auth";
import { cn, formatDate, PROVIDER_NAMES, relativeTime } from "../lib/utils";

const stagger = (i: number) => ({ "--i": i }) as CSSProperties;

export default function Profile() {
  const { user } = useSession();
  // The shared demo account has no profile of its own
  return user.is_demo ? <Navigate to="/app" replace /> : <ProfilePage />;
}

function Stat({ icon, label, value, note, index }: { icon: ReactNode; label: string; value: number; note?: string; index: number }) {
  return (
    <Card className="card-in p-4" style={stagger(index)}>
      <div className="flex items-center gap-2 text-xs text-muted">
        <span className="grid size-7 place-items-center rounded-lg bg-accent-soft text-accent">{icon}</span>
        {label}
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums"><CountUp value={value} /></p>
      {note && <p className="mt-0.5 text-xs text-subtle">{note}</p>}
    </Card>
  );
}

function NameEditor() {
  const { user } = useSession();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user.name);
  const rename = useMutation({
    mutationFn: () => api.rename(name),
    onSuccess: (me) => {
      qc.setQueryData(meKey, me);
      setEditing(false);
      toast.success("Name updated");
    },
    onError: (e) => toast.error(e.message),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (name.trim()) rename.mutate();
  };

  if (!editing) {
    return (
      <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
        <span className="truncate">{user.name || user.email.split("@")[0]}</span>
        <button onClick={() => { setName(user.name); setEditing(true); }} aria-label="Edit your name" title="Edit your name"
                className="rounded-md p-1 text-subtle hover:bg-surface-2 hover:text-text cursor-pointer">
          <Pencil className="size-4" />
        </button>
      </h1>
    );
  }
  return (
    <form onSubmit={submit} className="flex max-w-sm items-center gap-2">
      <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} autoFocus aria-label="Your name" />
      <Button type="submit" size="icon" loading={rename.isPending} disabled={!name.trim()} aria-label="Save name">
        {!rename.isPending && <Check className="size-4" />}
      </Button>
      <Button type="button" size="icon" variant="ghost" onClick={() => setEditing(false)} aria-label="Cancel">
        <X className="size-4" />
      </Button>
    </form>
  );
}

function ProfilePage() {
  const { user, limits } = useSession();
  const profile = useQuery({ queryKey: ["profile"], queryFn: api.profile });
  const p = profile.data;

  const signIns = [
    user.has_password && <Badge key="pw">Email &amp; password</Badge>,
    user.google_linked && <Badge key="g"><GoogleIcon className="size-3" /> Google</Badge>,
    user.github_login && <Badge key="gh"><GitHubIcon className="size-3" /> {user.github_login}</Badge>,
  ].filter(Boolean);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10">
      <Card className="card-in overflow-hidden">
        <div className="h-24 bg-gradient-to-r from-accent-soft via-accent-soft/40 to-transparent" />
        <div className="flex flex-col gap-4 px-6 pb-6 sm:flex-row sm:items-end">
          <div className="-mt-12 shrink-0">
            {user.avatar_url ? (
              <img src={user.avatar_url} alt="" className="size-24 rounded-2xl border-4 border-surface object-cover shadow-card" />
            ) : (
              <span className="grid size-24 place-items-center rounded-2xl border-4 border-surface bg-accent text-3xl font-semibold text-accent-fg shadow-card">
                {(user.name || user.email)[0].toUpperCase()}
              </span>
            )}
          </div>
          <div className="min-w-0 flex-1">
            <NameEditor />
            <p className="mt-0.5 truncate text-sm text-muted">{user.email}</p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge><CalendarDays className="size-3" /> Member since {formatDate(user.created_at)}</Badge>
              {signIns}
              {user.is_admin && <Badge tone="success"><ShieldCheck className="size-3" /> Admin</Badge>}
            </div>
          </div>
          <Link to="/app/settings" className="shrink-0"><Button variant="secondary" size="sm">Account settings</Button></Link>
        </div>
      </Card>

      {profile.error && <ErrorNotice error={profile.error} className="mt-6" />}
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-5">
        {!p ? [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />) : (
          <>
            <Stat index={0} icon={<FolderGit2 className="size-3.5" />} label="Repositories" value={p.repos}
                  note={p.ready_repos === p.repos ? "all ready" : `${p.ready_repos} ready`} />
            <Stat index={1} icon={<GitCommitHorizontal className="size-3.5" />} label="Commits indexed" value={p.commits_indexed} />
            <Stat index={2} icon={<GitPullRequest className="size-3.5" />} label="Pull requests linked" value={p.prs_linked} />
            <Stat index={3} icon={<MessageSquareText className="size-3.5" />} label="Questions asked" value={p.questions} />
            <Stat index={4} icon={<MessagesSquare className="size-3.5" />} label="Chats" value={p.chats} />
          </>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-5">
        <Card className="card-in lg:col-span-3" style={stagger(2)}>
          <CardHeader title="Your latest questions" description="Pick up a chat where you left it." />
          {!p ? <div className="p-5"><Skeleton className="h-24 rounded-lg" /></div> : p.recent.length === 0 ? (
            <div className="px-5 py-8 text-center text-sm text-muted">
              No questions yet. Open a repository and ask why something changed.
            </div>
          ) : (
            <ul className="divide-y divide-border">
              {p.recent.map((q, i) => (
                <li key={`${q.repo_id}-${i}`}>
                  <Link to={`/app/repos/${q.repo_id}/ask${q.chat_id ? `?chat=${q.chat_id}` : ""}`}
                        className="group flex items-center gap-3 px-5 py-3 transition-colors hover:bg-surface-2">
                    <RepoAvatar fullName={q.repo || "?"} className="size-8" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium">{q.question}</span>
                      <span className="block truncate text-xs text-subtle">{q.repo} · {relativeTime(q.created_at)}</span>
                    </span>
                    <ArrowRight className="size-4 shrink-0 -translate-x-1 text-accent opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card className="card-in p-5" style={stagger(3)}>
            <p className="text-xs font-medium text-muted">Model</p>
            {user.active_provider && user.active_model ? (
              <div className="mt-3 flex items-center gap-3">
                <ProviderMark id={user.active_provider} className="size-9" />
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{PROVIDER_NAMES[user.active_provider]}</p>
                  <p className="truncate font-mono text-xs text-muted">{user.active_model}</p>
                </div>
              </div>
            ) : (
              <p className="mt-2 text-sm text-muted">No model connected yet.</p>
            )}
            <Link to="/app/settings" className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline">
              {user.active_provider ? "Change model" : "Connect a model"} <ArrowRight className="size-3" />
            </Link>
          </Card>

          <Card className="card-in p-5" style={stagger(4)}>
            <p className="text-xs font-medium text-muted">Your plan</p>
            {limits.unlimited ? (
              <p className="mt-2 text-sm">No limits on this account.</p>
            ) : (
              <div className="mt-3 space-y-3">
                {[["Repositories", limits.repos_used, limits.max_repos], ["Ingests in the last 24 hours", limits.ingests_today, limits.max_ingests_day]].map(([label, used, max]) => (
                  <div key={label as string}>
                    <div className="flex justify-between text-xs">
                      <span className="text-muted">{label}</span>
                      <span className="font-medium tabular-nums">{used} / {max}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
                      <div className={cn("h-full rounded-full bg-accent transition-[width] duration-700", (used as number) >= (max as number) && "bg-warning")}
                           style={{ width: `${Math.min(100, ((used as number) / Math.max(max as number, 1)) * 100)}%` }} />
                    </div>
                  </div>
                ))}
                <p className="text-xs text-subtle">
                  Up to {limits.max_commits} commits per repository; repositories are removed after {limits.repo_ttl_hours} hours.
                </p>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
