import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ExternalLink, KeyRound, LogOut, ShieldCheck, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { GitHubIcon, ProviderMark } from "../components/brand";
import { ModelPicker } from "../components/ModelPicker";
import { Badge, Button, Card, CardHeader, ConfirmDialog, ErrorNotice, Input, Skeleton } from "../components/ui";
import { api } from "../lib/api";
import { meKey, useSession, useSignOut } from "../lib/auth";
import { providersKey, useProviders } from "../lib/queries";
import type { Provider } from "../lib/types";
import { cn, formatDate } from "../lib/utils";

function KeyForm({ provider, onDone }: { provider: Provider; onDone?: () => void }) {
  const [key, setKey] = useState("");
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: () => api.saveKey(provider.id, key),
    onSuccess: (res) => {
      qc.setQueryData(["models", provider.id], res.models);
      qc.invalidateQueries({ queryKey: providersKey });
      qc.invalidateQueries({ queryKey: meKey });
      setKey("");
      toast.success(`${provider.name} connected`, { description: `${res.models.length} models available. Pick one below.` });
      onDone?.();
    },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <KeyRound className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} required minLength={8}
                 autoComplete="off" spellCheck={false} placeholder={`Paste your ${provider.name} API key`}
                 aria-label={`${provider.name} API key`} className="pl-9 font-mono text-[13px]" />
        </div>
        <Button type="submit" loading={save.isPending} disabled={key.trim().length < 8}>Verify & save</Button>
      </div>
      {save.error && <ErrorNotice error={save.error} />}
      <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-subtle">
        <a href={provider.key_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-accent hover:underline">
          Create an API key <ExternalLink className="size-3" />
        </a>
        <span className="inline-flex items-center gap-1"><ShieldCheck className="size-3.5" /> Verified with the provider, then encrypted at rest</span>
      </p>
    </form>
  );
}

