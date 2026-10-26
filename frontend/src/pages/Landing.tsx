import {
  ArrowRight, BarChart3, FileClock, GitMerge, KeyRound, Network, Search, ShieldCheck, Sparkles, Users,
} from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { GitHubIcon, Logo, ProviderMark, ThemeToggle } from "../components/brand";
import { Button } from "../components/ui";
import { useMe } from "../lib/auth";
import type { ProviderId } from "../lib/types";
import { PROVIDER_NAMES } from "../lib/utils";

const FEATURES: { icon: ReactNode; title: string; body: string }[] = [
  { icon: <Search className="size-4" />, title: "Grounded answers",
    body: "Hybrid dense + BM25 retrieval finds the exact commits, diffs and PR discussions behind a change, and every answer cites them." },
  { icon: <GitMerge className="size-4" />, title: "Pull request context",
    body: "PR descriptions, review comments and linked issues are merged into each commit — that's where the real “why” lives." },
  { icon: <FileClock className="size-4" />, title: "File timelines",
    body: "Trace how any file evolved: the phases it went through, who drove them and the patterns that keep recurring." },
  { icon: <Network className="size-4" />, title: "Hidden coupling",
    body: "Co-change analysis surfaces files that always move together — dependencies static analysis can't see." },
  { icon: <BarChart3 className="size-4" />, title: "Hot spots",
    body: "See where churn concentrates, which commit types dominate and how activity changes week to week." },
  { icon: <Users className="size-4" />, title: "Knowledge map",
    body: "Know who owns what. If a contributor left tomorrow, see exactly which parts of the codebase they carried." },
];

const PROVIDERS: ProviderId[] = ["anthropic", "openai", "gemini", "groq", "openrouter"];

