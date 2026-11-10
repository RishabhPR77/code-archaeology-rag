import { GitCommitHorizontal, Globe, Lock, Plus, Search } from "lucide-react";
import { cn } from "../../lib/utils";
import { GitHubIcon } from "../brand";
import type { DemoState, Reg } from "./data";
import { REPOS, STAGES } from "./data";
import { Btn, SetupChecklist } from "./frame";

export function IngestScene({ s, t }: { s: DemoState; t: Reg }) {
  const done = s.stage === STAGES.length - 1;
  return (
    <div className="h-full">
      <p className="text-[12px] text-muted">Welcome back, Jo</p>
      <p className="text-[17px] font-semibold">Your repositories</p>
      {!s.ingesting && <div className="mt-3"><SetupChecklist connected /></div>}

      <div className="mt-3 grid grid-cols-3 gap-3">
        {s.ingesting && (
          <div ref={t("repo-card")} className="rounded-xl border border-border bg-surface p-3.5 shadow-card animate-fade-up">
            <div className="flex items-start gap-2.5">
              <span className="grid size-9 place-items-center rounded-lg bg-accent text-[13px] font-bold text-accent-fg">A</span>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] text-subtle">acme</p>
                <p className="flex items-center gap-1 text-[13px] font-semibold">storefront <Lock className="size-3 text-warning" /></p>
              </div>
              <span className={cn("rounded-md px-1.5 py-0.5 text-[10px]", done ? "bg-success-soft text-success" : "bg-warning-soft text-warning")}>
                {done ? "Ready" : "Ingesting"}
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between text-[10px]">
              <span className={done ? "text-muted" : "text-warning"}>{done ? "Ingested just now" : STAGES[s.stage]}</span>
              {!done && <span className="text-subtle">step {s.stage + 1} of {STAGES.length - 1}</span>}
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div className={cn("h-full rounded-full transition-[width] duration-500", done ? "bg-success" : "progress-sweep bg-warning")}
                   style={{ width: `${((s.stage + 1) / STAGES.length) * 100}%` }} />
            </div>
            <p className="mt-3 border-t border-border pt-2 text-[10px] text-subtle">{done ? "commits 1–300 · 86 PRs" : "Reading history…"}</p>
          </div>
        )}
        <div className="flex h-40 flex-col items-center justify-center rounded-xl border-2 border-dashed border-border-strong text-center">
          <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent"><Plus className="size-4" /></span>
          <p className="mt-2 text-[12px] font-semibold">Add a repository</p>
          <p className="text-[10px] text-subtle">Paste a GitHub URL or pick one of yours</p>
        </div>
      </div>
    </div>
  );
}

/** The real "Ingest a repository" dialog, over the whole page. */
export function IngestDialog({ s, t }: { s: DemoState; t: Reg }) {
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-black/40 backdrop-blur-[2px]">
      <div className="w-[460px] rounded-2xl border border-border bg-surface px-5 py-4 shadow-2xl animate-fade-up">
        <p className="text-[14px] font-semibold">Ingest a repository</p>
        <p className="text-[11px] text-muted">Its commit history, pull requests and reviews become searchable.</p>
        <div className="mt-2.5 grid grid-cols-2 rounded-lg border border-border bg-surface-2 p-0.5 text-[12px]">
          <span className="flex items-center justify-center gap-1.5 rounded-md bg-surface-3 py-1 font-medium"><GitHubIcon className="size-3" /> Your GitHub</span>
          <span className="flex items-center justify-center gap-1.5 py-1 text-muted"><Globe className="size-3" /> Public URL</span>
        </div>
        <span className="mt-2 flex h-7 items-center gap-2 rounded-lg border border-border px-2.5 text-[11px] text-subtle">
          <Search className="size-3.5" /> Search your repositories
        </span>
        <div className="mt-2 overflow-hidden rounded-lg border border-border">
          {REPOS.map((r, i) => (
            <span key={r.name} ref={t(`repo-${i}`)}
                  className={cn("flex items-center gap-2.5 border-b border-border px-3 py-1 last:border-b-0",
                    s.picked === r.name && "bg-accent-soft")}>
              {r.private ? <Lock className="size-3 text-warning" /> : <Globe className="size-3 text-subtle" />}
              <span className="font-mono text-[11.5px]">{r.name}</span>
              <span className="ml-auto text-[10px] text-subtle">{r.note}</span>
            </span>
          ))}
        </div>

        <div className="mt-2.5 flex items-center justify-between">
          <span className="text-[12px] font-medium">Commits to analyse</span>
          <span className="text-[10px] text-subtle">On the default branch</span>
        </div>
        <div className="mt-1.5 inline-flex rounded-lg border border-border bg-surface-2 p-0.5 text-[11px]">
          <span className={cn("rounded-md px-2.5 py-0.5", !s.range && "bg-surface-3 font-medium")}>The latest</span>
          <span ref={t("which-range")} className={cn("rounded-md px-2.5 py-0.5", s.range && "bg-surface-3 font-medium")}>A range</span>
        </div>
        {!s.range ? (
          <div className="mt-2 flex gap-1.5 text-[11px]">
            {[50, 100, 200, 300, 500].map((n) => (
              <span key={n} className={cn("rounded-md border px-2.5 py-0.5", n === 300 ? "border-accent bg-accent-soft font-medium" : "border-border")}>{n}</span>
            ))}
          </div>
        ) : (
          <div className="mt-2 space-y-1.5 rounded-xl border border-border bg-surface-2/50 px-3 py-2 animate-fade-up">
            <div className="relative h-4">
              <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-surface-3" />
              <div className="absolute top-1/2 left-[2%] h-1.5 w-[22%] -translate-y-1/2 rounded-full bg-accent" />
              <span className="absolute top-1/2 left-[2%] size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-surface" />
              <span className="absolute top-1/2 left-[24%] size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-surface" />
            </div>
            <div className="flex items-center justify-between text-[10px] text-subtle"><span>#1 newest</span><span>#1,342 oldest</span></div>
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className="text-muted">Commits</span>
              <span className="rounded-md border border-border bg-surface px-2 font-mono">1</span>
              <span className="text-muted">to</span>
              <span className="rounded-md border border-border bg-surface px-2 font-mono">300</span>
              <span className="ml-auto rounded-md bg-accent-soft px-1.5 text-[10px] font-medium text-accent">300 commits</span>
            </div>
            <div className="space-y-0.5 border-t border-border pt-1.5 text-[10px]">
              <p className="flex items-center gap-1.5 truncate"><GitCommitHorizontal className="size-3 text-accent" /><span className="text-subtle">Starts at</span>
                <span className="font-mono text-accent">#1</span> · 4 Nov 2026 · Add idempotent retry</p>
              <p className="flex items-center gap-1.5 truncate"><GitCommitHorizontal className="size-3 text-accent" /><span className="text-subtle">Ends at</span>
                <span className="font-mono text-accent">#300</span> · 12 Mar 2025 · Split checkout into steps</p>
            </div>
          </div>
        )}
        <div className="mt-3 flex justify-end gap-2">
          <Btn>Cancel</Btn>
          <Btn primary r={t("start")} className={cn(!s.picked && "opacity-50")}>Start ingest</Btn>
        </div>
      </div>
    </div>
  );
}
