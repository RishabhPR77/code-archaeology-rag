import type { CommitType } from "../lib/types";
import { COMMIT_TYPES } from "../lib/utils";

export function CommitTypeBadge({ type }: { type: CommitType }) {
  const { label, color } = COMMIT_TYPES[type];
  return (
    <span className="inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase"
          style={{ color, background: `${color}1f` }}>
      {label}
    </span>
  );
}
