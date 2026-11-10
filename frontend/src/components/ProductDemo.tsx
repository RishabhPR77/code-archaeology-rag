import {
  ArrowUp, Check, CheckCircle2, ChevronDown, Circle, File as FileIcon, GitCommitHorizontal, Globe, LayoutGrid, Loader2,
  Lock, LogOut, Mail, Moon, Plus, Search, Settings, Sparkles, Square, UserRound,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "../lib/utils";
import { GitHubIcon, GoogleIcon, LogoMark, ProviderMark } from "./brand";

/*
 * An animated walkthrough of the app: a fake cursor clicks and types through six screens on a loop,
 * from signing up to signing out, and every change of screen is caused by a click, as it would be in
 * the real app (Create account, Confirm email, Open settings, the logo, a repository card, a tab, the
 * account menu). Labels, tabs and dialogs mirror the real pages.
 * Everything is drawn on a fixed 880x500 canvas that's scaled to fit, so cursor targets are
 * measured in canvas coordinates. The repository and people shown are fictional.
 */

const W = 880;
const H = 500;

const SCENES = [
  { id: "signup", title: "Sign up",
    body: "Create an account with GitHub, Google or an email address. Email sign-ups confirm a 6-digit code first." },
  { id: "connect", title: "Connect your model",
    body: "Paste an API key from Anthropic, OpenAI, Gemini, Groq or OpenRouter, then pick any model from its live list." },
  { id: "ingest", title: "Add a repository",
    body: "Pick one of your GitHub repositories or paste a public URL, and take its latest commits or any range of its history." },
  { id: "ask", title: "Ask why",
    body: "Ask in plain English. The answer streams in and cites the exact commits and pull requests it comes from." },
  { id: "suspects", title: "Find what broke",
    body: "Describe a bug or paste a stack trace. The three most likely culprit commits come back, each with the reasons it was flagged." },
  { id: "explore", title: "Explore the history",
    body: "See busy weeks and hot spots, or search for any file and trace how it changed." },
] as const;

// The real repository page's tabs, in order
const TABS = ["Overview", "Ask", "File timeline", "Bug origins", "Who broke it?", "Hot files", "Co-change", "Authors",
  "Pull requests", "Commits"] as const;
const PROVIDERS = [
  { id: "anthropic", name: "Anthropic" }, { id: "openai", name: "OpenAI" },
  { id: "gemini", name: "Google Gemini" }, { id: "groq", name: "Groq" },
  { id: "openrouter", name: "OpenRouter" },
] as const;
const MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"];
const REPOS = [
  { name: "acme/storefront", private: true, note: "Checkout and payments" },
  { name: "acme/payments-api", private: true, note: "Payment service" },
  { name: "acme/docs", private: false, note: "Developer docs" },
];
const STAGES = ["Cloning repository", "Reading commits", "Fetching pull requests", "Embedding history", "Ready"];
const QUESTION = "Why was the checkout session logic refactored?";
const ANSWER = "The refactor in `3f9c2a1` moved token refresh out of `CheckoutSession` after two fix commits " +
  "traced double charges to sessions expiring mid-payment. The review on PR #412 asked for an idempotent " +
  "retry path, added in `a81e0c4`.";
const SOURCES = ["3f9c2a1 · j.chen", "a81e0c4 · m.okafor", "PR #412"];
const REPORT = "Customers are charged twice when a payment is retried after the session expires.\n" +
  "  at retryPayment (payments/retry.ts:42)";
const SUSPECTS = [
  { sha: "7d2e4b1", type: "Feature", msg: "Retry failed payments automatically", score: 84,
    reasons: ["Changed code your report mentions: retryPayment", "Changed payments/retry.ts, which your report names"] },
  { sha: "0c1d9fa", type: "Feature", msg: "Add checkout session", score: 71,
    reasons: ["Already traced as the cause of 2 earlier bug fixes", "A large change (1,240 lines)"] },
  { sha: "9a1f3c7", type: "Refactor", msg: "Share session tokens between tabs", score: 58,
    reasons: ["Partly matches your description", "Changed checkout/session.ts"] },
] as const;
const ACTIVITY = [3, 5, 4, 8, 6, 11, 7, 9, 14, 10, 6, 12, 9, 13];
const HOT = [["checkout/session.ts", 100], ["payments/retry.ts", 74], ["api/orders.ts", 58], ["checkout/cart.ts", 41]] as const;
const TRACE_FILES = [
  { path: "checkout/session.ts", changes: 31 }, { path: "payments/retry.ts", changes: 22 },
  { path: "checkout/cart.ts", changes: 18 }, { path: "api/orders.ts", changes: 14 },
  { path: "checkout/session.test.ts", changes: 9 },
];
const PHASES = [
  ["2023", "Built as one class handling the cart, tokens and payment.", "0c1d9fa"],
  ["2024", "Two double-charge fixes, then token refresh moved out.", "3f9c2a1"],
  ["2025", "A retry that is safe to repeat, asked for on PR #412.", "a81e0c4"],
] as const;
const TRACE_COMMITS = [
  ["0c1d9fa", "Add checkout session"], ["5e2b8c0", "Fix double charge on retry"],
  ["3f9c2a1", "Move token refresh out"], ["a81e0c4", "Add idempotent retry"],
] as const;

interface DemoState {
  name: string; email: string; password: string; creating: boolean; verify: boolean; code: string; confirming: boolean;
  onSettings: boolean; expanded: boolean; keyText: string; saving: boolean; connected: boolean; model: string | null; toast: string | null;
  dialog: boolean; picked: string | null; range: boolean; ingesting: boolean; stage: number;
  askTab: boolean; question: string; asked: boolean; found: boolean; answer: number; sources: number;
  report: string; finding: boolean; suspects: number;
  grow: boolean; timelineTab: boolean; pickerOpen: boolean; pickerText: string; traced: boolean; menu: boolean;
}

const START: DemoState = {
  name: "", email: "", password: "", creating: false, verify: false, code: "", confirming: false,
  onSettings: false, expanded: false, keyText: "", saving: false, connected: false, model: null, toast: null,
  dialog: false, picked: null, range: false, ingesting: false, stage: -1,
  askTab: false, question: "", asked: false, found: false, answer: 0, sources: 0,
  report: "", finding: false, suspects: 0,
  grow: false, timelineTab: false, pickerOpen: false, pickerText: "", traced: false, menu: false,
};

// What each scene looks like when it has finished — used for reduced motion
const FINAL: Record<number, Partial<DemoState>> = {
  0: { name: "Jo Chen", email: "jo@acme.dev", password: "••••••••••" },
  1: { onSettings: true, expanded: true, keyText: "sk-ant-••••••••••••••••", connected: true, model: MODELS[1] },
  2: { picked: REPOS[0].name, ingesting: true, stage: STAGES.length - 1 },
  3: { askTab: true, question: QUESTION, asked: true, found: true, answer: ANSWER.length, sources: SOURCES.length },
  4: { report: REPORT, suspects: SUSPECTS.length },
  5: { grow: true, timelineTab: true, pickerText: TRACE_FILES[0].path, traced: true },
};

class Cancelled extends Error {}

export function ProductDemo() {
  const [scene, setScene] = useState(0);
  const [s, setS] = useState<DemoState>(START);
  const [cursor, setCursor] = useState({ x: W / 2, y: H - 60, click: 0 });
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
    const press = async (key: string, ms = 750) => { await move(key, ms); await click(); };
    const type = async (text: string, set: (v: string) => void, speed = 45) => {
      for (let i = 1; i <= text.length; i++) {
        set(text.slice(0, i));
        await sleep(speed);
      }
    };

    // Each script ends with the click that opens the next screen
    const scripts = [
      async () => {  // Sign up, confirm the emailed code, and land on the dashboard
        await press("signup-name");
        await type("Jo Chen", (name) => patch({ name }), 55);
        await press("signup-email", 500);
        await type("jo@acme.dev", (email) => patch({ email }), 45);
        await press("signup-password", 500);
        await type("••••••••••", (password) => patch({ password }), 40);
        await press("create", 600);
        patch({ creating: true });
        await sleep(700);
        patch({ creating: false, verify: true });
        await press("code", 700);
        await type("482913", (code) => patch({ code }), 110);
        await press("confirm", 550);
        patch({ confirming: true });
        await sleep(650);
      },
      async () => {  // The dashboard's checklist opens Settings: connect a model, then the logo goes back
        await sleep(500);
        await press("open-settings", 800);
        patch({ onSettings: true });
        await press("provider-anthropic");
        patch({ expanded: true });
        await press("key-input");
        await type("sk-ant-••••••••••••••••", (keyText) => patch({ keyText }), 40);
        await press("verify");
        patch({ saving: true });
        await sleep(900);
        patch({ saving: false, connected: true, toast: "Anthropic connected · models loaded" });
        await press("model-1");
        patch({ model: MODELS[1] });
        await sleep(1300);
        await press("logo", 800);
      },
      async () => {  // Dashboard: ingest a range of a repository, then open it
        await press("new-repo");
        patch({ dialog: true });
        await press("repo-0", 850);
        patch({ picked: REPOS[0].name });
        await press("which-range", 650);
        patch({ range: true });
        await sleep(1100);
        await press("start");
        patch({ dialog: false, ingesting: true, stage: 0 });
        for (let i = 1; i < STAGES.length; i++) {
          await sleep(650);
          patch({ stage: i });
        }
        await sleep(900);
        await press("repo-card", 800);
      },
      async () => {  // The repository opens on Overview; the Ask tab, a question, then Who broke it?
        await sleep(500);
        await press("tab-Ask");
        patch({ askTab: true });
        await press("ask-input");
        await type(QUESTION, (question) => patch({ question }), 38);
        await press("send", 500);
        patch({ asked: true });
        await sleep(800);
        patch({ found: true });
        await sleep(700);
        await move("stop", 500);
        for (let i = 4; i <= ANSWER.length; i += 4) {
          patch({ answer: i });
          await sleep(24);
        }
        patch({ answer: ANSWER.length });
        for (let i = 1; i <= SOURCES.length; i++) {
          await sleep(220);
          patch({ sources: i });
        }
        await move("source-0", 700);
        await sleep(1100);
        await press("tab-Who broke it?", 800);
      },
      async () => {  // Who broke it?: a bug report, three suspects, then back to Overview
        await press("report");
        await type(REPORT, (report) => patch({ report }), 22);
        await press("find", 550);
        patch({ finding: true });
        await sleep(900);
        patch({ finding: false });
        for (let i = 1; i <= SUSPECTS.length; i++) {
          patch({ suspects: i });
          await sleep(320);
        }
        await move("suspect-0", 800);
        await sleep(1700);
        await press("tab-Overview", 800);
      },
      async () => {  // Overview and a file's timeline, then the account menu back to Settings
        patch({ grow: true });
        await move("chart", 900);
        await sleep(700);
        await press("tab-File timeline");
        patch({ timelineTab: true });
        await press("picker", 600);
        patch({ pickerOpen: true });
        await sleep(500);
        await type("sess", (pickerText) => patch({ pickerText }), 120);
        await press("pick-0", 650);
        patch({ pickerOpen: false, pickerText: TRACE_FILES[0].path, traced: true });
        await move("trace-commits", 800);
        await sleep(1600);
        await press("avatar", 800);
        patch({ menu: true });
        await press("menu-signout", 650);
      },
    ];

    (async () => {
      let i = startAt;
      try {
        for (;;) {
          alive();
          setScene(i);
          setS(START);
          await sleep(350);
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
          <Chrome scene={scene} s={s} />
          {scene === 0 ? <SignupScene s={s} t={t} /> : (
            <>
              <AppBar scene={scene} s={s} t={t} />
              <div className="absolute inset-x-0 top-20 bottom-0 px-7 pt-4 pb-4">
                {scene === 1 && <ConnectScene s={s} t={t} />}
                {scene === 2 && <IngestScene s={s} t={t} />}
                {scene === 3 && <AskScene s={s} t={t} />}
                {scene === 4 && <SuspectsScene s={s} t={t} />}
                {scene === 5 && <ExploreScene s={s} t={t} />}
              </div>
            </>
          )}
          {scene === 2 && s.dialog && <IngestDialog s={s} t={t} />}
          {!reduced && <Cursor x={cursor.x} y={cursor.y} click={cursor.click} />}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6" role="tablist" aria-label="Product walkthrough">
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

function pageUrl(scene: number, s: DemoState): string {
  if (scene === 0) return s.verify ? "/verify-email" : "/register";
  if (scene === 1) return s.onSettings ? "/app/settings" : "/app";
  if (scene === 2) return "/app";
  if (scene === 3) return s.askTab ? "/app/repos/storefront/ask" : "/app/repos/storefront";
  if (scene === 4) return "/app/repos/storefront/suspects";
  return s.timelineTab ? "/app/repos/storefront/timeline" : "/app/repos/storefront";
}

function Chrome({ scene, s }: { scene: number; s: DemoState }) {
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
function AppBar({ scene, s, t }: { scene: number; s: DemoState; t: Reg }) {
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

/** The repository header and its ten tabs, each one a cursor target. */
function RepoTitle({ active, t }: { active: string; t: Reg }) {
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

function Field({ label, value, placeholder, r, focus }: {
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
function SignupScene({ s, t }: { s: DemoState; t: Reg }) {
  const typing = s.password ? "password" : s.email ? "email" : s.name ? "name" : "";
  return (
    <div className="absolute inset-x-0 top-9 bottom-0 flex bg-surface">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between px-6 py-3">
          <span className="flex items-center gap-2"><LogoMark className="size-6" /><span className="text-[13px] font-semibold">Code Archaeologist</span></span>
          <Moon className="size-3.5 text-muted" />
        </div>
        <div className="flex flex-1 items-center justify-center px-6">
          {!s.verify ? (
            <div className="w-[300px] animate-fade-up">
              <p className="text-[19px] font-bold tracking-tight">Create your account</p>
              <p className="mt-0.5 text-[11.5px] text-muted">Bring your own model key. Start digging in minutes.</p>
              <div className="mt-3.5 grid grid-cols-2 gap-2">
                <Btn className="w-full"><GoogleIcon className="size-3.5" /> Google</Btn>
                <Btn className="w-full"><GitHubIcon className="size-3.5" /> GitHub</Btn>
              </div>
              <p className="my-2.5 flex items-center gap-2 text-[10.5px] text-subtle">
                <span className="h-px flex-1 bg-border" /> or with email <span className="h-px flex-1 bg-border" />
              </p>
              <div className="space-y-2">
                <Field label="Name" value={s.name} placeholder="Ada Lovelace" r={t("signup-name")} focus={typing === "name"} />
                <Field label="Email" value={s.email} placeholder="you@company.com" r={t("signup-email")} focus={typing === "email"} />
                <Field label="Password" value={s.password} placeholder="At least 8 characters" r={t("signup-password")} focus={typing === "password"} />
              </div>
              <span ref={t("create")} className="mt-3 block">
                <Btn primary className="h-9 w-full">{s.creating && <Loader2 className="size-3.5 animate-spin" />} Create account</Btn>
              </span>
              <p className="mt-2.5 text-center text-[10.5px] text-muted">Already have an account? <span className="font-medium text-accent">Sign in</span></p>
            </div>
          ) : (
            <div className="w-[300px] text-center animate-fade-up">
              <span className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><Mail className="size-5" /></span>
              <p className="mt-3 text-[19px] font-semibold tracking-tight">Check your email</p>
              <p className="mt-1 text-[11.5px] text-muted">We sent a 6-digit code to <span className="font-medium text-text">jo@acme.dev</span>.</p>
              <span ref={t("code")} className={cn("mt-4 flex h-11 items-center justify-center rounded-lg border font-mono text-[20px] tracking-[0.4em]",
                s.code ? "border-accent ring-2 ring-accent-soft" : "border-border text-subtle")}>
                {s.code || "000000"}
              </span>
              <span ref={t("confirm")} className="mt-3 block">
                <Btn primary className={cn("h-9 w-full", s.code.length < 6 && "opacity-50")}>
                  {s.confirming && <Loader2 className="size-3.5 animate-spin" />} Confirm email
                </Btn>
              </span>
              <p className="mt-2.5 text-[10.5px] text-subtle">Resend code in 58s</p>
            </div>
          )}
        </div>
      </div>
      <div className="flex w-[40%] items-center justify-center border-l border-border bg-accent-soft p-6">
        <div className="w-full">
          <p className="text-[15px] font-bold tracking-tight">Ask a repository why its code was written.</p>
          <div className="mt-3 rounded-xl border border-border bg-surface p-3 shadow-card">
            <p className="ml-auto w-fit rounded-xl rounded-br-sm bg-accent px-2.5 py-1 text-[10.5px] text-accent-fg">Why was the checkout session logic refactored?</p>
            <p className="mt-2 text-[10.5px] leading-relaxed">Token refresh moved out of <code className="rounded bg-surface-3 px-1 font-mono text-[9.5px]">CheckoutSession</code> after two fixes traced double charges to sessions expiring mid-payment.</p>
            <p className="mt-2 border-t border-border pt-1.5 font-mono text-[9.5px] text-accent">3f9c2a1 · a81e0c4 · PR #412</p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** A brand-new account's dashboard: the "Get set up" checklist, whose first step opens Settings. */
function SetupChecklist({ t, connected }: { t?: Reg; connected: boolean }) {
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

function ConnectScene({ s, t }: { s: DemoState; t: Reg }) {
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

function IngestScene({ s, t }: { s: DemoState; t: Reg }) {
  const done = s.stage === STAGES.length - 1;
  return (
    <div className="h-full">
      <p className="text-[12px] text-muted">Welcome back, Jo</p>
      <p className="text-[17px] font-semibold">Your repositories</p>
      {!s.ingesting && <div className="mt-3"><SetupChecklist connected /></div>}

      <div className="mt-3 grid grid-cols-3 gap-3">
        {s.ingesting && (
          <div ref={t("repo-card")} className="rounded-xl border border-border bg-surface p-3.5 shadow-card animate-fade-up">
            <div className="flex items-start gap-2.5">
              <span className="grid size-9 place-items-center rounded-lg bg-accent text-[13px] font-bold text-accent-fg">A</span>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] text-subtle">acme</p>
                <p className="flex items-center gap-1 text-[13px] font-semibold">storefront <Lock className="size-3 text-warning" /></p>
              </div>
              <span className={cn("rounded-md px-1.5 py-0.5 text-[10px]", done ? "bg-success-soft text-success" : "bg-warning-soft text-warning")}>
                {done ? "Ready" : "Ingesting"}
              </span>
            </div>
            <div className="mt-3 flex items-center justify-between text-[10px]">
              <span className={done ? "text-muted" : "text-warning"}>{done ? "Ingested just now" : STAGES[s.stage]}</span>
              {!done && <span className="text-subtle">step {s.stage + 1} of {STAGES.length - 1}</span>}
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-3">
              <div className={cn("h-full rounded-full transition-[width] duration-500", done ? "bg-success" : "progress-sweep bg-warning")}
                   style={{ width: `${((s.stage + 1) / STAGES.length) * 100}%` }} />
            </div>
            <p className="mt-3 border-t border-border pt-2 text-[10px] text-subtle">{done ? "commits 1–300 · 86 PRs" : "Reading history…"}</p>
          </div>
        )}
        <div className="flex h-40 flex-col items-center justify-center rounded-xl border-2 border-dashed border-border-strong text-center">
          <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent"><Plus className="size-4" /></span>
          <p className="mt-2 text-[12px] font-semibold">Add a repository</p>
          <p className="text-[10px] text-subtle">Paste a GitHub URL or pick one of yours</p>
        </div>
      </div>
    </div>
  );
}

/** The real "Ingest a repository" dialog, over the whole page. */
function IngestDialog({ s, t }: { s: DemoState; t: Reg }) {
  return (
    <div className="absolute inset-0 z-30 grid place-items-center bg-black/40 backdrop-blur-[2px]">
      <div className="w-[460px] rounded-2xl border border-border bg-surface px-5 py-4 shadow-2xl animate-fade-up">
        <p className="text-[14px] font-semibold">Ingest a repository</p>
        <p className="text-[11px] text-muted">Its commit history, pull requests and reviews become searchable.</p>
        <div className="mt-2.5 grid grid-cols-2 rounded-lg border border-border bg-surface-2 p-0.5 text-[12px]">
          <span className="flex items-center justify-center gap-1.5 rounded-md bg-surface-3 py-1 font-medium"><GitHubIcon className="size-3" /> Your GitHub</span>
          <span className="flex items-center justify-center gap-1.5 py-1 text-muted"><Globe className="size-3" /> Public URL</span>
        </div>
        <span className="mt-2 flex h-7 items-center gap-2 rounded-lg border border-border px-2.5 text-[11px] text-subtle">
          <Search className="size-3.5" /> Search your repositories
        </span>
        <div className="mt-2 overflow-hidden rounded-lg border border-border">
          {REPOS.map((r, i) => (
            <span key={r.name} ref={t(`repo-${i}`)}
                  className={cn("flex items-center gap-2.5 border-b border-border px-3 py-1 last:border-b-0",
                    s.picked === r.name && "bg-accent-soft")}>
              {r.private ? <Lock className="size-3 text-warning" /> : <Globe className="size-3 text-subtle" />}
              <span className="font-mono text-[11.5px]">{r.name}</span>
              <span className="ml-auto text-[10px] text-subtle">{r.note}</span>
            </span>
          ))}
        </div>

        <div className="mt-2.5 flex items-center justify-between">
          <span className="text-[12px] font-medium">Commits to analyse</span>
          <span className="text-[10px] text-subtle">On the default branch</span>
        </div>
        <div className="mt-1.5 inline-flex rounded-lg border border-border bg-surface-2 p-0.5 text-[11px]">
          <span className={cn("rounded-md px-2.5 py-0.5", !s.range && "bg-surface-3 font-medium")}>The latest</span>
          <span ref={t("which-range")} className={cn("rounded-md px-2.5 py-0.5", s.range && "bg-surface-3 font-medium")}>A range</span>
        </div>
        {!s.range ? (
          <div className="mt-2 flex gap-1.5 text-[11px]">
            {[50, 100, 200, 300, 500].map((n) => (
              <span key={n} className={cn("rounded-md border px-2.5 py-0.5", n === 300 ? "border-accent bg-accent-soft font-medium" : "border-border")}>{n}</span>
            ))}
          </div>
        ) : (
          <div className="mt-2 space-y-1.5 rounded-xl border border-border bg-surface-2/50 px-3 py-2 animate-fade-up">
            <div className="relative h-4">
              <div className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-surface-3" />
              <div className="absolute top-1/2 left-[2%] h-1.5 w-[22%] -translate-y-1/2 rounded-full bg-accent" />
              <span className="absolute top-1/2 left-[2%] size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-surface" />
              <span className="absolute top-1/2 left-[24%] size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-surface" />
            </div>
            <div className="flex items-center justify-between text-[10px] text-subtle"><span>#1 newest</span><span>#1,342 oldest</span></div>
            <div className="flex items-center gap-1.5 text-[11px]">
              <span className="text-muted">Commits</span>
              <span className="rounded-md border border-border bg-surface px-2 font-mono">1</span>
              <span className="text-muted">to</span>
              <span className="rounded-md border border-border bg-surface px-2 font-mono">300</span>
              <span className="ml-auto rounded-md bg-accent-soft px-1.5 text-[10px] font-medium text-accent">300 commits</span>
            </div>
            <div className="space-y-0.5 border-t border-border pt-1.5 text-[10px]">
              <p className="flex items-center gap-1.5 truncate"><GitCommitHorizontal className="size-3 text-accent" /><span className="text-subtle">Starts at</span>
                <span className="font-mono text-accent">#1</span> · 4 Nov 2026 · Add idempotent retry</p>
              <p className="flex items-center gap-1.5 truncate"><GitCommitHorizontal className="size-3 text-accent" /><span className="text-subtle">Ends at</span>
                <span className="font-mono text-accent">#300</span> · 12 Mar 2025 · Split checkout into steps</p>
            </div>
          </div>
        )}
        <div className="mt-3 flex justify-end gap-2">
          <Btn>Cancel</Btn>
          <Btn primary r={t("start")} className={cn(!s.picked && "opacity-50")}>Start ingest</Btn>
        </div>
      </div>
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

function OverviewBody({ s, t }: { s: DemoState; t?: Reg }) {
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

function AskScene({ s, t }: { s: DemoState; t: Reg }) {
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

function SuspectsScene({ s, t }: { s: DemoState; t: Reg }) {
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

function Match({ text, q }: { text: string; q: string }) {
  const i = q ? text.indexOf(q) : -1;
  if (i < 0) return <>{text}</>;
  return <>{text.slice(0, i)}<b className="text-accent">{text.slice(i, i + q.length)}</b>{text.slice(i + q.length)}</>;
}

function ExploreScene({ s, t }: { s: DemoState; t: Reg }) {
  const q = s.pickerOpen ? s.pickerText.toLowerCase() : "";
  return (
    <div className="h-full">
      <RepoTitle active={s.timelineTab ? "File timeline" : "Overview"} t={t} />

      {!s.timelineTab ? <OverviewBody s={s} t={t} /> : (
        <div className="relative mt-3 animate-fade-up">
          <div className="flex gap-2">
            <span ref={t("picker")}
                  className={cn("flex h-9 flex-1 items-center gap-2 rounded-lg border bg-surface px-3 font-mono text-[12px] transition-colors",
                    s.pickerOpen ? "border-accent" : "border-border")}>
              <Search className="size-3.5 shrink-0 text-subtle" />
              {s.pickerText || <span className="font-sans text-subtle">Search files and folders, e.g. main.py</span>}
              {s.pickerOpen && <span className="ml-px h-4 w-px animate-pulse bg-text" />}
            </span>
            <Btn primary>Trace evolution</Btn>
          </div>

          {s.pickerOpen && (
            <div className="absolute inset-x-0 top-11 z-10 rounded-xl border border-border bg-surface py-1 shadow-card animate-fade-up">
              <p className="px-3 pt-1 pb-1.5 text-[10px] font-semibold text-subtle">{q ? "Matching files and folders" : "Most changed files"}</p>
              {TRACE_FILES.filter((f) => f.path.includes(q)).map((f, i) => (
                <span key={f.path} ref={i === 0 ? t("pick-0") : undefined}
                      className={cn("flex items-center gap-2 px-3 py-1.5", i === 0 && q && "bg-accent-soft")}>
                  <FileIcon className="size-3.5 shrink-0 text-subtle" />
                  <span className="flex-1 font-mono text-[11.5px]"><Match text={f.path} q={q} /></span>
                  <span className="text-[10px] text-subtle">{f.changes} changes</span>
                </span>
              ))}
            </div>
          )}

          {s.traced && (
            <div className="mt-3 grid grid-cols-5 gap-3 animate-fade-up">
              <div className="col-span-3 rounded-xl border border-border bg-surface p-3.5">
                <p className="text-[11px] font-medium">Evolution summary <span className="font-mono text-subtle">· {TRACE_FILES[0].path}</span></p>
                <ol className="mt-3 space-y-2.5">
                  {PHASES.map(([year, text, sha]) => (
                    <li key={sha} className="flex gap-2.5 text-[11.5px] leading-snug">
                      <span className="font-semibold">{year}</span>
                      <span className="text-muted">{text} <code className="font-mono text-[10.5px] text-accent">{sha}</code></span>
                    </li>
                  ))}
                </ol>
              </div>
              <div ref={t("trace-commits")} className="col-span-2 rounded-xl border border-border bg-surface p-3.5">
                <p className="text-[11px] font-medium">{TRACE_COMMITS.length} commits</p>
                <ul className="mt-3 space-y-2.5">
                  {TRACE_COMMITS.map(([sha, msg]) => (
                    <li key={sha} className="flex gap-2 text-[11px]">
                      <span className="font-mono font-semibold text-accent">{sha}</span>
                      <span className="truncate text-muted">{msg}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
