import { ArrowUp, Plus, Sparkles, Square } from "lucide-react";
import { cn } from "../../lib/utils";
import { ProviderMark } from "../brand";
import type { DemoState, Reg } from "./data";
import { ANSWER, MODELS, QUESTION, SOURCES } from "./data";
import { AnswerText, Btn, OverviewBody, RepoTitle } from "./frame";

export function AskScene({ s, t }: { s: DemoState; t: Reg }) {
  const writing = s.asked && s.answer > 0 && s.answer < ANSWER.length;
  if (!s.askTab) {
    return (
      <div className="h-full">
        <RepoTitle active="Overview" t={t} />
        <OverviewBody s={{ ...s, grow: true }} />
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col">
      <RepoTitle active="Ask" t={t} />
      <div className="mt-3 grid min-h-0 flex-1 grid-cols-[150px_1fr] gap-4">
        <div className="space-y-3">
          <Btn className="w-full justify-start"><Plus className="size-3.5" /> New chat</Btn>
          <div>
            <p className="px-1 text-[9.5px] font-semibold tracking-wider text-subtle uppercase">Chats</p>
            {s.asked ? (
              <div className="mt-1.5 rounded-lg bg-accent-soft px-2 py-1.5 animate-fade-up">
                <p className="truncate text-[11px] font-medium">{QUESTION}</p>
                <p className="text-[9.5px] text-subtle">just now · 1 question</p>
              </div>
            ) : <p className="mt-1.5 px-1 text-[10.5px] text-subtle">Your chats will appear here.</p>}
          </div>
        </div>

        <div className="flex min-h-0 flex-col">
          <div className="min-h-0 flex-1 space-y-2.5 overflow-hidden">
            {!s.asked ? (
              <div className="grid h-full place-items-center text-center">
                <div>
                  <div className="mx-auto grid size-9 place-items-center rounded-xl bg-accent-soft text-accent"><Sparkles className="size-4" /></div>
                  <p className="mt-2 text-[13px] font-medium">Ask about acme/storefront</p>
                  <p className="text-[11px] text-muted">Answers come only from this repository's commits, PRs and reviews.</p>
                </div>
              </div>
            ) : (
              <>
                <div className="ml-auto w-fit max-w-[75%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-[12px] text-accent-fg animate-fade-up">{QUESTION}</div>
                <div className="rounded-xl border border-border bg-surface p-3.5 animate-fade-up">
                  <div className="mb-2 flex items-center gap-2 text-[10px] text-subtle">
                    <ProviderMark id="anthropic" className="size-4 text-[7px]" />
                    <span className="font-mono">{MODELS[1]}</span><span>·</span><span>Detailed</span>
                    {writing && (
                      <span className="ml-auto inline-flex items-center gap-1.5 text-accent">
                        <span className="size-1.5 animate-pulse rounded-full bg-accent" /> Writing…
                      </span>
                    )}
                  </div>
                  {s.answer === 0 ? (
                    <div className="flex items-center gap-2 py-1 text-[11px] text-muted">
                      <span className="flex gap-1">
                        {[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-bounce rounded-full bg-accent" style={{ animationDelay: `${i * 120}ms` }} />)}
                      </span>
                      {s.found ? <>Found the relevant commits. Waiting for <span className="font-mono">{MODELS[1]}</span>…</> : "Searching this repository's history…"}
                    </div>
                  ) : (
                    <p className="text-[12px] leading-relaxed">
                      <AnswerText text={ANSWER.slice(0, s.answer)} />
                      {writing && <span className="ml-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 animate-pulse bg-accent" />}
                    </p>
                  )}
                  {s.sources > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-border pt-2.5">
                      {SOURCES.slice(0, s.sources).map((src, i) => (
                        <span key={src} ref={t(`source-${i}`)} className="rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-muted animate-fade-up">{src}</span>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          <div className="mt-2.5 flex items-center gap-2 rounded-xl border border-border bg-surface p-1.5">
            <span ref={t("ask-input")} className="flex h-8 flex-1 items-center px-2 text-[12px]">
              {s.asked ? <span className="text-subtle">Ask another question in this chat</span> : s.question || <span className="text-subtle">Why was the auth module refactored?</span>}
              {!s.asked && s.question && <span className="ml-0.5 h-4 w-px animate-pulse bg-text" />}
            </span>
            {s.asked && s.answer < ANSWER.length ? (
              <span ref={t("stop")} className="grid size-8 place-items-center rounded-lg border border-border bg-surface-2 text-text">
                <Square className="size-3 fill-current" />
              </span>
            ) : (
              <span ref={t("send")} className={cn("grid size-8 place-items-center rounded-lg bg-accent text-accent-fg", !s.question && "opacity-50")}>
                <ArrowUp className="size-3.5" />
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
