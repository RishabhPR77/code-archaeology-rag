import { useQuery } from "@tanstack/react-query";
import { GitCommitHorizontal } from "lucide-react";
import { useEffect, useState, type CSSProperties } from "react";

import { api } from "../lib/api";
import type { CommitBrief } from "../lib/types";
import { cn, formatDate, formatNumber } from "../lib/utils";
import { ErrorNotice, Skeleton } from "./ui";

export const MIN_RANGE = 10;

/** A value that only settles once it has stopped changing for `ms`, so dragging doesn't flood GitHub. */
function useSettled<T>(value: T, ms = 350): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setSettled(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return settled;
}

// Two range inputs share one track; only their thumbs take the pointer, so both can be dragged
const THUMB = "pointer-events-none absolute inset-0 h-6 w-full appearance-none bg-transparent " +
  "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:size-5 [&::-webkit-slider-thumb]:appearance-none " +
  "[&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-accent " +
  "[&::-webkit-slider-thumb]:bg-surface [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-grab " +
  "[&::-webkit-slider-thumb]:transition-transform [&::-webkit-slider-thumb]:hover:scale-110 " +
  "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:size-5 [&::-moz-range-thumb]:rounded-full " +
  "[&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-accent [&::-moz-range-thumb]:bg-surface " +
  "focus-visible:outline-none [&:focus-visible::-webkit-slider-thumb]:ring-4 [&:focus-visible::-webkit-slider-thumb]:ring-accent/30";

function Slider({ max, from, to, onChange }: { max: number; from: number; to: number; onChange: (from: number, to: number) => void }) {
  const pct = (n: number) => ((n - 1) / Math.max(max - 1, 1)) * 100;
  return (
    <div className="relative h-6">
      <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-surface-3" />
      <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-accent transition-[left,width] duration-75"
           style={{ left: `${pct(from)}%`, width: `${pct(to) - pct(from)}%` } as CSSProperties} />
      <input type="range" min={1} max={max} value={from} aria-label="First commit in the range"
             onChange={(e) => onChange(Number(e.target.value), to)} className={THUMB} />
      <input type="range" min={1} max={max} value={to} aria-label="Last commit in the range"
             onChange={(e) => onChange(from, Number(e.target.value))} className={THUMB} />
    </div>
  );
}

function CommitRow({ label, commit }: { label: string; commit: CommitBrief | null | undefined }) {
  return (
    <div className="flex items-center gap-2.5 text-xs">
      <GitCommitHorizontal className="size-3.5 shrink-0 text-accent" />
      <span className="w-14 shrink-0 text-subtle">{label}</span>
      {commit ? (
        <span className="min-w-0 flex-1 truncate">
          <span className="font-mono text-accent">#{formatNumber(commit.number)}</span>
          <span className="text-subtle"> · {commit.date ? formatDate(commit.date) : "—"} · </span>
          <span className="font-mono text-muted">{commit.sha}</span>
          <span className="text-text"> {commit.message}</span>
        </span>
      ) : <Skeleton className="h-3.5 flex-1" />}
    </div>
  );
}

/**
 * Pick which commits to ingest, counted back from the newest (commit 1). The range can be dragged on a
 * slider over the whole history or typed in, and the commits at each end are previewed from GitHub.
 */
