

export const W = 880;
export const H = 500;
export const SCENES = [
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
export const TABS = ["Overview", "Ask", "File timeline", "Bug origins", "Who broke it?", "Hot files", "Co-change", "Authors",
  "Pull requests", "Commits"] as const;
export const PROVIDERS = [
  { id: "anthropic", name: "Anthropic" }, { id: "openai", name: "OpenAI" },
  { id: "gemini", name: "Google Gemini" }, { id: "groq", name: "Groq" },
  { id: "openrouter", name: "OpenRouter" },
] as const;
export const MODELS = ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"];
export const REPOS = [
  { name: "acme/storefront", private: true, note: "Checkout and payments" },
  { name: "acme/payments-api", private: true, note: "Payment service" },
  { name: "acme/docs", private: false, note: "Developer docs" },
];
export const STAGES = ["Cloning repository", "Reading commits", "Fetching pull requests", "Embedding history", "Ready"];
export const QUESTION = "Why was the checkout session logic refactored?";
export const ANSWER = "The refactor in `3f9c2a1` moved token refresh out of `CheckoutSession` after two fix commits " +
  "traced double charges to sessions expiring mid-payment. The review on PR #412 asked for an idempotent " +
  "retry path, added in `a81e0c4`.";
export const SOURCES = ["3f9c2a1 · j.chen", "a81e0c4 · m.okafor", "PR #412"];
export const REPORT = "Customers are charged twice when a payment is retried after the session expires.\n" +
  "  at retryPayment (payments/retry.ts:42)";
export const SUSPECTS = [
  { sha: "7d2e4b1", type: "Feature", msg: "Retry failed payments automatically", score: 84,
    reasons: ["Changed code your report mentions: retryPayment", "Changed payments/retry.ts, which your report names"] },
  { sha: "0c1d9fa", type: "Feature", msg: "Add checkout session", score: 71,
    reasons: ["Already traced as the cause of 2 earlier bug fixes", "A large change (1,240 lines)"] },
  { sha: "9a1f3c7", type: "Refactor", msg: "Share session tokens between tabs", score: 58,
    reasons: ["Partly matches your description", "Changed checkout/session.ts"] },
] as const;
export const ACTIVITY = [3, 5, 4, 8, 6, 11, 7, 9, 14, 10, 6, 12, 9, 13];
export const HOT = [["checkout/session.ts", 100], ["payments/retry.ts", 74], ["api/orders.ts", 58], ["checkout/cart.ts", 41]] as const;
export const TRACE_FILES = [
  { path: "checkout/session.ts", changes: 31 }, { path: "payments/retry.ts", changes: 22 },
  { path: "checkout/cart.ts", changes: 18 }, { path: "api/orders.ts", changes: 14 },
  { path: "checkout/session.test.ts", changes: 9 },
];
export const PHASES = [
  ["2023", "Built as one class handling the cart, tokens and payment.", "0c1d9fa"],
  ["2024", "Two double-charge fixes, then token refresh moved out.", "3f9c2a1"],
  ["2025", "A retry that is safe to repeat, asked for on PR #412.", "a81e0c4"],
] as const;
export const TRACE_COMMITS = [
  ["0c1d9fa", "Add checkout session"], ["5e2b8c0", "Fix double charge on retry"],
  ["3f9c2a1", "Move token refresh out"], ["a81e0c4", "Add idempotent retry"],
] as const;
export interface DemoState {
  name: string; email: string; password: string; confirm: string; creating: boolean; verify: boolean; code: string; confirming: boolean;
  onSettings: boolean; expanded: boolean; keyText: string; saving: boolean; connected: boolean; model: string | null; toast: string | null;
  dialog: boolean; picked: string | null; range: boolean; ingesting: boolean; stage: number;
  askTab: boolean; question: string; asked: boolean; found: boolean; answer: number; sources: number;
  report: string; finding: boolean; suspects: number;
  grow: boolean; timelineTab: boolean; pickerOpen: boolean; pickerText: string; traced: boolean; menu: boolean;
}
export const START: DemoState = {
  name: "", email: "", password: "", confirm: "", creating: false, verify: false, code: "", confirming: false,
  onSettings: false, expanded: false, keyText: "", saving: false, connected: false, model: null, toast: null,
  dialog: false, picked: null, range: false, ingesting: false, stage: -1,
  askTab: false, question: "", asked: false, found: false, answer: 0, sources: 0,
  report: "", finding: false, suspects: 0,
  grow: false, timelineTab: false, pickerOpen: false, pickerText: "", traced: false, menu: false,
};
// What each scene looks like when it has finished — used for reduced motion
export const FINAL: Record<number, Partial<DemoState>> = {
  0: { name: "Jo Chen", email: "jo@acme.dev", password: "••••••••••••", confirm: "••••••••••••" },
  1: { onSettings: true, expanded: true, keyText: "sk-ant-••••••••••••••••", connected: true, model: MODELS[1] },
  2: { picked: REPOS[0].name, ingesting: true, stage: STAGES.length - 1 },
  3: { askTab: true, question: QUESTION, asked: true, found: true, answer: ANSWER.length, sources: SOURCES.length },
  4: { report: REPORT, suspects: SUSPECTS.length },
  5: { grow: true, timelineTab: true, pickerText: TRACE_FILES[0].path, traced: true },
};

// Thrown to stop the walkthrough's running script when it's restarted or hidden
export class Cancelled extends Error {}

export type Reg = (key: string) => (el: HTMLElement | null) => void;
