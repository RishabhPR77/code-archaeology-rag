import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { GitHubIcon, GoogleIcon } from "../../components/brand";
import { Badge, Button, Card, CardHeader } from "../../components/ui";
import { api } from "../../lib/api";
import { meKey, useSession } from "../../lib/auth";
import { githubStatusKey, useAuthConfig, useGitHubStatus } from "../../lib/queries";
import { formatDate } from "../../lib/utils";

function GitHubConnection() {
  const { user } = useSession();
  const qc = useQueryClient();
  const status = useGitHubStatus(user.github_connected);
  const disconnect = useMutation({
    mutationFn: api.disconnectGitHub,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: meKey });
      qc.invalidateQueries({ queryKey: githubStatusKey });
      toast.success("GitHub disconnected");
    },
  });
  const s = status.data;
  const shared = s?.installations ?? [];

  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-5 py-4">
      <div className="flex min-w-0 gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-surface-2"><GitHubIcon /></span>
        <div className="min-w-0">
          <p className="text-[13px] font-medium">GitHub</p>
          <p className="mt-0.5 text-xs text-muted">
            {!user.github_connected ? "Connect to ingest your own repositories, including private ones."
              : status.isPending ? "Checking access…"
              : s?.error ? s.error
              : shared.length === 0 ? <>Connected as @{user.github_login} · no repositories shared yet</>
              : <>Connected as @{user.github_login} · {shared.map((i) =>
                  `${i.account} (${i.repository_selection === "all" ? "all repos" : "selected repos"})`).join(", ")}</>}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {user.github_connected && !s?.error ? (
          <>
            {s?.install_url && (
              <a href={s.install_url}><Button size="sm" variant="secondary">Choose repositories</Button></a>
            )}
            <Button size="sm" variant="ghost" className="hover:text-danger" loading={disconnect.isPending}
                    onClick={() => disconnect.mutate()}>Disconnect</Button>
          </>
        ) : (
          <a href="/api/auth/github/login"><Button size="sm">{user.github_connected ? "Reconnect" : "Connect GitHub"}</Button></a>
        )}
      </div>
    </div>
  );
}

export function AccountCard() {
  const { user } = useSession();
  const config = useAuthConfig();
  return (
    <Card>
      <CardHeader title="Account" description="Your sign-in details and connected accounts." />
      <dl className="divide-y divide-border text-[13px]">
        {[
          ["Name", user.name || "—"],
          ["Email", user.email],
          ["Sign-in", (
            <span className="flex flex-wrap items-center justify-end gap-2">
              {user.has_password && <Badge>Email & password</Badge>}
              {user.google_linked && <Badge><GoogleIcon className="size-3" /> Google</Badge>}
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
      {config.data?.github_enabled && (
        <div className="border-t border-border">
          <p className="px-5 pt-4 text-[11px] font-semibold tracking-wider text-subtle uppercase">Connected accounts</p>
          <GitHubConnection />
        </div>
      )}
    </Card>
  );
}

