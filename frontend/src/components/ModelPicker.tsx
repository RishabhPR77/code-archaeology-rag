import { Check, RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { Model } from "../lib/types";
import { cn, compactTokens } from "../lib/utils";
import { Input, Skeleton } from "./ui";

export function ModelPicker({ models, selected, onSelect, loading, pending, onRefresh, refreshing }: {
  models: Model[] | undefined;
  selected: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  pending: string | null;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = models ?? [];
    return needle ? list.filter((m) => `${m.name} ${m.id}`.toLowerCase().includes(needle)) : list;
  }, [models, q]);

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-subtle" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search models"
                 className="h-9 pl-8 text-[13px]" aria-label="Search models" />
        </div>
        <button onClick={onRefresh} disabled={refreshing} title="Reload from provider" aria-label="Reload models"
                className="grid size-9 place-items-center rounded-lg border border-border text-muted hover:text-text disabled:opacity-50 cursor-pointer">
          <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
        </button>
      </div>

      <div role="listbox" aria-label="Models" className="max-h-72 overflow-y-auto rounded-lg border border-border">
        {loading && (
          <div className="space-y-2 p-3">
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10" />)}
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <p className="px-3 py-6 text-center text-[13px] text-subtle">No models match “{q}”.</p>
        )}
        {filtered.map((m) => {
          const isSelected = m.id === selected;
          const ctx = compactTokens(m.context_window);
          return (
            <button
              key={m.id}
              role="option"
              aria-selected={isSelected}
              onClick={() => onSelect(m.id)}
              disabled={pending !== null}
              className={cn(
                "flex w-full items-center gap-3 border-b border-border px-3 py-2.5 text-left last:border-b-0 transition-colors cursor-pointer",
                isSelected ? "bg-accent-soft" : "hover:bg-surface-2",
              )}
            >
              <span className={cn("grid size-4 shrink-0 place-items-center rounded-full border",
                isSelected ? "border-accent bg-accent text-accent-fg" : "border-border-strong")}>
                {isSelected && <Check className="size-2.5" strokeWidth={3} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] font-medium">{m.name}</span>
                {m.name !== m.id && <span className="block truncate font-mono text-[11px] text-subtle">{m.id}</span>}
              </span>
              {ctx && <span className="shrink-0 rounded border border-border px-1.5 py-0.5 font-mono text-[10px] text-muted">{ctx} ctx</span>}
              {pending === m.id && <RefreshCw className="size-3.5 animate-spin text-muted" />}
            </button>
          );
        })}
      </div>
      {models && <p className="mt-1.5 text-xs text-subtle">{models.length} text models available with this key · listed live from the provider</p>}
    </div>
  );
}