function ProductPreview() {
  return (
    <div className="relative mx-auto mt-16 max-w-4xl">
      <div className="absolute -inset-x-10 -top-10 -bottom-4 rounded-[2rem] bg-accent/10 blur-3xl" aria-hidden />
      <div className="relative overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl">
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <span className="size-2.5 rounded-full bg-[#ff5f57]" />
          <span className="size-2.5 rounded-full bg-[#febc2e]" />
          <span className="size-2.5 rounded-full bg-[#28c840]" />
          <span className="ml-3 font-mono text-xs text-subtle">acme/storefront · Ask</span>
        </div>
        <div className="space-y-4 p-5 sm:p-7">
          <div className="ml-auto w-fit max-w-md rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-sm text-accent-fg">
            Why was the checkout session logic refactored?
          </div>
          <div className="rounded-xl border border-border bg-surface-2 p-4 text-left text-[13px] leading-relaxed sm:p-5">
            <div className="mb-3 flex items-center gap-2 text-xs text-subtle">
              <ProviderMark id="anthropic" className="size-5 text-[8px]" />
              <span className="font-mono">claude-sonnet-5-5</span>
            </div>
            <p>
              The refactor in <code className="rounded bg-surface-3 px-1 font-mono text-accent">3f9c2a1</code> moved
              token refresh out of <code className="rounded bg-surface-3 px-1 font-mono">CheckoutSession</code> after
              two fix commits traced double charges to sessions expiring mid-payment. The PR review asked for the
              retry path to be idempotent, which <code className="rounded bg-surface-3 px-1 font-mono text-accent">a81e0c4</code> added…
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {["3f9c2a1 · j.chen", "a81e0c4 · m.okafor", "PR #412"].map((s) => (
                <span key={s} className="rounded-md border border-border bg-surface px-2 py-1 font-mono text-[11px] text-muted">{s}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function Landing() {
  const { data: me } = useMe();
  const signedIn = !!me;

  return (
    <div className="min-h-full overflow-x-hidden">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-bg/75 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-6 px-4 sm:px-6">
          <Logo />
          <nav className="hidden items-center gap-6 text-[13px] text-muted md:flex">
            <a href="#features" className="hover:text-text">Features</a>
            <a href="#how" className="hover:text-text">How it works</a>
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

      <section className="relative px-4 pt-20 pb-24 sm:px-6 sm:pt-28">
        <div className="grid-bg absolute inset-0 -z-10 opacity-60" aria-hidden />
        <div className="mx-auto max-w-3xl text-center animate-fade-up">
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted">
            <Sparkles className="size-3.5 text-accent" /> Bring your own model — 5 providers supported
          </span>
          <h1 className="mt-6 text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
            Ask <span className="text-accent">why</span> your code is the way it is.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-base text-muted text-balance sm:text-lg">
            Code Archaeologist turns a repository's commits, pull requests and code reviews into a searchable
            memory — and answers with citations, not guesses.
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link to={signedIn ? "/app" : "/register"}>
              <Button size="lg">{signedIn ? "Open your workspace" : "Start for free"} <ArrowRight className="size-4" /></Button>
            </Link>
            <a href="https://github.com/RishabhPR77/code-archaeology-rag" target="_blank" rel="noopener noreferrer">
              <Button size="lg" variant="outline"><GitHubIcon /> View on GitHub</Button>
            </a>
          </div>
        </div>
        <ProductPreview />
      </section>

      <section id="features" className="border-t border-border bg-surface/50 px-4 py-24 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <div className="max-w-2xl">
            <p className="text-[13px] font-semibold text-accent">Features</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Everything Git remembers, finally reachable.</h2>
            <p className="mt-3 text-muted">The knowledge of why a decision was made is buried in history. These tools dig it out.</p>
          </div>
          <div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-border bg-border sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="bg-surface p-6">
                <div className="grid size-9 place-items-center rounded-lg bg-accent-soft text-accent">{f.icon}</div>
                <h3 className="mt-4 text-[15px] font-semibold">{f.title}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="px-4 py-24 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <p className="text-[13px] font-semibold text-accent">How it works</p>
          <h2 className="mt-2 text-3xl font-semibold tracking-tight">Three steps from URL to answers.</h2>
          <ol className="mt-12 grid gap-6 md:grid-cols-3">
            {[
              ["Connect your model", "Add an API key from any supported provider and pick the exact model you want from its live catalogue."],
              ["Ingest a repository", "Paste a public GitHub URL. Commits, diffs, PRs and reviews are chunked, embedded and indexed in minutes."],
              ["Ask anything", "Ask in plain English. Answers cite the commits they come from, with links straight to GitHub."],
            ].map(([title, body], i) => (
              <li key={title} className="rounded-2xl border border-border bg-surface p-6">
                <span className="font-mono text-xs text-subtle">0{i + 1}</span>
                <h3 className="mt-3 text-[15px] font-semibold">{title}</h3>
                <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="providers" className="border-t border-border bg-surface/50 px-4 py-24 sm:px-6">
        <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-2">
          <div>
            <p className="text-[13px] font-semibold text-accent">Your model, your key</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">Use the provider you already trust.</h2>
            <p className="mt-3 text-muted">
              Models are loaded live from each provider's official API with your key, so new releases show up the day
              they ship. Switch providers any time.
            </p>
            <ul className="mt-6 space-y-3 text-[13px] text-muted">
              <li className="flex gap-2.5"><KeyRound className="mt-0.5 size-4 shrink-0 text-accent" /> Keys are encrypted at rest and never sent back to the browser.</li>
              <li className="flex gap-2.5"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-accent" /> Each key is verified against the provider before it's saved.</li>
            </ul>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {PROVIDERS.map((p) => (
              <div key={p} className="flex items-center gap-3 rounded-xl border border-border bg-surface p-4">
                <ProviderMark id={p} />
                <span className="text-sm font-medium">{PROVIDER_NAMES[p]}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-4 py-24 sm:px-6">
        <div className="mx-auto max-w-4xl rounded-3xl border border-border bg-surface px-6 py-14 text-center shadow-card">
          <h2 className="text-3xl font-semibold tracking-tight text-balance">Stop guessing what the last developer meant.</h2>
          <p className="mx-auto mt-3 max-w-lg text-muted">Create an account, connect a model and ingest your first repository in a few minutes.</p>
          <Link to={signedIn ? "/app" : "/register"} className="mt-8 inline-block">
            <Button size="lg">{signedIn ? "Open your workspace" : "Create your account"} <ArrowRight className="size-4" /></Button>
          </Link>
        </div>
      </section>

      <footer className="border-t border-border px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 text-xs text-subtle sm:flex-row">
          <Logo className="text-text" />
          <p>Built with FastAPI, React and retrieval-augmented generation.</p>
        </div>
      </footer>
    </div>
  );
}
