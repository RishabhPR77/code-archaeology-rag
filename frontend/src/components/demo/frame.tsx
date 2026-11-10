import { CheckCircle2, ChevronDown, Circle, LayoutGrid, Lock, LogOut, Moon, Plus, Settings, UserRound } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "../../lib/utils";
import { LogoMark, ProviderMark } from "../brand";
import type { DemoState, Reg } from "./data";
import { ACTIVITY, HOT, MODELS, TABS } from "./data";

export function pageUrl(scene: number, s: DemoState): string {
  if (scene === 0) return s.verify ? "/verify-email" : "/register";
  if (scene === 1) return s.onSettings ? "/app/settings" : "/app";
  if (scene === 2) return "/app";
  if (scene === 3) return s.askTab ? "/app/repos/storefront/ask" : "/app/repos/storefront";
  if (scene === 4) return "/app/repos/storefront/suspects";
  return s.timelineTab ? "/app/repos/storefront/timeline" : "/app/repos/storefront";
}
export function Chrome({ scene, s }: { scene: number; s: DemoState }) {
  return (
    <div className="absolute inset-x-0 top-0 flex h-9 items-center gap-2 border-b border-border bg-surface px-4">
      <span className="size-2.5 rounded-full bg-[#ff5f57]" />
      <span className="size-2.5 rounded-full bg-[#febc2e]" />
      <span className="size-2.5 rounded-full bg-[#28c840]" />
      <span className="mx-auto w-80 truncate rounded-md bg-surface-2 px-3 py-0.5 text-center font-mono text-[11px] text-subtle">
        code-archaeologist.app{pageUrl(scene, s)}
      </span>
    </div>
  );
}

