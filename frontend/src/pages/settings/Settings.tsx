import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Navigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { ErrorNotice, Skeleton } from "../../components/ui";
import { meKey, useSession } from "../../lib/auth";
import { githubStatusKey, useProviders } from "../../lib/queries";
import { AccountCard } from "./AccountCard";
import { ActivityCard } from "./ActivityCard";
import { DeleteAccountCard } from "./DeleteAccountCard";
import { DemoCard } from "./DemoCard";
import { ProviderCard } from "./ProviderCard";
import { SecurityCard } from "./SecurityCard";

const GITHUB_NOTICES: Record<string, [kind: "success" | "error", message: string]> = {
  connected: ["success", "GitHub connected"],
  installed: ["success", "Repository access updated"],
  taken: ["error", "That GitHub account is already linked to another Code Archaeologist account"],
};

export default function Settings() {
  const { user } = useSession();
  // The demo is read-only, so it has nothing to set
  return user.is_demo ? <Navigate to="/app" replace /> : <SettingsPage />;
}

function SettingsPage() {
  const providers = useProviders();
  const { user } = useSession();
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();

  // Messages from the GitHub redirect (?github=connected|installed|taken)
  const notice = params.get("github");
  useEffect(() => {
    const entry = notice ? GITHUB_NOTICES[notice] : undefined;
    if (!entry) return;
    toast[entry[0]](entry[1]);
    qc.invalidateQueries({ queryKey: githubStatusKey });
    qc.invalidateQueries({ queryKey: meKey });
    setParams({}, { replace: true });
  }, [notice, qc, setParams]);

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <p className="mt-1 text-sm text-muted">Your model provider, account and security.</p>

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

      <section className="mt-10 space-y-6">
        <AccountCard />
        <SecurityCard />
        <ActivityCard />
        <DeleteAccountCard />
      </section>

      {user.is_admin && (
        <section className="mt-10">
          <DemoCard />
        </section>
      )}
    </div>
  );
}
