import { Check, Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";
import type { DemoState, Reg } from "./data";
import { SUSPECTS } from "./data";
import { Btn, RepoTitle } from "./frame";

export function SuspectsScene({ s, t }: { s: DemoState; t: Reg }) {
  return (
    <div className="flex h-full flex-col">
      <RepoTitle active="Who broke it?" t={t} />
      <div className="mt-3 rounded-xl border border-border bg-surface p-3">
        <div className="flex items-baseline justify-between text-[11px]">
          <span className="font-medium">Describe the bug</span>
          <span className="text-[10px] text-subtle">An error message or stack trace helps most</span>
        </div>
        <span ref={t("report")}
              className={cn("mt-1.5 block h-[44px] overflow-hidden rounded-lg border bg-surface px-2.5 py-1.5 text-[11px] leading-snug",
                s.report ? "border-accent" : "border-border")}>
          {s.report ? (
            <>{s.report.split("\n")[0]}{s.report.includes("\n") && <span className="block font-mono text-[10px] text-muted">{s.report.split("\n")[1]}</span>}</>
          ) : <span className="text-subtle">What went wrong, and any error or stack trace</span>}
        </span>
        <div className="mt-2 flex items-end gap-2.5">
          <span className="text-[10px] text-muted">It worked before (optional)
            <span className="mt-0.5 block h-7 w-32 rounded-lg border border-border px-2 py-1 text-[10.5px] text-subtle">dd-mm-yyyy</span>
          </span>
          <span ref={t("find")}><Btn primary className="h-7">{s.finding && <Loader2 className="size-3.5 animate-spin" />} Find suspects</Btn></span>
        </div>
      </div>

      <div className="mt-2.5 space-y-2">
        {SUSPECTS.slice(0, s.suspects).map((x, i) => (
          <div key={x.sha} ref={i === 0 ? t("suspect-0") : undefined}
               className="rounded-xl border border-border bg-surface px-3.5 py-2 animate-fade-up">
            <div className="flex items-center gap-2 text-[11px]">
              <span className={cn("rounded-md px-1.5 py-0.5 text-[10px] font-medium", i === 0 ? "bg-danger-soft text-danger" : "bg-surface-2 text-muted")}>
                #{i + 1}{i === 0 && " Most likely"}
              </span>
              <span className="font-mono font-semibold text-accent">{x.sha}</span>
              <span className="rounded-md bg-accent-soft px-1.5 py-0.5 text-[9px] font-semibold text-accent uppercase">{x.type}</span>
              <span className="truncate font-medium">{x.msg}</span>
              <span className="ml-auto shrink-0 text-[10px] text-subtle">score {x.score}/100</span>
            </div>
            <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-surface-3">
              <div className="h-full origin-left rounded-full bg-accent transition-transform duration-700 ease-out"
                   style={{ width: `${x.score}%`, transform: `scaleX(${s.suspects > i ? 1 : 0})` }} />
            </div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-[10.5px] text-muted">
              {x.reasons.map((why) => <span key={why} className="inline-flex items-center gap-1"><Check className="size-3 text-accent" />{why}</span>)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