function ProviderCard({ provider, defaultOpen }: { provider: Provider; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [replacing, setReplacing] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const qc = useQueryClient();

  const models = useQuery({
    queryKey: ["models", provider.id],
    queryFn: () => api.models(provider.id),
    enabled: open && provider.configured,
    staleTime: 5 * 60_000,
  });
  const refresh = useMutation({
    mutationFn: () => api.models(provider.id, true),
    onSuccess: (data) => qc.setQueryData(["models", provider.id], data),
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: providersKey });
    qc.invalidateQueries({ queryKey: meKey });
  };
  const select = useMutation({
    mutationFn: async (model: string) => {
      await api.selectModel(provider.id, model);
      // The first model chosen also makes the provider active, so it's usable straight away
      if (!provider.active) await api.setActive(provider.id);
      return model;
    },
    onSuccess: (model) => { refreshAll(); toast.success("Model updated", { description: model }); },
    onError: (e) => toast.error(e.message),
  });
  const activate = useMutation({
    mutationFn: () => api.setActive(provider.id),
    onSuccess: () => { refreshAll(); toast.success(`Now using ${provider.name}`); },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: () => api.deleteKey(provider.id),
    onSuccess: () => {
      qc.removeQueries({ queryKey: ["models", provider.id] });
      refreshAll();
      setConfirmRemove(false);
      toast.success(`${provider.name} key removed`);
    },
  });

  const status = provider.active && provider.model
    ? <Badge tone="accent">Active</Badge>
    : provider.configured ? <Badge tone="success">Connected</Badge> : <Badge>Not connected</Badge>;

  return (
    <Card className={cn("overflow-hidden transition-colors", provider.active && "border-accent/40")}>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
              className="flex w-full items-center gap-3 px-5 py-4 text-left hover:bg-surface-2/50 cursor-pointer">
        <ProviderMark id={provider.id} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{provider.name}</span>
            {status}
          </div>
          <p className="mt-0.5 truncate text-xs text-muted">
            {provider.configured
              ? <>Key <span className="font-mono">{provider.key_hint}</span>{provider.model && <> · <span className="font-mono">{provider.model}</span></>}</>
              : "Add an API key to use this provider"}
          </p>
        </div>
        <ChevronDown className={cn("size-4 shrink-0 text-subtle transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="space-y-5 border-t border-border px-5 py-5">
          {!provider.configured || replacing ? (
            <KeyForm provider={provider} onDone={() => setReplacing(false)} />
          ) : (
            <>
              <div>
                <p className="mb-2 text-[13px] font-medium">Model</p>
                {models.error ? <ErrorNotice error={models.error} /> : (
                  <ModelPicker models={models.data} selected={provider.model} loading={models.isPending}
                               onSelect={(id) => id !== provider.model && select.mutate(id)}
                               pending={select.isPending ? select.variables ?? null : null}
                               onRefresh={() => refresh.mutate()} refreshing={refresh.isPending} />
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
                {!provider.active && (
                  <Button size="sm" onClick={() => activate.mutate()} loading={activate.isPending} disabled={!provider.model}
                          title={provider.model ? undefined : "Choose a model first"}>
                    Use {provider.name}
                  </Button>
                )}
                <Button size="sm" variant="secondary" onClick={() => setReplacing(true)}>Replace key</Button>
                <div className="flex-1" />
                <Button size="sm" variant="ghost" className="hover:text-danger" onClick={() => setConfirmRemove(true)}>
                  <Trash2 className="size-3.5" /> Remove
                </Button>
              </div>
            </>
          )}
          {replacing && (
            <button onClick={() => setReplacing(false)} className="text-xs text-muted hover:text-text cursor-pointer">Cancel</button>
          )}
        </div>
      )}

      <ConfirmDialog open={confirmRemove} onClose={() => setConfirmRemove(false)} onConfirm={() => remove.mutate()}
                     loading={remove.isPending} confirmLabel="Remove key" title={`Remove ${provider.name} key?`}
                     description="The encrypted key is deleted. You can add it again at any time." />
    </Card>
  );
}

function AccountCard() {
  const { user } = useSession();
  const signOut = useSignOut();
  const navigate = useNavigate();
  return (
    <Card>
      <CardHeader title="Account" description="Your sign-in details." />
      <dl className="divide-y divide-border text-[13px]">
        {[
          ["Name", user.name || "—"],
          ["Email", user.email],
          ["Sign-in", (
            <span className="flex flex-wrap items-center gap-2">
              {user.has_password && <Badge>Email & password</Badge>}
              {user.github_login && <Badge><GitHubIcon className="size-3" /> {user.github_login}</Badge>}
            </span>
          )],
          ["Member since", formatDate(user.created_at)],
        ].map(([k, v]) => (
          <div key={k as string} className="flex items-center justify-between gap-4 px-5 py-3">
            <dt className="text-muted">{k}</dt>
            <dd className="text-right">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="border-t border-border px-5 py-4">
        <Button variant="secondary" size="sm" onClick={async () => { await signOut(); navigate("/login"); }}>
          <LogOut className="size-3.5" /> Sign out
        </Button>
      </div>
    </Card>
  );
}

export default function Settings() {
  const providers = useProviders();
  const { user } = useSession();

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <p className="mt-1 text-sm text-muted">Connect the model provider you want answers from.</p>

      <section className="mt-8">
        <div className="mb-3 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold">Model providers</h2>
            <p className="mt-0.5 text-[13px] text-muted">
              Your own API key is used for every answer. Models are listed live from each provider's official API.
            </p>
          </div>
        </div>
        {providers.error && <ErrorNotice error={providers.error} />}
        <div className="space-y-3">
          {providers.isPending && [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-[72px] rounded-xl" />)}
          {providers.data?.map((p) => (
            <ProviderCard key={p.id} provider={p}
                          defaultOpen={p.active || (!user.active_provider && p.id === providers.data[0].id)} />
          ))}
        </div>
      </section>

      <section className="mt-10">
        <AccountCard />
      </section>
    </div>
  );
}
