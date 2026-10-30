import {
  ArrowRight, BarChart3, FileClock, GitMerge, KeyRound, Network, PlayCircle, Search, ShieldCheck, Users,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { AnswerPreview } from "../components/AnswerPreview";
import { Logo, ProviderMark, ThemeToggle } from "../components/brand";
import { ProductDemo } from "../components/ProductDemo";
import { Button } from "../components/ui";
import { useMe } from "../lib/auth";
import type { ProviderId } from "../lib/types";
import { PROVIDER_NAMES } from "../lib/utils";

const FEATURES: { icon: ReactNode; title: string; body: string }[] = [
  { icon: <Search className="size-4" />, title: "Answers with sources",
    body: "Every answer links to the exact commits, diffs and pull requests it came from." },
  { icon: <GitMerge className="size-4" />, title: "Pull request context",
    body: "PR descriptions, review comments and linked issues are read alongside each commit." },
  { icon: <FileClock className="size-4" />, title: "File timelines",
    body: "See how any file changed over time and who drove each change." },
  { icon: <Network className="size-4" />, title: "Hidden coupling",
    body: "Find files that always change together, even when no import connects them." },
  { icon: <BarChart3 className="size-4" />, title: "Hot spots",
    body: "See where changes concentrate and how activity moves week to week." },
  { icon: <Users className="size-4" />, title: "Knowledge map",
    body: "See who owns what, and which parts of the code depend on one person." },
];

const STEPS = [
  ["Add your API key", "Paste a key from any supported provider and pick a model from its live list."],
  ["Connect a repository", "Choose one of your GitHub repositories or paste a public URL."],
  ["Ask your question", "Ask in plain English and get an answer with links to the sources."],
];

const PROVIDERS: ProviderId[] = ["anthropic", "openai", "gemini", "groq", "openrouter"];

export function Landing() {
  const { data: me } = useMe();
  const signedIn = !!me;

  return (
    <div className="min-h-full overflow-x-hidden">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/90 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:gap-6 sm:px-6">
          <Logo />
          <nav className="hidden items-center gap-6 text-[13px] font-medium text-muted md:ml-4 md:flex">
            <a href="#demo" className="hover:text-text">Demo</a>
            <a href="#features" className="hover:text-text">Features</a>
            <a href="#providers" className="hover:text-text">Providers</a>
          </nav>
          <div className="flex-1" />
          <ThemeToggle />
          {signedIn ? (
            <Link to="/app"><Button size="sm">Open app <ArrowRight className="size-3.5" /></Button></Link>
          ) : (
            <>
              <Link to="/login" className="hidden text-[13px] font-medium text-muted hover:text-text sm:block">Sign in</Link>
              <Link to="/register"><Button size="sm">Get started</Button></Link>
            </>
          )}
        </div>
      </header>

      <section className="bg-surface px-4 pt-12 pb-16 sm:px-6 lg:pt-20 lg:pb-24">
        <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-2 lg:gap-14">
          <div className="animate-fade-up">
            <h1 className="text-4xl leading-[1.1] font-extrabold tracking-tight text-balance sm:text-5xl lg:text-[3.5rem]">
              Find out why any code was written.
            </h1>
            <p className="mt-5 max-w-xl text-lg leading-relaxed text-muted">
              Connect a GitHub repository and ask about it in plain English. Answers come from its commits,
              pull requests and code reviews, with links to the sources.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link to={signedIn ? "/app" : "/register"}>
                <Button size="lg" className="w-full sm:w-auto">{signedIn ? "Open your workspace" : "Start for free"} <ArrowRight className="size-4" /></Button>
              </Link>
              <a href="#demo">
                <Button size="lg" variant="outline" className="w-full sm:w-auto"><PlayCircle className="size-4" /> Watch the demo</Button>
              </a>
            </div>
            <p className="mt-6 text-[13px] text-subtle">
              Uses your own API key from Anthropic, OpenAI, Gemini, Groq or OpenRouter.
            </p>
          </div>
          <div className="min-w-0 rounded-3xl bg-accent-soft p-3 sm:p-6">
            <AnswerPreview />
          </div>
        </div>
      </section>

      <section id="demo" className="scroll-mt-16 border-t border-border px-4 py-16 sm:px-6 lg:py-20">
        <div className="mx-auto max-w-6xl">
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-[13px] font-semibold text-accent">Demo</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight">See how it works.</h2>
          </div>
          <div className="mt-10"><ProductDemo /></div>
        </div>
      </section>

      <section id="features" className="scroll-mt-16 border-t border-border bg-surface px-4 py-16 sm:px-6 lg:py-20">
        <div className="mx-auto max-w-6xl">
          <p className="text-[13px] font-semibold text-accent">Features</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">More than a chatbot for your repo.</h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="rounded-xl border border-border bg-surface p-6 transition-colors hover:border-accent/50">
                <div className="grid size-9 place-items-center rounded-lg bg-accent-soft text-accent">{f.icon}</div>
                <h3 className="mt-4 text-[15px] font-bold">{f.title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="border-t border-border px-4 py-16 sm:px-6 lg:py-20">
        <div className="mx-auto max-w-6xl">
          <p className="text-[13px] font-semibold text-accent">How it works</p>
          <h2 className="mt-2 text-3xl font-bold tracking-tight">Three steps to your first answer.</h2>
          <ol className="mt-10 grid gap-8 md:grid-cols-3">
            {STEPS.map(([title, body], i) => (
              <li key={title}>
                <span className="grid size-9 place-items-center rounded-full bg-accent text-sm font-bold text-accent-fg">{i + 1}</span>
                <h3 className="mt-4 text-[15px] font-bold">{title}</h3>
                <p className="mt-1.5 text-sm leading-relaxed text-muted">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="providers" className="scroll-mt-16 border-t border-border bg-surface px-4 py-16 sm:px-6 lg:py-20">
        <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-2 lg:gap-14">
          <div>
            <p className="text-[13px] font-semibold text-accent">Your key</p>
            <h2 className="mt-2 text-3xl font-bold tracking-tight">Use the model you already pay for.</h2>
            <p className="mt-3 leading-relaxed text-muted">
              Models are loaded live from each provider with your key, so new releases show up the day they ship.
            </p>
            <ul className="mt-6 space-y-3 text-sm text-muted">
              <li className="flex gap-2.5"><KeyRound className="mt-0.5 size-4 shrink-0 text-accent" /> Keys are encrypted at rest and never sent back to the browser.</li>
              <li className="flex gap-2.5"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" /> Each key is verified with the provider before it's saved.</li>
            </ul>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {PROVIDERS.map((p) => (
              <div key={p} className="flex items-center gap-3 rounded-xl border border-border bg-surface p-4 sm:last:col-span-2">
                <ProviderMark id={p} />
                <span className="text-sm font-semibold">{PROVIDER_NAMES[p]}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 py-16 sm:px-6 lg:py-20">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 rounded-3xl bg-[#065f46] px-6 py-10 text-white sm:px-10 sm:py-12 md:flex-row md:items-center">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-balance">Ask your first question in a few minutes.</h2>
            <p className="mt-2 text-white/80">Create an account, add a key and connect a repository.</p>
          </div>
          <Link to={signedIn ? "/app" : "/register"} className="shrink-0">
            <button className="inline-flex h-12 cursor-pointer items-center gap-2 rounded-lg bg-white px-6 text-[15px] font-semibold text-[#065f46] transition-colors hover:bg-white/90">
              {signedIn ? "Open your workspace" : "Create your account"} <ArrowRight className="size-4" />
            </button>
          </Link>
        </div>
      </section>

      <footer className="border-t border-border px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 text-xs text-subtle sm:flex-row">
          <Logo className="text-text" />
          <p className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            <span>Built with FastAPI, React and retrieval-augmented generation.</span>
            <Link to="/privacy" className="hover:text-text">Privacy</Link>
            <Link to="/terms" className="hover:text-text">Terms</Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