/** The real top bar: logo, the open repository, the model, theme, New repository and the account menu. */
export function AppBar({ scene, s, t }: { scene: number; s: DemoState; t: Reg }) {
  const inRepo = scene >= 3;
  const model = scene > 1 || s.model;
  return (
    <div className="absolute inset-x-0 top-9 z-20 flex h-11 items-center gap-2 border-b border-border bg-surface px-5">
      <span ref={t("logo")} className="flex items-center gap-2">
        <LogoMark className="size-6" />
        <span className="text-[13px] font-semibold">Code Archaeologist</span>
      </span>
      {inRepo && (
        <>
          <span className="text-border-strong">/</span>
          <span className="flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-[12px]">
            <span className="grid size-5 place-items-center rounded-md bg-accent text-[9px] font-bold text-accent-fg">A</span>
            <span className="text-subtle">acme /</span><b>storefront</b>
            <ChevronDown className="size-3 text-subtle" />
          </span>
        </>
      )}
      <div className="flex-1" />
      {model && (
        <span className="flex items-center gap-1.5 rounded-lg border border-border px-1.5 py-0.5">
          <ProviderMark id="anthropic" className="size-5 text-[8px]" />
          <span className="font-mono text-[10px] text-muted">{MODELS[1]}</span>
        </span>
      )}
      <Moon className="mx-1 size-3.5 text-muted" />
      <span ref={scene === 2 ? t("new-repo") : undefined}>
        <Btn primary className="h-7"><Plus className="size-3.5" /> New repository</Btn>
      </span>
      <span ref={t("avatar")} className={cn("grid size-7 place-items-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent",
        s.menu && "ring-2 ring-accent/50")}>J</span>
      {s.menu && (
        <div className="absolute top-10 right-4 w-48 rounded-xl border border-border bg-surface p-1 text-[12px] shadow-card animate-fade-up">
          <div className="border-b border-border px-2.5 pt-1 pb-1.5">
            <p className="font-medium">Jo Chen</p>
            <p className="text-[10px] text-subtle">jo@acme.dev</p>
          </div>
          <p className="mt-1 flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-muted"><UserRound className="size-3.5" /> Profile</p>
          <p className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-muted"><LayoutGrid className="size-3.5" /> Repositories</p>
          <p className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-muted"><Settings className="size-3.5" /> Settings</p>
          <p ref={t("menu-signout")} className="flex items-center gap-2 rounded-lg bg-surface-2 px-2.5 py-1.5 text-text"><LogOut className="size-3.5" /> Sign out</p>
        </div>
      )}
    </div>
  );
}
export function Cursor({ x, y, click }: { x: number; y: number; click: number }) {
  return (
    <div className="pointer-events-none absolute top-0 left-0 z-50 transition-transform duration-700 ease-in-out"
         style={{ transform: `translate(${x}px, ${y}px)` }}>
      {click > 0 && (
        <span key={click} className="absolute -top-4 -left-4 size-8 rounded-full border-2 border-accent animate-[demo-ripple_0.45s_ease-out_forwards]" />
      )}
      <svg width="22" height="22" viewBox="0 0 24 24" className="drop-shadow-md" key={`c${click}`}
           style={{ animation: click > 0 ? "demo-press 0.22s ease-out" : undefined }}>
        <path d="M4 2.5 19.5 12l-7 1.6L9 20.5z" fill="#fff" stroke="#111" strokeWidth="1.6" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
export function Btn({ children, primary, className, r }: { children: ReactNode; primary?: boolean; className?: string; r?: (el: HTMLElement | null) => void }) {
  return (
    <span ref={r} className={cn("inline-flex h-8 items-center justify-center gap-1.5 rounded-lg px-3 text-[12px] font-medium whitespace-nowrap",
      primary ? "bg-accent text-accent-fg" : "border border-border bg-surface-2 text-text", className)}>
      {children}
    </span>
  );
}

/** The repository header and its ten tabs, each one a cursor target. */
export function RepoTitle({ active, t }: { active: string; t: Reg }) {
  return (
    <>
      <div className="flex items-center gap-2">
        <span className="font-mono text-[15px] font-semibold">acme/storefront</span>
        <span className="rounded-md bg-warning-soft px-1.5 py-0.5 text-[10px] text-warning"><Lock className="mr-0.5 inline size-2.5" />Private</span>
        <span className="rounded-md bg-success-soft px-1.5 py-0.5 text-[10px] text-success">Ready</span>
        <span className="text-[10px] text-subtle">· commits 1–300 · 86 linked PRs</span>
      </div>
      <div className="mt-2 flex gap-3.5 border-b border-border text-[11.5px] whitespace-nowrap">
        {TABS.map((tab) => (
          <span key={tab} ref={t(`tab-${tab}`)}
                className={cn("-mb-px border-b-2 pb-1.5 transition-colors", tab === active ? "border-accent text-text" : "border-transparent text-muted")}>
            {tab}
          </span>
        ))}
      </div>
    </>
  );
}
export function Field({ label, value, placeholder, r, focus }: {
  label: string; value: string; placeholder: string; r: (el: HTMLElement | null) => void; focus: boolean;
}) {
  return (
    <div>
      <p className="text-[11px] font-medium">{label}</p>
      <span ref={r} className={cn("mt-1 flex h-8 items-center rounded-lg border bg-surface px-2.5 text-[12px]",
        focus ? "border-accent ring-2 ring-accent-soft" : "border-border")}>
        {value || <span className="text-subtle">{placeholder}</span>}
        {focus && <span className="ml-0.5 h-3.5 w-px animate-pulse bg-text" />}
      </span>
    </div>
  );
}

/** The real sign-up page, then the "Check your email" code page, in the same two-panel layout. */
export function SetupChecklist({ t, connected }: { t?: Reg; connected: boolean }) {
  const steps = [
    { done: connected, title: "Connect a model provider", body: "Add your Anthropic, OpenAI, Gemini, Groq or OpenRouter key and pick a model.", action: "Open settings" },
    { done: false, title: "Ingest a repository", body: "Paste a public GitHub URL. Commits, PRs and reviews are indexed in a few minutes.", action: "New repository" },
    { done: false, title: "Ask why", body: "Open a repository and ask about any change in plain English.", action: "" },
  ];
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
      <p className="text-[12.5px] font-semibold">Get set up</p>
      <p className="text-[11px] text-muted">Two quick steps and you're ready to ask questions.</p>
      <ol className="mt-3 space-y-2.5">
        {steps.map((st, i) => (
          <li key={st.title} className="flex items-center gap-2.5">
            {st.done ? <CheckCircle2 className="size-4 shrink-0 text-success" /> : <Circle className="size-4 shrink-0 text-border-strong" />}
            <span className="min-w-0 flex-1">
              <span className={cn("block text-[11.5px] font-medium", st.done && "text-muted line-through")}>{i + 1}. {st.title}</span>
              <span className="block truncate text-[10.5px] text-muted">{st.body}</span>
            </span>
            {!st.done && st.action && (
              <span ref={i === 0 ? t?.("open-settings") : undefined}>
                <Btn primary={i === (connected ? 1 : 0)} className="h-7">{st.action}</Btn>
              </span>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
export function AnswerText({ text }: { text: string }) {
  // Backticked spans render as commit-SHA chips, even mid-typing
  return (
    <>
      {text.split("`").map((part, i) => i % 2
        ? <code key={i} className="rounded bg-surface-3 px-1 font-mono text-[11px] text-accent">{part}</code>
        : <span key={i}>{part}</span>)}
    </>
  );
}
export function OverviewBody({ s, t }: { s: DemoState; t?: Reg }) {
  const max = Math.max(...ACTIVITY);
  const points = ACTIVITY.map((v, i) => `${(i / (ACTIVITY.length - 1)) * 300},${100 - (v / max) * 88}`).join(" ");
  return (
    <>
      <div className="mt-3 grid grid-cols-4 gap-3">
        {[["Commits", "300"], ["Contributors", "7"], ["Files touched", "64"], ["Linked pull requests", "86"]].map(([label, n], i) => (
          <div key={label} className="rounded-xl border border-border bg-surface p-3 transition-all duration-500"
               style={{ opacity: s.grow ? 1 : 0.25, transform: s.grow ? "none" : "translateY(8px)", transitionDelay: `${i * 80}ms` }}>
            <p className="text-[10px] text-muted">{label}</p>
            <p className="mt-1 text-[20px] font-semibold">{n}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 grid grid-cols-5 gap-3">
        <div ref={t?.("chart")} className="col-span-3 rounded-xl border border-border bg-surface p-3">
          <p className="text-[11px] font-medium">Commit activity</p>
          <p className="text-[10px] text-subtle">Commits per week</p>
          <svg viewBox="0 0 300 100" preserveAspectRatio="none" className="mt-2 h-28 w-full origin-bottom transition-transform duration-700 ease-out"
               style={{ transform: `scaleY(${s.grow ? 1 : 0.08})` }}>
            <polygon points={`0,100 ${points} 300,100`} fill="var(--accent)" opacity="0.15" />
            <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
          </svg>
        </div>
        <div className="col-span-2 rounded-xl border border-border bg-surface p-3">
          <p className="text-[11px] font-medium">Hottest files</p>
          <ul className="mt-3 space-y-2.5">
            {HOT.map(([f, w], i) => (
              <li key={f}>
                <p className="truncate font-mono text-[10px]">{f}</p>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2">
                  <div className="h-full origin-left rounded-full bg-accent transition-transform duration-700 ease-out"
                       style={{ width: `${w}%`, transform: `scaleX(${s.grow ? 1 : 0})`, transitionDelay: `${200 + i * 90}ms` }} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </>
  );
}
export function Match({ text, q }: { text: string; q: string }) {
  const i = q ? text.indexOf(q) : -1;
  if (i < 0) return <>{text}</>;
  return <>{text.slice(0, i)}<b className="text-accent">{text.slice(i, i + q.length)}</b>{text.slice(i + q.length)}</>;
}