export function CommitRange({ url, maxSpan, from, to, onChange }: {
  url: string; maxSpan: number; from: number; to: number; onChange: (from: number, to: number) => void;
}) {
  const settled = useSettled({ url, from, to });
  const preview = useQuery({
    queryKey: ["range-preview", settled.url, settled.from, settled.to],
    queryFn: () => api.rangePreview(settled.url, settled.from - 1, settled.to - settled.from + 1),
    enabled: !!settled.url,
    staleTime: 5 * 60_000,
    placeholderData: (previous) => previous,   // keep showing the last preview while the next one loads
    retry: false,
  });
  const total = preview.data?.total;
  const reach = preview.data?.reach ?? 5000;
  const max = Math.max(MIN_RANGE, Math.min(total ?? reach, reach));

  // Keep the range valid: inside the history, at least MIN_RANGE long and at most maxSpan
  const set = (f: number, t: number, moved: "from" | "to") => {
    f = Math.max(1, Math.min(f, max));
    t = Math.max(1, Math.min(t, max));
    if (moved === "from") {
      if (t - f + 1 < MIN_RANGE) t = Math.min(max, f + MIN_RANGE - 1);
      if (t - f + 1 > maxSpan) t = f + maxSpan - 1;
      if (t - f + 1 < MIN_RANGE) f = Math.max(1, t - MIN_RANGE + 1);
    } else {
      if (t - f + 1 < MIN_RANGE) f = Math.max(1, t - MIN_RANGE + 1);
      if (t - f + 1 > maxSpan) f = t - maxSpan + 1;
      if (t - f + 1 < MIN_RANGE) t = Math.min(max, f + MIN_RANGE - 1);
    }
    onChange(f, t);
  };
  // When the real history turns out shorter, pull the range back inside it
  useEffect(() => {
    if (total !== undefined && total >= MIN_RANGE && to > total) set(from, to, "to");
  }, [total]);   // eslint-disable-line react-hooks/exhaustive-deps

  const count = to - from + 1;
  const noHistory = total !== undefined && total < MIN_RANGE;
  const numberInput = "h-9 w-24 rounded-lg border border-border bg-surface px-2.5 text-center font-mono text-[13px] tabular-nums outline-none focus:border-accent focus:ring-3 focus:ring-accent-soft";

  return (
    <div className="space-y-4 rounded-xl border border-border bg-surface-2/50 p-4 animate-fade-up">
      {!url ? (
        <p className="text-xs text-muted">Choose a repository first, and its history appears here.</p>
      ) : noHistory ? (
        <p className="text-xs text-muted">This repository has only {total} commits, so take its latest commits instead.</p>
      ) : (
        <>
          <div>
            <Slider max={max} from={from} to={to}
                    onChange={(f, t) => set(f, t, f !== from ? "from" : "to")} />
            <div className="mt-1.5 flex justify-between text-[11px] text-subtle">
              <span>#1 newest</span>
              <span>
                {total === undefined ? "Loading history…" : total > reach
                  ? `#${formatNumber(reach)} (of ${formatNumber(total)}; ranges reach back ${formatNumber(reach)})`
                  : `#${formatNumber(total)} oldest`}
              </span>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-[13px]">
            <span className="text-muted">Commits</span>
            <input type="number" min={1} max={max} value={from} aria-label="From commit number"
                   onChange={(e) => onChange(Number(e.target.value) || 1, to)} onBlur={() => set(from, to, "from")}
                   className={numberInput} />
            <span className="text-muted">to</span>
            <input type="number" min={1} max={max} value={to} aria-label="To commit number"
                   onChange={(e) => onChange(from, Number(e.target.value) || 1)} onBlur={() => set(from, to, "to")}
                   className={numberInput} />
            <span className={cn("ml-auto rounded-md px-2 py-0.5 text-xs font-medium tabular-nums",
              count > maxSpan || count < MIN_RANGE ? "bg-warning-soft text-warning" : "bg-accent-soft text-accent")}>
              {formatNumber(count)} commits
            </span>
          </div>

          {preview.error ? <ErrorNotice error={preview.error} /> : (
            <div className="space-y-1.5 border-t border-border pt-3">
              <CommitRow label="Starts at" commit={preview.data?.newest} />
              <CommitRow label="Ends at" commit={preview.data?.oldest} />
            </div>
          )}
          <p className="text-[11px] text-subtle">
            Commit #1 is the newest. Up to {formatNumber(maxSpan)} commits at a time.
          </p>
        </>
      )}
    </div>
  );
}
