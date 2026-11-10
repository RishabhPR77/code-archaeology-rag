import { File as FileIcon, Search } from "lucide-react";
import { cn } from "../../lib/utils";
import type { DemoState, Reg } from "./data";
import { PHASES, TRACE_COMMITS, TRACE_FILES } from "./data";
import { Btn, Match, OverviewBody, RepoTitle } from "./frame";

export function ExploreScene({ s, t }: { s: DemoState; t: Reg }) {
  const q = s.pickerOpen ? s.pickerText.toLowerCase() : "";
  return (
    <div className="h-full">
      <RepoTitle active={s.timelineTab ? "File timeline" : "Overview"} t={t} />

      {!s.timelineTab ? <OverviewBody s={s} t={t} /> : (
        <div className="relative mt-3 animate-fade-up">
          <div className="flex gap-2">
            <span ref={t("picker")}
                  className={cn("flex h-9 flex-1 items-center gap-2 rounded-lg border bg-surface px-3 font-mono text-[12px] transition-colors",
                    s.pickerOpen ? "border-accent" : "border-border")}>
              <Search className="size-3.5 shrink-0 text-subtle" />
              {s.pickerText || <span className="font-sans text-subtle">Search files and folders, e.g. main.py</span>}
              {s.pickerOpen && <span className="ml-px h-4 w-px animate-pulse bg-text" />}
            </span>
            <Btn primary>Trace evolution</Btn>
          </div>

          {s.pickerOpen && (
            <div className="absolute inset-x-0 top-11 z-10 rounded-xl border border-border bg-surface py-1 shadow-card animate-fade-up">
              <p className="px-3 pt-1 pb-1.5 text-[10px] font-semibold text-subtle">{q ? "Matching files and folders" : "Most changed files"}</p>
              {TRACE_FILES.filter((f) => f.path.includes(q)).map((f, i) => (
                <span key={f.path} ref={i === 0 ? t("pick-0") : undefined}
                      className={cn("flex items-center gap-2 px-3 py-1.5", i === 0 && q && "bg-accent-soft")}>
                  <FileIcon className="size-3.5 shrink-0 text-subtle" />
                  <span className="flex-1 font-mono text-[11.5px]"><Match text={f.path} q={q} /></span>
                  <span className="text-[10px] text-subtle">{f.changes} changes</span>
                </span>
              ))}
            </div>
          )}

          {s.traced && (
            <div className="mt-3 grid grid-cols-5 gap-3 animate-fade-up">
              <div className="col-span-3 rounded-xl border border-border bg-surface p-3.5">
                <p className="text-[11px] font-medium">Evolution summary <span className="font-mono text-subtle">· {TRACE_FILES[0].path}</span></p>
                <ol className="mt-3 space-y-2.5">
                  {PHASES.map(([year, text, sha]) => (
                    <li key={sha} className="flex gap-2.5 text-[11.5px] leading-snug">
                      <span className="font-semibold">{year}</span>
                      <span className="text-muted">{text} <code className="font-mono text-[10.5px] text-accent">{sha}</code></span>
                    </li>
                  ))}
                </ol>
              </div>
              <div ref={t("trace-commits")} className="col-span-2 rounded-xl border border-border bg-surface p-3.5">
                <p className="text-[11px] font-medium">{TRACE_COMMITS.length} commits</p>
                <ul className="mt-3 space-y-2.5">
                  {TRACE_COMMITS.map(([sha, msg]) => (
                    <li key={sha} className="flex gap-2 text-[11px]">
                      <span className="font-mono font-semibold text-accent">{sha}</span>
                      <span className="truncate text-muted">{msg}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
