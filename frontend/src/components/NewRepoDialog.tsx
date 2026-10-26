import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, GitBranch, Globe, Lock, Search, Settings2 } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router";

import { api } from "../lib/api";
import { meKey, useSession } from "../lib/auth";
import { reposKey, useAuthConfig, useGitHubStatus } from "../lib/queries";
import { cn, relativeTime } from "../lib/utils";
import { GitHubIcon } from "./brand";
import { Button, Dialog, ErrorNotice, Input, Label, Segmented, Skeleton } from "./ui";

const EXAMPLES = ["pallets/flask", "fastapi/fastapi", "psf/requests"];

function GitHubPicker({ selected, onSelect }: { selected: string; onSelect: (fullName: string) => void }) {
  const status = useGitHubStatus();
  const connected = status.data?.connected && status.data.installations.length > 0;
  const repos = useQuery({ queryKey: ["github-repos"], queryFn: api.githubRepos, enabled: !!connected });
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return (repos.data ?? []).filter((r) => !needle || r.full_name.toLowerCase().includes(needle));
  }, [repos.data, q]);

  if (status.isPending) return <Skeleton className="h-40 rounded-lg" />;
  const s = status.data;
  if (!s) return <ErrorNotice error={status.error} />;

  if (!s.connected) {
    return (
      <div className="rounded-lg border border-dashed border-border-strong p-5 text-center">
        <GitHubIcon className="mx-auto size-6" />
        <p className="mt-3 text-sm font-medium">Connect your GitHub account</p>
        <p className="mt-1 text-[13px] text-muted">{s.error ?? "Pick from your own repositories, including private ones."}</p>
        <a href="/api/auth/github/login" className="mt-4 inline-block">
          <Button type="button" size="sm"><GitHubIcon /> Connect GitHub</Button>
        </a>
      </div>
    );
  }
  if (s.installations.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border-strong p-5 text-center">
        <Lock className="mx-auto size-5 text-muted" />
        <p className="mt-3 text-sm font-medium">Choose which repositories to share</p>
        <p className="mt-1 text-[13px] text-muted">
          GitHub asks you to pick repositories. Access is read-only and you can change it any time.
        </p>
        {s.install_url && (
          <a href={s.install_url} className="mt-4 inline-block">
            <Button type="button" size="sm">Choose repositories on GitHub <ExternalLink className="size-3.5" /></Button>
          </a>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="relative">
        <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search your repositories"
               className="pl-9 text-[13px]" aria-label="Search your repositories" data-autofocus />
      </div>
      <div role="listbox" aria-label="Your repositories" className="mt-2 max-h-60 overflow-y-auto rounded-lg border border-border">
        {repos.isPending && <div className="space-y-2 p-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-10" />)}</div>}
        {repos.error && <ErrorNotice error={repos.error} className="m-3" />}
        {repos.data && filtered.length === 0 && (
          <p className="px-3 py-6 text-center text-[13px] text-subtle">No shared repositories match.</p>
        )}
        {filtered.map((r) => (
          <button key={r.full_name} type="button" role="option" aria-selected={selected === r.full_name}
                  onClick={() => onSelect(r.full_name)}
                  className={cn("flex w-full items-center gap-3 border-b border-border px-3 py-2.5 text-left last:border-b-0 cursor-pointer",
                    selected === r.full_name ? "bg-accent-soft" : "hover:bg-surface-2")}>
            {r.private ? <Lock className="size-3.5 shrink-0 text-warning" /> : <Globe className="size-3.5 shrink-0 text-subtle" />}
            <span className="min-w-0 flex-1">
              <span className="block truncate font-mono text-[13px]">{r.full_name}</span>
              {r.description && <span className="block truncate text-xs text-subtle">{r.description}</span>}
            </span>
            {r.updated_at && <span className="shrink-0 text-[11px] text-subtle">{relativeTime(r.updated_at)}</span>}
          </button>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-subtle">
        <span>Signed in to GitHub as <span className="font-medium text-muted">@{s.login}</span></span>
        {s.install_url && (
          <a href={s.install_url} className="inline-flex items-center gap-1 text-accent hover:underline">
            <Settings2 className="size-3" /> Change shared repositories
          </a>
        )}
      </div>
    </div>
  );
}

// Mounted only while the dialog is open, so every open starts with a fresh form
function NewRepoForm({ onClose }: { onClose: () => void }) {
  const { user, limits } = useSession();
  const config = useAuthConfig();
  const githubEnabled = !!config.data?.github_enabled;
  const [source, setSource] = useState<"github" | "url">(user.github_connected ? "github" : "url");
  const [url, setUrl] = useState("");
  const [picked, setPicked] = useState("");
  const [commits, setCommits] = useState(limits.commit_options.at(-1) ?? 100);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const target = source === "github" && githubEnabled ? (picked ? `https://github.com/${picked}` : "") : url.trim();
  const create = useMutation({
    mutationFn: () => api.createRepo(target, commits),
    onSuccess: (repo) => {
      qc.invalidateQueries({ queryKey: reposKey });
      qc.invalidateQueries({ queryKey: meKey });
      onClose();
      navigate(`/app/repos/${repo.id}`);
    },
  });

  const atRepoLimit = !limits.unlimited && limits.repos_used >= limits.max_repos;

  return (
    <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-5">
      {githubEnabled && (
        <Segmented value={source} onChange={setSource} className="w-full [&>button]:flex-1"
                   options={[{ value: "github", label: <span className="inline-flex items-center gap-1.5"><GitHubIcon className="size-3.5" /> Your GitHub</span> },
                             { value: "url", label: <span className="inline-flex items-center gap-1.5"><Globe className="size-3.5" /> Public URL</span> }]} />
      )}

      {source === "github" && githubEnabled ? (
        <GitHubPicker selected={picked} onSelect={setPicked} />
      ) : (
        <div>
          <Label htmlFor="repo-url">Repository URL</Label>
          <div className="relative">
            <GitBranch className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
            <Input id="repo-url" data-autofocus required value={url} onChange={(e) => setUrl(e.target.value)}
                   placeholder="https://github.com/owner/repo" className="pl-9 font-mono text-[13px]" />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-subtle">Try</span>
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => setUrl(`https://github.com/${ex}`)}
                      className="rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[11px] text-muted hover:text-text cursor-pointer">
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <Label hint="Most recent commits on the default branch">Commits to analyse</Label>
        <Segmented value={commits} onChange={setCommits}
                   options={limits.commit_options.map((c) => ({ value: c, label: c }))} />
      </div>

      {!limits.unlimited && (
        <p className="text-xs text-subtle">
          {limits.repos_used}/{limits.max_repos} repositories · {limits.ingests_today}/{limits.max_ingests_day} ingests in the last 24h
          {limits.repo_ttl_hours > 0 && ` · kept for ${limits.repo_ttl_hours}h`}
        </p>
      )}

      {atRepoLimit && <ErrorNotice error={new Error(`You can keep up to ${limits.max_repos} repositories. Delete one to add another.`)} />}
      {create.error && <ErrorNotice error={create.error} />}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
        <Button type="submit" loading={create.isPending} disabled={!target || atRepoLimit}>Start ingest</Button>
      </div>
    </form>
  );
}

export function NewRepoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Ingest a repository"
            description="Its commit history, pull requests and reviews become searchable.">
      <NewRepoForm onClose={onClose} />
    </Dialog>
  );
}
