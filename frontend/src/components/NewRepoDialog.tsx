import { useMutation, useQueryClient } from "@tanstack/react-query";
import { GitBranch } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { api } from "../lib/api";
import { meKey, useSession } from "../lib/auth";
import { reposKey } from "../lib/queries";
import { Button, Dialog, ErrorNotice, Input, Label, Segmented } from "./ui";

const EXAMPLES = ["pallets/flask", "fastapi/fastapi", "psf/requests"];

// Mounted only while the dialog is open, so every open starts with a fresh form
function NewRepoForm({ onClose }: { onClose: () => void }) {
  const { limits } = useSession();
  const [url, setUrl] = useState("");
  const [commits, setCommits] = useState(limits.commit_options.at(-1) ?? 100);
  const qc = useQueryClient();
  const navigate = useNavigate();

  const create = useMutation({
    mutationFn: () => api.createRepo(url.trim(), commits),
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
        <Button type="submit" loading={create.isPending} disabled={!url.trim() || atRepoLimit}>Start ingest</Button>
      </div>
    </form>
  );
}

export function NewRepoDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Dialog open={open} onClose={onClose} title="Ingest a repository"
            description="Paste any public GitHub repository. Its commit history, pull requests and reviews become searchable.">
      <NewRepoForm onClose={onClose} />
    </Dialog>
  );
}
