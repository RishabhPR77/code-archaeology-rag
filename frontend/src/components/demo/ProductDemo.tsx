import { useCallback, useEffect, useRef, useState } from "react";
import { cn } from "../../lib/utils";
import { AskScene } from "./AskScene";
import { ConnectScene } from "./ConnectScene";
import { ExploreScene } from "./ExploreScene";
import { IngestDialog, IngestScene } from "./IngestScene";
import { SignupScene } from "./SignupScene";
import { SuspectsScene } from "./SuspectsScene";
import type { DemoState } from "./data";
import { ANSWER, Cancelled, FINAL, H, MODELS, QUESTION, REPORT, REPOS, SCENES, SOURCES, STAGES, START, SUSPECTS, TRACE_FILES, W } from "./data";
import { AppBar, Chrome, Cursor } from "./frame";

/*
 * An animated walkthrough of the app: a fake cursor clicks and types through six screens on a loop,
 * from signing up to signing out, and every change of screen is caused by a click, as it would be in
 * the real app (Create account, Confirm email, Open settings, the logo, a repository card, a tab, the
 * account menu). Labels, tabs and dialogs mirror the real pages.
 * Everything is drawn on a fixed 880x500 canvas that's scaled to fit, so cursor targets are
 * measured in canvas coordinates. The repository and people shown are fictional.
 */
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
        await type("••••••••••••", (password) => patch({ password }), 40);
        await press("signup-confirm", 450);   // the real form asks for the password twice
        await type("••••••••••••", (confirm) => patch({ confirm }), 35);
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
    // A counter, not a DOM node: bumping its latest value is what cancels the script started above
    const counter = epoch;
    return () => { counter.current++; };
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
