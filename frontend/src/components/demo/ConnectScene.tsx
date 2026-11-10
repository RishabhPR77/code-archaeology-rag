import { Check, ChevronDown, Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";
import { ProviderMark } from "../brand";
import type { DemoState, Reg } from "./data";
import { MODELS, PROVIDERS } from "./data";
import { Btn, SetupChecklist } from "./frame";

export function ConnectScene({ s, t }: { s: DemoState; t: Reg }) {
  if (!s.onSettings) {
    return (
      <div className="h-full">
        <p className="text-[12px] text-muted">Welcome back, Jo</p>
        <p className="text-[17px] font-semibold">Your repositories</p>
        <div className="mt-4"><SetupChecklist t={t} connected={false} /></div>
      </div>
    );
  }
  return (
    <div className="relative h-full">
      <p className="text-[17px] font-semibold">Settings</p>
      <p className="mt-0.5 text-[12px] text-muted">Connect the model provider you want answers from.</p>
      <p className="mt-3 text-[12px] font-semibold">Model providers</p>
      <div className="mt-2 space-y-1.5">
        {PROVIDERS.map((p) => {
          const chosen = p.id === "anthropic";
          const open = chosen && s.expanded;
          return (
            <div key={p.id} className={cn("rounded-xl border bg-surface transition-colors", open ? "border-accent/40" : "border-border")}>
              <div ref={chosen ? t("provider-anthropic") : undefined} className="flex items-center gap-3 px-3 py-1.5">
                <ProviderMark id={p.id} className="size-6 text-[9px]" />
                <span className="text-[12.5px] font-medium">{p.name}</span>
                <span className={cn("rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                  chosen && s.connected ? "bg-success-soft text-success" : "bg-surface-2 text-subtle")}>
                  {chosen && s.connected ? (s.model ? "Active" : "Connected") : "Not connected"}
                </span>
                <ChevronDown className={cn("ml-auto size-3.5 text-subtle transition-transform", open && "rotate-180")} />
              </div>
              {open && (
                <div className="space-y-3 border-t border-border px-3 py-2.5 animate-fade-up">
                  {!s.connected ? (
                    <div className="flex gap-2">
                      <span ref={t("key-input")} className="flex h-8 flex-1 items-center rounded-lg border border-accent bg-bg px-3 font-mono text-[12px]">
                        {s.keyText || <span className="text-subtle">Paste your Anthropic API key</span>}
                        <span className="ml-0.5 h-4 w-px animate-pulse bg-text" />
                      </span>
                      <Btn primary r={t("verify")}>
                        {s.saving && <Loader2 className="size-3.5 animate-spin" />} Verify & save
                      </Btn>
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      {MODELS.map((m, i) => (
                        <span key={m} ref={t(`model-${i}`)}
                              className={cn("flex items-center gap-2 rounded-lg border px-2.5 py-1.5 font-mono text-[11px]",
                                s.model === m ? "border-accent bg-accent-soft" : "border-border")}>
                          <span className={cn("grid size-3.5 place-items-center rounded-full border",
                            s.model === m ? "border-accent bg-accent text-accent-fg" : "border-border-strong")}>
                            {s.model === m && <Check className="size-2.5" strokeWidth={3} />}
                          </span>
                          <span className="truncate">{m}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {s.toast && (
        <div className="absolute top-0 right-0 flex items-center gap-2 rounded-xl border border-border bg-surface px-3 py-2.5 text-[12px] shadow-card animate-fade-up">
          <Check className="size-4 text-success" /> {s.toast}
        </div>
      )}
    </div>
  );
}
