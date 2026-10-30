import { ArrowUp, Check, FolderGit2, Globe, LayoutDashboard, Loader2, Lock, Plus, Settings, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "../lib/utils";
import { GitHubIcon, LogoMark, ProviderMark } from "./brand";

/*
 * An animated walkthrough of the app: a fake cursor moves, clicks and types through
 * four scenes on a loop. Everything is drawn at a fixed 880x500 "canvas" and scaled
 * to fit, so cursor targets are measured in canvas coordinates. The repository and
 * people shown are fictional.
 */

const W = 880;
const H = 500;

const SCENES = [
  { id: "connect", title: "Connect your model",
    body: "Paste an API key from Anthropic, OpenAI, Gemini, Groq or OpenRouter, then pick any model from its live list." },
  { id: "ingest", title: "Ingest a repository",
    body: "Choose one of your GitHub repositories, private ones included, or paste any public URL." },
  { id: "ask", title: "Ask why",
    body: "Ask in plain English. Answers cite the exact commits and pull requests they come from." },
  { id: "explore", title: "Explore the history",
    body: "See hot spots, busy weeks and the files that change together, without asking anything." },
] as const;

const PROVIDERS = [
  { id: "anthropic", name: "Anthropic" }, { id: "openai", name: "OpenAI" },
  { id: "gemini", name: "Google Gemini" }, { id: "groq", name: "Groq" },
  { id: "openrouter", name: "OpenRouter" },
] as const;
const MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"];
const REPOS = [
  { name: "acme/storefront", private: true }, { name: "acme/payments-api", private: true },
  { name: "acme/docs", private: false },
];
const STAGES = ["Cloning repository", "Reading commits", "Fetching pull requests", "Embedding history", "Ready"];
const QUESTION = "Why was the checkout session logic refactored?";
const ANSWER = "The refactor in `3f9c2a1` moved token refresh out of `CheckoutSession` after two fix commits " +
  "traced double charges to sessions expiring mid-payment. The review on PR #412 asked for an idempotent " +
  "retry path, added in `a81e0c4`.";
const SOURCES = ["3f9c2a1 · j.chen", "a81e0c4 · m.okafor", "PR #412"];
const BARS = [3, 5, 4, 8, 6, 11, 7, 9, 14, 10, 6, 12];
const HOT = [["checkout/session.ts", 100], ["payments/retry.ts", 74], ["api/orders.ts", 58], ["checkout/cart.ts", 41]] as const;

interface DemoState {
  expanded: boolean; keyText: string; saving: boolean; connected: boolean; model: string | null; toast: string | null;
  dialog: boolean; picked: string | null; ingesting: boolean; stage: number;
  question: string; asked: boolean; thinking: boolean; answer: number; sources: number;
  grow: boolean; hotTab: boolean;
}

const START: DemoState = {
  expanded: false, keyText: "", saving: false, connected: false, model: null, toast: null,
  dialog: false, picked: null, ingesting: false, stage: -1,
  question: "", asked: false, thinking: false, answer: 0, sources: 0,
  grow: false, hotTab: false,
};

// What each scene looks like when it has finished — used for reduced motion
const FINAL: Record<number, Partial<DemoState>> = {
  0: { expanded: true, keyText: "sk-ant-••••••••••••••••", connected: true, model: MODELS[1] },
  1: { picked: REPOS[0].name, ingesting: true, stage: STAGES.length - 1 },
  2: { question: QUESTION, asked: true, answer: ANSWER.length, sources: SOURCES.length },
  3: { grow: true },
};

class Cancelled extends Error {}

export function ProductDemo() {
  const [scene, setScene] = useState(0);
  const [s, setS] = useState<DemoState>(START);
  const [cursor, setCursor] = useState({ x: W / 2, y: H - 40, click: 0 });
  const [scale, setScale] = useState(1);
  const [reduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);

  const outer = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const targets = useRef(new Map<string, HTMLElement>());
  const epoch = useRef(0);
  const paused = useRef(false);
  // `n` makes every tab click restart, even on the scene the loop started from
  const [start, setStart] = useState({ at: 0, n: 0 });
  const startAt = start.at;

  const patch = useCallback((p: Partial<DemoState>) => setS((prev) => ({ ...prev, ...p })), []);
  const t = useCallback((key: string) => (el: HTMLElement | null) => {
    if (el) targets.current.set(key, el);
    else targets.current.delete(key);
  }, []);

  // Fit the fixed-size canvas to the available width
  useEffect(() => {
    const el = outer.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setScale(Math.min(1, entry.contentRect.width / W)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Pause while off screen or in a background tab
  useEffect(() => {
    const el = outer.current;
    if (!el) return;
    let visible = true;
    const sync = () => { paused.current = !visible || document.hidden; };
    const io = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; sync(); }, { threshold: 0.15 });
    io.observe(el);
    document.addEventListener("visibilitychange", sync);
    return () => { io.disconnect(); document.removeEventListener("visibilitychange", sync); };
  }, []);

  // The script runner
  useEffect(() => {
    if (reduced) {
      setS({ ...START, ...FINAL[startAt] });
      setScene(startAt);
      return;
    }
    const mine = ++epoch.current;
    const alive = () => { if (epoch.current !== mine) throw new Cancelled(); };

    const sleep = (ms: number) => new Promise<void>((resolve, reject) => {
      let left = ms;
      let last = performance.now();
      const tick = () => {
        if (epoch.current !== mine) return reject(new Cancelled());
        const now = performance.now();
        if (!paused.current) left -= now - last;
        last = now;
        if (left <= 0) resolve();
        else setTimeout(tick, Math.min(left, 80));
      };
      setTimeout(tick, Math.min(ms, 80));
    });

    const move = async (key: string, ms = 750) => {
      await sleep(60);  // let the target mount after the last state change
      const el = targets.current.get(key);
      const c = canvas.current;
      if (!el || !c) return;
      const r = el.getBoundingClientRect();
      const cr = c.getBoundingClientRect();
      const k = cr.width / W || 1;
      setCursor((p) => ({ ...p, x: (r.left - cr.left + Math.min(r.width / 2, 40)) / k, y: (r.top - cr.top + r.height / 2) / k }));
      await sleep(ms);
    };
    const click = async () => {
      setCursor((p) => ({ ...p, click: p.click + 1 }));
      await sleep(220);
    };
    const type = async (text: string, set: (v: string) => void, speed = 45) => {
      for (let i = 1; i <= text.length; i++) {
        set(text.slice(0, i));
        await sleep(speed);
      }
    };

    const scripts = [
      async () => {  // Connect
        await move("provider-anthropic");
        await click();
        patch({ expanded: true });
        await move("key-input");
        await click();
        await type("sk-ant-••••••••••••••••", (keyText) => patch({ keyText }), 40);
        await move("verify");
        await click();
        patch({ saving: true });
        await sleep(900);
        patch({ saving: false, connected: true, toast: "Anthropic connected · models loaded" });
        await move("model-1");
        await click();
        patch({ model: MODELS[1] });
        await sleep(1600);
      },
      async () => {  // Ingest
        await move("new-repo");
        await click();
        patch({ dialog: true });
        await move("repo-0", 850);
        await click();
        patch({ picked: REPOS[0].name });
        await move("start");
        await click();
        patch({ dialog: false, ingesting: true, stage: 0 });
        for (let i = 1; i < STAGES.length; i++) {
          await sleep(650);
          patch({ stage: i });
        }
        await sleep(1500);
      },
      async () => {  // Ask
        await move("ask-input");
        await click();
        await type(QUESTION, (question) => patch({ question }), 38);
        await move("send", 500);
        await click();
        patch({ asked: true, thinking: true });
        await sleep(900);
        patch({ thinking: false });
        for (let i = 4; i <= ANSWER.length; i += 4) {
          patch({ answer: i });
          await sleep(22);
        }
        patch({ answer: ANSWER.length });
        for (let i = 1; i <= SOURCES.length; i++) {
          await sleep(220);
          patch({ sources: i });
        }
        await move("source-0", 700);
        await sleep(1500);
      },
      async () => {  // Explore
        patch({ grow: true });
        await move("chart", 900);
        await sleep(700);
        await move("tab-hot");
        await click();
        patch({ hotTab: true });
        await move("hot-0", 700);
        await sleep(1800);
      },
    ];

    (async () => {
      let i = startAt;
      try {
        for (;;) {
          alive();
          setScene(i);
          setS(START);
          await sleep(500);
          await scripts[i]();
          i = (i + 1) % scripts.length;
        }
      } catch (e) {
        if (!(e instanceof Cancelled)) throw e;
      }
    })();
    return () => { epoch.current++; };
  }, [start, startAt, reduced, patch]);

  return (
    <div className="mx-auto w-full max-w-[880px]">
      <div ref={outer} className="relative w-full" style={{ height: H * scale }}>
        <div
          ref={canvas}
          aria-hidden
          className="absolute top-0 left-0 overflow-hidden rounded-2xl border border-border bg-bg text-left shadow-2xl select-none"
          style={{ width: W, height: H, transform: `scale(${scale})`, transformOrigin: "top left" }}
        >
          <Chrome />
          <div className="absolute top-9 bottom-0 left-0 flex w-14 flex-col items-center gap-4 border-r border-border bg-surface pt-4 text-subtle">
            <LogoMark className="size-6" />
            <LayoutDashboard className={cn("size-4", scene === 1 && "text-accent")} />
            <FolderGit2 className={cn("size-4", (scene === 2 || scene === 3) && "text-accent")} />
            <Settings className={cn("size-4", scene === 0 && "text-accent")} />
          </div>
          <div className="absolute top-9 right-0 bottom-0 left-14 p-6">
            {scene === 0 && <ConnectScene s={s} t={t} />}
            {scene === 1 && <IngestScene s={s} t={t} />}
            {scene === 2 && <AskScene s={s} t={t} />}
            {scene === 3 && <ExploreScene s={s} t={t} />}
          </div>
          {!reduced && <Cursor x={cursor.x} y={cursor.y} click={cursor.click} />}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-2 sm:grid-cols-4" role="tablist" aria-label="Product walkthrough">
        {SCENES.map((sc, i) => (
          <button
            key={sc.id}
            role="tab"
            aria-selected={scene === i}
            onClick={() => setStart((prev) => ({ at: i, n: prev.n + 1 }))}
            className={cn("rounded-xl border px-3 py-2.5 text-left transition-colors cursor-pointer",
              scene === i ? "border-accent/50 bg-accent-soft" : "border-border bg-surface hover:border-border-strong")}
          >
            <span className={cn("font-mono text-[11px]", scene === i ? "text-accent" : "text-subtle")}>0{i + 1}</span>
            <span className="mt-0.5 block text-[13px] font-medium">{sc.title}</span>
          </button>
        ))}
      </div>
      <p className="mx-auto mt-4 min-h-10 max-w-xl text-center text-sm text-muted" aria-live="polite">
        {SCENES[scene].body}
      </p>
    </div>
  );
}

// ── Pieces ────────────────────────────────────────────────────────
type Reg = (key: string) => (el: HTMLElement | null) => void;

function Chrome() {
  return (
    <div className="absolute inset-x-0 top-0 flex h-9 items-center gap-2 border-b border-border bg-surface px-4">
      <span className="size-2.5 rounded-full bg-[#ff5f57]" />
      <span className="size-2.5 rounded-full bg-[#febc2e]" />
      <span className="size-2.5 rounded-full bg-[#28c840]" />
      <span className="mx-auto rounded-md bg-surface-2 px-12 py-0.5 font-mono text-[11px] text-subtle">code-archaeologist.app</span>
    </div>
  );
}

function Cursor({ x, y, click }: { x: number; y: number; click: number }) {
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

function Btn({ children, primary, className, r }: { children: ReactNode; primary?: boolean; className?: string; r?: (el: HTMLElement | null) => void }) {
  return (
    <span ref={r} className={cn("inline-flex h-8 items-center justify-center gap-1.5 rounded-lg px-3 text-[12px] font-medium whitespace-nowrap",
      primary ? "bg-accent text-accent-fg" : "border border-border bg-surface-2 text-text", className)}>
      {children}
    </span>
  );
}

function ConnectScene({ s, t }: { s: DemoState; t: Reg }) {
  return (
    <div className="relative h-full">
      <p className="text-[17px] font-semibold">Model providers</p>
      <p className="mt-0.5 text-[12px] text-muted">Your own API key is used for every answer.</p>
      <div className="mt-4 space-y-2">
        {PROVIDERS.map((p) => {
          const chosen = p.id === "anthropic";
          const open = chosen && s.expanded;
          return (
            <div key={p.id} className={cn("rounded-xl border bg-surface transition-colors", open ? "border-accent/40" : "border-border")}>
              <div ref={chosen ? t("provider-anthropic") : undefined} className="flex items-center gap-3 px-3 py-2">
                <ProviderMark id={p.id} className="size-7 text-[10px]" />
                <span className="text-[13px] font-medium">{p.name}</span>
                <span className={cn("rounded-md px-1.5 py-0.5 text-[10px] font-medium",
                  chosen && s.connected ? "bg-success-soft text-success" : "bg-surface-2 text-subtle")}>
                  {chosen && s.connected ? (s.model ? "Active" : "Connected") : "Not connected"}
                </span>
              </div>
              {open && (
                <div className="space-y-3 border-t border-border px-3 py-3 animate-fade-up">
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
                              className={cn("flex items-center gap-2 rounded-lg border px-2.5 py-2 font-mono text-[11px]",
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

function IngestScene({ s, t }: { s: DemoState; t: Reg }) {
  return (
    <div className="relative h-full">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[17px] font-semibold">Repositories</p>
          <p className="mt-0.5 text-[12px] text-muted">Your ingested repositories live here.</p>
        </div>
        <Btn primary r={t("new-repo")}><Plus className="size-3.5" /> New repository</Btn>
      </div>

      {!s.ingesting ? (
        <div className="mt-6 grid h-56 place-items-center rounded-xl border border-dashed border-border-strong text-center">
          <div>
            <FolderGit2 className="mx-auto size-6 text-subtle" />
            <p className="mt-2 text-[13px] font-medium">No repositories yet</p>
          </div>
        </div>
      ) : (
        <div className="mx-auto mt-6 w-[420px] rounded-xl border border-border bg-surface p-5 animate-fade-up">
          <p className="flex items-center gap-2 text-[13px] font-semibold">
            {s.stage < STAGES.length - 1 ? <Loader2 className="size-4 animate-spin text-accent" /> : <Check className="size-4 text-success" />}
            {s.stage < STAGES.length - 1 ? "Ingesting acme/storefront" : "acme/storefront is ready"}
            <Lock className="size-3 text-warning" />
          </p>
          <ol className="mt-4 space-y-2.5">
            {STAGES.map((st, i) => (
              <li key={st} className="flex items-center gap-2.5 text-[12px]">
                <span className={cn("grid size-5 place-items-center rounded-full border text-[10px] transition-colors",
                  i < s.stage || s.stage === STAGES.length - 1 ? "border-accent bg-accent text-accent-fg"
                    : i === s.stage ? "border-accent bg-accent-soft text-accent" : "border-border text-subtle")}>
                  {i < s.stage || s.stage === STAGES.length - 1 ? <Check className="size-3" strokeWidth={3} /> : i + 1}
                </span>
                <span className={i <= s.stage ? "text-text" : "text-subtle"}>{st}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {s.dialog && (
        <div className="absolute inset-0 grid place-items-center bg-black/40 backdrop-blur-[2px]">
          <div className="w-[440px] rounded-2xl border border-border bg-surface p-5 shadow-2xl animate-fade-up">
            <p className="text-[14px] font-semibold">Ingest a repository</p>
            <div className="mt-3 grid grid-cols-2 rounded-lg border border-border bg-surface-2 p-0.5 text-[12px]">
              <span className="flex items-center justify-center gap-1.5 rounded-md bg-surface-3 py-1 font-medium"><GitHubIcon className="size-3" /> Your GitHub</span>
              <span className="flex items-center justify-center gap-1.5 py-1 text-muted"><Globe className="size-3" /> Public URL</span>
            </div>
            <div className="mt-3 overflow-hidden rounded-lg border border-border">
              {REPOS.map((r, i) => (
                <span key={r.name} ref={t(`repo-${i}`)}
                      className={cn("flex items-center gap-2.5 border-b border-border px-3 py-2 font-mono text-[12px] last:border-b-0",
                        s.picked === r.name && "bg-accent-soft")}>
                  {r.private ? <Lock className="size-3 text-warning" /> : <Globe className="size-3 text-subtle" />}
                  {r.name}
                </span>
              ))}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <Btn>Cancel</Btn>
              <Btn primary r={t("start")} className={cn(!s.picked && "opacity-50")}>Start ingest</Btn>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function AnswerText({ text }: { text: string }) {
  // Backticked spans render as commit-SHA chips, even mid-typing
  return (
    <>
      {text.split("`").map((part, i) => i % 2
        ? <code key={i} className="rounded bg-surface-3 px-1 font-mono text-[11px] text-accent">{part}</code>
        : <span key={i}>{part}</span>)}
    </>
  );
}

function AskScene({ s, t }: { s: DemoState; t: Reg }) {
  return (
    <div className="relative flex h-full flex-col">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[15px] font-semibold">acme/storefront</span>
        <span className="rounded-md bg-warning-soft px-1.5 py-0.5 text-[10px] text-warning"><Lock className="mr-0.5 inline size-2.5" />Private</span>
        <span className="rounded-md bg-success-soft px-1.5 py-0.5 text-[10px] text-success">Ready</span>
      </div>
      <div className="mt-3 flex gap-4 border-b border-border text-[12px]">
        {["Overview", "Ask", "File timeline", "Hot files", "Pull requests"].map((tab) => (
          <span key={tab} className={cn("-mb-px border-b-2 pb-2", tab === "Ask" ? "border-accent text-text" : "border-transparent text-muted")}>{tab}</span>
        ))}
      </div>

      <div className="flex-1 space-y-3 overflow-hidden pt-4">
        {!s.asked ? (
          <div className="grid h-full place-items-center text-center">
            <div>
              <div className="mx-auto grid size-9 place-items-center rounded-xl bg-accent-soft text-accent"><Sparkles className="size-4" /></div>
              <p className="mt-2 text-[13px] font-medium">Ask about acme/storefront</p>
              <p className="text-[11px] text-muted">Answers come only from its commits, PRs and reviews.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="ml-auto w-fit max-w-[70%] rounded-2xl rounded-br-md bg-accent px-3.5 py-2 text-[12px] text-accent-fg animate-fade-up">{QUESTION}</div>
            <div className="rounded-xl border border-border bg-surface p-4 animate-fade-up">
              <div className="mb-2 flex items-center gap-2 text-[10px] text-subtle">
                <ProviderMark id="anthropic" className="size-4 text-[7px]" />
                <span className="font-mono">{MODELS[1]}</span>
              </div>
              {s.thinking ? (
                <div className="flex gap-1 py-2">
                  {[0, 1, 2].map((i) => <span key={i} className="size-1.5 animate-bounce rounded-full bg-accent" style={{ animationDelay: `${i * 120}ms` }} />)}
                </div>
              ) : (
                <p className="text-[12.5px] leading-relaxed"><AnswerText text={ANSWER.slice(0, s.answer)} /></p>
              )}
              {s.sources > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5 border-t border-border pt-3">
                  {SOURCES.slice(0, s.sources).map((src, i) => (
                    <span key={src} ref={t(`source-${i}`)} className="rounded-md border border-border bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-muted animate-fade-up">{src}</span>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <div className="mt-3 flex items-center gap-2 rounded-xl border border-border bg-surface p-2">
        <span ref={t("ask-input")} className="flex h-8 flex-1 items-center px-2 text-[12.5px]">
          {s.asked ? <span className="text-subtle">Ask a follow-up…</span> : s.question || <span className="text-subtle">Why was the auth module refactored?</span>}
          {!s.asked && s.question && <span className="ml-0.5 h-4 w-px animate-pulse bg-text" />}
        </span>
        <span ref={t("send")} className={cn("grid size-8 place-items-center rounded-lg bg-accent text-accent-fg", !s.question && "opacity-50")}>
          <ArrowUp className="size-3.5" />
        </span>
      </div>
    </div>
  );
}

function ExploreScene({ s, t }: { s: DemoState; t: Reg }) {
  const max = Math.max(...BARS);
  return (
    <div className="h-full">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[15px] font-semibold">acme/storefront</span>
        <span className="rounded-md bg-success-soft px-1.5 py-0.5 text-[10px] text-success">Ready</span>
      </div>
      <div className="mt-3 flex gap-4 border-b border-border text-[12px]">
        {["Overview", "Ask", "File timeline", "Hot files", "Pull requests"].map((tab) => (
          <span key={tab} ref={tab === "Hot files" ? t("tab-hot") : undefined}
                className={cn("-mb-px border-b-2 pb-2 transition-colors",
                  (tab === "Hot files" ? s.hotTab : tab === "Overview" && !s.hotTab) ? "border-accent text-text" : "border-transparent text-muted")}>
            {tab}
          </span>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-4 gap-3">
        {[["Commits", 100], ["Contributors", 7], ["Files touched", 64], ["Linked PRs", 24]].map(([label, n]) => (
          <div key={label} className="rounded-xl border border-border bg-surface p-3">
            <p className="text-[10px] text-muted">{label}</p>
            <p className="mt-1 text-[20px] font-semibold transition-opacity duration-700" style={{ opacity: s.grow ? 1 : 0.15 }}>{n}</p>
          </div>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-5 gap-3">
        <div ref={t("chart")} className="col-span-3 rounded-xl border border-border bg-surface p-3">
          <p className="text-[11px] font-medium">Commit activity</p>
          <div className="mt-3 flex h-36 items-end gap-1.5">
            {BARS.map((b, i) => (
              <span key={i} className="flex-1 origin-bottom rounded-t bg-accent/80 transition-transform duration-700 ease-out"
                    style={{ height: `${(b / max) * 100}%`, transform: `scaleY(${s.grow ? 1 : 0.05})`, transitionDelay: `${i * 45}ms` }} />
            ))}
          </div>
        </div>
        <div className={cn("col-span-2 rounded-xl border bg-surface p-3 transition-colors", s.hotTab ? "border-accent/50" : "border-border")}>
          <p className="text-[11px] font-medium">Hot files</p>
          <ul className="mt-3 space-y-2.5">
            {HOT.map(([f, w], i) => (
              <li key={f} ref={i === 0 ? t("hot-0") : undefined}>
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
    </div>
  );
}
