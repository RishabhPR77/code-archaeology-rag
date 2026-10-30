import { GitCommitHorizontal, GitPullRequest } from "lucide-react";

import { GitHubIcon } from "./brand";
import { Badge } from "./ui";

// A sample question and answer. The repository and people shown are fictional.
const SOURCES = [
  { pr: false, ref: "3f9c2a1", title: "Move token refresh out of CheckoutSession" },
  { pr: false, ref: "a81e0c4", title: "Add an idempotent retry to the payment path" },
  { pr: true, ref: "#412", title: "Stop double charges on expired sessions" },
];

export function AnswerPreview() {
  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-surface text-left shadow-card">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <GitHubIcon className="size-4 text-muted" />
        <span className="truncate font-mono text-[13px] font-semibold">acme/storefront</span>
        <Badge tone="success" className="ml-auto">Ready</Badge>
      </div>
      <div className="space-y-4 p-4 sm:p-5">
        <p className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-sm font-medium text-accent-fg">
          Why was the checkout session logic refactored?
        </p>
        <p className="text-sm leading-relaxed">
          Token refresh was moved out of <code className="rounded bg-surface-2 px-1 font-mono text-[12.5px]">CheckoutSession</code> after
          two bug fixes traced double charges to sessions expiring mid-payment. The review on PR #412 asked for
          a retry that is safe to repeat.
        </p>
        <div className="border-t border-border pt-3.5">
          <p className="text-xs font-semibold text-muted">Sources</p>
          <ul className="mt-2 space-y-1.5">
            {SOURCES.map((s) => (
              <li key={s.ref} className="flex items-center gap-2 text-xs">
                {s.pr ? <GitPullRequest className="size-3.5 shrink-0 text-subtle" /> : <GitCommitHorizontal className="size-3.5 shrink-0 text-subtle" />}
                <span className="shrink-0 font-mono font-semibold text-accent">{s.ref}</span>
                <span className="truncate text-muted">{s.title}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
