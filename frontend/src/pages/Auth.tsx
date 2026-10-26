import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";

import { GitHubIcon, Logo, ThemeToggle } from "../components/brand";
import { Button, ErrorNotice, Input, Label } from "../components/ui";
import { api } from "../lib/api";
import { meKey } from "../lib/auth";

const OAUTH_ERRORS: Record<string, string> = {
  github_denied: "GitHub sign-in was cancelled.",
  github_state: "That sign-in link expired. Please try again.",
  github_token: "GitHub didn't accept the sign-in. Please try again.",
  github_unavailable: "Couldn't reach GitHub. Please try again.",
  github_no_email: "Your GitHub account has no verified email address.",
};

function AuthShell({ title, subtitle, children, footer }: {
  title: string; subtitle: string; children: ReactNode; footer: ReactNode;
}) {
  return (
    <div className="relative flex min-h-full flex-col">
      <div className="grid-bg absolute inset-0 -z-10 opacity-50" aria-hidden />
      <header className="flex items-center justify-between px-4 py-4 sm:px-8">
        <Logo />
        <ThemeToggle />
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-sm animate-fade-up">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1.5 text-sm text-muted">{subtitle}</p>
          <div className="mt-8">{children}</div>
          <p className="mt-8 text-center text-[13px] text-muted">{footer}</p>
        </div>
      </main>
    </div>
  );
}

function GitHubButton() {
  const { data } = useQuery({ queryKey: ["auth-config"], queryFn: api.authConfig, staleTime: Infinity });
  if (!data?.github_enabled) return null;
  return (
    <>
      <a href="/api/auth/github/login" className="block">
        <Button type="button" variant="secondary" size="lg" className="w-full">
          <GitHubIcon /> Continue with GitHub
        </Button>
      </a>
      <div className="my-6 flex items-center gap-3 text-xs text-subtle">
        <div className="h-px flex-1 bg-border" /> or with email <div className="h-px flex-1 bg-border" />
      </div>
    </>
  );
}

function PasswordInput({ id, value, onChange, autoComplete }: {
  id: string; value: string; onChange: (v: string) => void; autoComplete: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div className="relative">
      <Input id={id} type={show ? "text" : "password"} required minLength={8} value={value}
             autoComplete={autoComplete} onChange={(e) => onChange(e.target.value)} className="pr-10" />
      <button type="button" onClick={() => setShow((s) => !s)} aria-label={show ? "Hide password" : "Show password"}
              className="absolute top-1/2 right-2 -translate-y-1/2 rounded p-1 text-subtle hover:text-text cursor-pointer">
        {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
      </button>
    </div>
  );
}

function useAuthSuccess() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/app";
  return (me: Awaited<ReturnType<typeof api.login>>) => {
    qc.setQueryData(meKey, me);
    navigate(from, { replace: true });
  };
}

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [params] = useSearchParams();
  const onSuccess = useAuthSuccess();
  const login = useMutation({ mutationFn: () => api.login(email, password), onSuccess });
  const oauthError = OAUTH_ERRORS[params.get("error") ?? ""];

  const submit = (e: FormEvent) => { e.preventDefault(); login.mutate(); };

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your workspace."
               footer={<>New here? <Link to="/register" className="font-medium text-accent hover:underline">Create an account</Link></>}>
      {oauthError && <ErrorNotice error={new Error(oauthError)} className="mb-5" />}
      <GitHubButton />
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required autoComplete="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="current-password" />
        </div>
        {login.error && <ErrorNotice error={login.error} />}
        <Button type="submit" size="lg" className="w-full" loading={login.isPending}>Sign in</Button>
      </form>
    </AuthShell>
  );
}

export function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const onSuccess = useAuthSuccess();
  const register = useMutation({ mutationFn: () => api.register(email, password, name), onSuccess });

  const submit = (e: FormEvent) => { e.preventDefault(); register.mutate(); };

  return (
    <AuthShell title="Create your account" subtitle="Bring your own model key. Start digging in minutes."
               footer={<>Already have an account? <Link to="/login" className="font-medium text-accent hover:underline">Sign in</Link></>}>
      <GitHubButton />
      <form onSubmit={submit} className="space-y-4">
        <div>
          <Label htmlFor="name">Name</Label>
          <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ada Lovelace" />
        </div>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required autoComplete="email" value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" />
        </div>
        <div>
          <Label htmlFor="password" hint="At least 8 characters">Password</Label>
          <PasswordInput id="password" value={password} onChange={setPassword} autoComplete="new-password" />
        </div>
        {register.error && <ErrorNotice error={register.error} />}
        <Button type="submit" size="lg" className="w-full" loading={register.isPending}>Create account</Button>
      </form>
    </AuthShell>
  );
}
