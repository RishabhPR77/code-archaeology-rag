import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Button, Card, CardHeader, ErrorNotice, Skeleton } from "../../components/ui";
import { api } from "../../lib/api";
import { authConfigKey, demoReposKey, reposKey } from "../../lib/queries";

// Admins only: the repositories anyone can open from the home page without signing up
export function DemoCard() {
  const qc = useQueryClient();
  const shared = useQuery({ queryKey: demoReposKey, queryFn: api.demoRepos });
  const stop = useMutation({
    mutationFn: api.stopSharing,
    onSuccess: () => {
      for (const key of [demoReposKey, reposKey, authConfigKey]) qc.invalidateQueries({ queryKey: key });
      toast.success("Removed from the demo", { description: "It's back in your repositories, with its chats." });
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Card>
      <CardHeader title="Public demo"
                  description="Repositories anyone can explore from the home page without signing up. Only admins see this." />
      {shared.error && <div className="p-5"><ErrorNotice error={shared.error} /></div>}
      {shared.isPending ? (
        <div className="p-5"><Skeleton className="h-9 rounded-lg" /></div>
      ) : shared.data?.length ? (
        <ul className="divide-y divide-border text-[13px]">
          {shared.data.map((r) => (
            <li key={r.id} className="flex items-center justify-between gap-4 px-5 py-3">
              <span className="min-w-0 truncate font-mono">{r.full_name}</span>
              <Button size="sm" variant="secondary" loading={stop.isPending && stop.variables === r.id}
                      onClick={() => stop.mutate(r.id)}>Stop sharing</Button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-5 py-4 text-[13px] text-muted">
          Nothing is shared yet. Open one of your public repositories and choose Use as public demo.
        </p>
      )}
    </Card>
  );
}

