import { useState } from "react";

import type { Repo } from "../lib/types";
import { cn } from "../lib/utils";

/** The repository owner's GitHub avatar, with the owner's initial if it can't load. */
export function RepoAvatar({ fullName, className }: { fullName: string; className?: string }) {
  const owner = fullName.split("/")[0] ?? "";
  const [failed, setFailed] = useState(false);
  if (failed || !owner) {
    return (
      <span className={cn("grid size-7 shrink-0 place-items-center rounded-lg bg-surface-3 text-[11px] font-semibold uppercase text-muted", className)}>
        {owner[0] ?? "?"}
      </span>
    );
  }
  return (
    <img src={`https://github.com/${encodeURIComponent(owner)}.png?size=64`} alt=""
         onError={() => setFailed(true)}
         className={cn("size-7 shrink-0 rounded-lg bg-surface-3 object-cover", className)} />
  );
}

const DOT = { ready: "bg-success", failed: "bg-danger" } as const;

/** A small status dot to sit on the corner of an avatar: ready, failed, or ingesting (pulsing). */
export function StatusDot({ repo, className }: { repo: Repo; className?: string }) {
  const color = DOT[repo.status as keyof typeof DOT] ?? "bg-warning animate-pulse";
  return <span className={cn("size-2 shrink-0 rounded-full ring-2 ring-surface", color, className)} />;
}
