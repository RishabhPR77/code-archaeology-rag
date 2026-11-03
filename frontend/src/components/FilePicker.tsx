import { File, Folder, Search, TextSearch } from "lucide-react";
import { useEffect, useId, useMemo, useState, type KeyboardEvent, type ReactNode } from "react";

import type { RepoFile, TimelineMatch } from "../lib/types";
import { cn } from "../lib/utils";

export interface FileChoice { path: string; match: TimelineMatch }

interface Option extends FileChoice { key: string; name: string; dir: string; detail: string }

const LIMIT = 50;

/** What the search box shows once a choice is made. */
export const choiceLabel = (c: FileChoice) => (c.match === "folder" ? `${c.path}/` : c.path);

const split = (path: string) => {
  const i = path.lastIndexOf("/");
  return { name: path.slice(i + 1), dir: i < 0 ? "" : path.slice(0, i) };
};

// Lower ranks first: an exact or leading match on the name beats a match anywhere in the path
function rank(path: string, q: string) {
  const p = path.toLowerCase();
  const name = p.slice(p.lastIndexOf("/") + 1);
  if (name === q) return 0;
  if (name.startsWith(q)) return 1;
  if (name.includes(q)) return 2;
  return p.includes(q) ? 3 : -1;
}

function Highlight({ text, q }: { text: string; q: string }) {
  const i = q ? text.toLowerCase().indexOf(q) : -1;
  if (i < 0) return <>{text}</>;
  return <>{text.slice(0, i)}<mark className="bg-transparent font-bold text-accent">{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>;
}

function buildOptions(files: RepoFile[], query: string): { options: Option[]; matches: number } {
  const q = query.trim().toLowerCase().replace(/\/+$/, "");
  const file = (f: RepoFile): Option => ({
    key: `f:${f.path}`, path: f.path, match: "exact", ...split(f.path),
    detail: `${f.changes} ${f.changes === 1 ? "change" : "changes"}`,
  });
  if (!q) return { options: files.slice(0, LIMIT).map(file), matches: files.length };

  const hits = files.map((f) => ({ f, r: rank(f.path, q) })).filter((h) => h.r >= 0);
  hits.sort((a, b) => a.r - b.r || b.f.changes - a.f.changes || a.f.path.localeCompare(b.f.path));

  // Folders whose own name matches, with how many changed files sit inside them
  const folders = new Map<string, number>();
  for (const f of files) {
    const parts = f.path.split("/");
    for (let i = 1; i < parts.length; i++) {
      const dir = parts.slice(0, i).join("/");
      if (parts[i - 1].toLowerCase().includes(q)) folders.set(dir, (folders.get(dir) ?? 0) + 1);
    }
  }
  const folderOptions: Option[] = [...folders].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([dir, n]) => ({
    key: `d:${dir}`, path: dir, match: "folder", ...split(dir), detail: `${n} ${n === 1 ? "file" : "files"}`,
  }));

  const options: Option[] = [];
  if (hits.length > 1) {
    options.push({ key: "contains", path: query.trim(), match: "contains", name: `Every path containing “${query.trim()}”`,
                   dir: "", detail: `${hits.length} files` });
  }
  options.push(...folderOptions, ...hits.slice(0, LIMIT).map((h) => file(h.f)));
  return { options, matches: hits.length };
}

const ICONS: Record<TimelineMatch, ReactNode> = {
  exact: <File className="size-4" />,
  folder: <Folder className="size-4" />,
  contains: <TextSearch className="size-4" />,
};

/**
 * A searchable list of every file the ingested history touched. Choosing a file traces exactly
 * that file, a folder traces everything inside it, and pressing Enter on free text traces every
 * path containing it.
 */
export function FilePicker({ files, loading, query, onQueryChange, onPick }: {
  files: RepoFile[] | undefined; loading: boolean; query: string;
  onQueryChange: (q: string) => void; onPick: (choice: FileChoice) => void;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const { options, matches } = useMemo(() => buildOptions(files ?? [], query), [files, query]);
  const q = query.trim().toLowerCase().replace(/\/+$/, "");
  const optionId = (i: number) => `${listId}-${i}`;

  useEffect(() => {
    if (active >= 0) document.getElementById(optionId(active))?.scrollIntoView({ block: "nearest" });
  });

  const pick = (o: Option) => {
    setOpen(false);
    setActive(-1);
    onPick({ path: o.path, match: o.match });
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((a) => Math.max(0, Math.min(options.length - 1, a + step)));
    } else if (e.key === "Enter" && open && active >= 0 && options[active]) {
      e.preventDefault();  // otherwise Enter submits the form as a "contains" search
      pick(options[active]);
    } else if (e.key === "Escape" && open) {
      e.preventDefault();
      setOpen(false);
    }
  };

  return (
    <div className="relative flex-1">
      <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
      <input
        role="combobox"
        aria-label="File or folder to trace"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        autoComplete="off"
        spellCheck={false}
        value={query}
        placeholder="Search files and folders, e.g. main.py"
        onChange={(e) => { onQueryChange(e.target.value); setOpen(true); setActive(-1); }}
        onFocus={() => setOpen(true)}
        onClick={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        className={cn(
          "h-10 w-full rounded-lg border border-border bg-surface pr-3 pl-9 font-mono text-[13px] text-text",
          "outline-none transition-colors placeholder:font-sans placeholder:text-subtle",
          "focus:border-accent focus:ring-3 focus:ring-accent-soft",
        )}
      />

      {open && (
        // mousedown would blur the input before the click lands, closing the list first
        <div onMouseDown={(e) => e.preventDefault()}
             className="absolute inset-x-0 top-full z-20 mt-1.5 overflow-hidden rounded-xl border border-border bg-surface shadow-card">
          {loading ? (
            <p className="px-3 py-3 text-[13px] text-muted">Loading files…</p>
          ) : options.length === 0 ? (
            <p className="px-3 py-3 text-[13px] text-muted">
              {q ? <>No file or folder matches “{query.trim()}”.</> : "No files in the ingested history."}
            </p>
          ) : (
            <>
              <p className="border-b border-border px-3 py-2 text-[11px] font-semibold text-subtle">
                {q ? "Matching files and folders" : "Most changed files"}
              </p>
              <ul id={listId} role="listbox" className="max-h-72 overflow-y-auto py-1">
                {options.map((o, i) => (
                  <li
                    key={o.key}
                    id={optionId(i)}
                    role="option"
                    aria-selected={i === active}
                    onClick={() => pick(o)}
                    onMouseMove={() => active !== i && setActive(i)}
                    className={cn("flex cursor-pointer items-center gap-2.5 px-3 py-2",
                      i === active ? "bg-accent-soft" : "hover:bg-surface-2")}
                  >
                    <span className={cn("shrink-0", o.match === "exact" ? "text-subtle" : "text-accent")}>{ICONS[o.match]}</span>
                    <span className="min-w-0 flex-1">
                      <span className={cn("block truncate text-[13px]", o.match !== "contains" && "font-mono")}>
                        {o.match === "contains" ? o.name : <Highlight text={o.name} q={q} />}
                        {o.match === "folder" && "/"}
                      </span>
                      {o.dir && <span className="block truncate font-mono text-[11px] text-subtle"><Highlight text={o.dir} q={q} /></span>}
                    </span>
                    <span className="shrink-0 text-[11px] text-subtle">{o.detail}</span>
                  </li>
                ))}
              </ul>
              {matches > LIMIT && (
                <p className="border-t border-border px-3 py-2 text-[11px] text-subtle">
                  Showing {LIMIT} of {matches} files. Keep typing to narrow it down.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
