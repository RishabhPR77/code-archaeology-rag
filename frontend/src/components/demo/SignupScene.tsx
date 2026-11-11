import { Loader2, Mail, Moon } from "lucide-react";
import { cn } from "../../lib/utils";
import { GitHubIcon, GoogleIcon, LogoMark } from "../brand";
import type { DemoState, Reg } from "./data";
import { Btn, Field } from "./frame";

export function SignupScene({ s, t }: { s: DemoState; t: Reg }) {
  const typing = s.confirm ? "confirm" : s.password ? "password" : s.email ? "email" : s.name ? "name" : "";
  // The real form's strength meter: it fills as the password gets longer
  const strength = s.password.length >= 12 ? 3 : s.password.length >= 10 ? 2 : s.password.length >= 8 ? 1 : 0;
  return (
    <div className="absolute inset-x-0 top-9 bottom-0 flex bg-surface">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between px-6 py-2">
          <span className="flex items-center gap-2"><LogoMark className="size-6" /><span className="text-[13px] font-semibold">Code Archaeologist</span></span>
          <Moon className="size-3.5 text-muted" />
        </div>
        <div className="flex flex-1 items-center justify-center px-6">
          {!s.verify ? (
            // The real form (with its confirm field and strength meter) is taller than this frame; drawn a little smaller
            <div className="origin-center scale-[0.88]"><div className="w-[300px] animate-fade-up">
              <p className="text-[19px] font-bold tracking-tight">Create your account</p>
              <p className="mt-0.5 text-[11.5px] text-muted">Bring your own model key. Start digging in minutes.</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Btn className="w-full"><GoogleIcon className="size-3.5" /> Google</Btn>
                <Btn className="w-full"><GitHubIcon className="size-3.5" /> GitHub</Btn>
              </div>
              <p className="my-2 flex items-center gap-2 text-[10.5px] text-subtle">
                <span className="h-px flex-1 bg-border" /> or with email <span className="h-px flex-1 bg-border" />
              </p>
              <div className="space-y-1.5">
                <Field label="Name" value={s.name} placeholder="Ada Lovelace" r={t("signup-name")} focus={typing === "name"} />
                <Field label="Email" value={s.email} placeholder="you@company.com" r={t("signup-email")} focus={typing === "email"} />
                <Field label="Password" value={s.password} placeholder="At least 8 characters" r={t("signup-password")} focus={typing === "password"} />
                {s.password && (
                  <div className="flex items-center gap-2">
                    <div className="flex flex-1 gap-1">
                      {[1, 2, 3].map((i) => <span key={i} className={cn("h-1 flex-1 rounded-full bg-border", strength >= i && "bg-accent")} />)}
                    </div>
                    <span className="w-10 text-right text-[10px] text-muted">{["", "Okay", "Good", "Strong"][strength]}</span>
                  </div>
                )}
                <Field label="Confirm password" value={s.confirm} placeholder="Type it again" r={t("signup-confirm")} focus={typing === "confirm"} />
              </div>
              <span ref={t("create")} className="mt-2.5 block">
                <Btn primary className="h-9 w-full">{s.creating && <Loader2 className="size-3.5 animate-spin" />} Create account</Btn>
              </span>
              <p className="mt-2 text-center text-[10.5px] text-muted">Already have an account? <span className="font-medium text-accent">Sign in</span></p>
            </div></div>
          ) : (
            <div className="w-[300px] text-center animate-fade-up">
              <span className="mx-auto grid size-11 place-items-center rounded-xl bg-accent-soft text-accent"><Mail className="size-5" /></span>
              <p className="mt-3 text-[19px] font-semibold tracking-tight">Check your email</p>
              <p className="mt-1 text-[11.5px] text-muted">We sent a 6-digit code to <span className="font-medium text-text">jo@acme.dev</span>. It expires in 10 minutes.</p>
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
