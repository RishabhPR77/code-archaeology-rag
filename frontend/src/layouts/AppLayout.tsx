import { AlertTriangle, ChevronRight, LayoutDashboard, LogOut, Menu, Plus, Settings, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router";

import { LogoMark, ProviderMark, ThemeToggle } from "../components/brand";
import { NewRepoDialog } from "../components/NewRepoDialog";
import { Button } from "../components/ui";
import { useSession, useSignOut } from "../lib/auth";
import { useRepos } from "../lib/queries";
import type { Repo } from "../lib/types";
import { cn } from "../lib/utils";

function StatusDot({ repo }: { repo: Repo }) {
  const color = repo.status === "ready" ? "bg-success" : repo.status === "failed" ? "bg-danger" : "bg-warning animate-pulse";
  return <span className={cn("size-1.5 shrink-0 rounded-full", color)} />;
}

function Sidebar({ onNavigate, onNewRepo }: { onNavigate: () => void; onNewRepo: () => void }) {
  const { user } = useSession();
  const { data: repos } = useRepos();
  const signOut = useSignOut();
  const navigate = useNavigate();

  const navClass = ({ isActive }: { isActive: boolean }) =>
    cn("flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13px] font-medium transition-colors",
      isActive ? "bg-surface-2 text-text" : "text-muted hover:bg-surface-2 hover:text-text");

  return (
    <div className="flex h-full flex-col">
      <Link to="/app" onClick={onNavigate} className="flex items-center gap-2.5 px-4 pt-5 pb-6 font-semibold tracking-tight">
        <LogoMark />
        <span className="text-[15px]">Code Archaeologist</span>
      </Link>

      <nav className="space-y-0.5 px-3">
        <NavLink to="/app" end className={navClass} onClick={onNavigate}>
          <LayoutDashboard className="size-4" /> Dashboard
        </NavLink>
        <NavLink to="/app/settings" className={navClass} onClick={onNavigate}>
          <Settings className="size-4" /> Settings
        </NavLink>
      </nav>

      <div className="mt-7 flex items-center justify-between px-5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-subtle">Repositories</span>
        <button onClick={onNewRepo} aria-label="New repository"
                className="rounded-md p-1 text-muted hover:bg-surface-2 hover:text-text cursor-pointer">
          <Plus className="size-3.5" />
        </button>
      </div>
      <div className="mt-2 min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 pb-4">
        {repos?.length === 0 && <p className="px-2.5 py-2 text-[13px] text-subtle">No repositories yet</p>}
        {repos?.map((r) => (
          <NavLink key={r.id} to={`/app/repos/${r.id}`} className={navClass} onClick={onNavigate} title={r.full_name}>
            <StatusDot repo={r} />
            <span className="truncate">{r.full_name}</span>
          </NavLink>
        ))}
      </div>

      <div className="border-t border-border p-3">
        <div className="flex items-center gap-2.5 rounded-lg px-2 py-1.5">
          {user.avatar_url ? (
            <img src={user.avatar_url} alt="" className="size-8 rounded-full" />
          ) : (
            <span className="grid size-8 place-items-center rounded-full bg-accent-soft text-[13px] font-semibold text-accent">
              {(user.name || user.email)[0].toUpperCase()}
            </span>
          )}
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-medium">{user.name || user.email}</p>
            <p className="truncate text-xs text-subtle">{user.email}</p>
          </div>
          <button
            onClick={async () => { await signOut(); navigate("/login"); }}
            aria-label="Sign out" title="Sign out"
            className="rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text cursor-pointer"
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function ModelChip() {
  const { user } = useSession();
  if (!user.active_provider || !user.active_model) {
    return (
      <Link to="/app/settings"
            className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3 py-1.5 text-[13px] font-medium text-warning">
        <AlertTriangle className="size-3.5" />
        <span className="hidden sm:inline">Connect a model</span>
      </Link>
    );
  }
  return (
    <Link to="/app/settings" title="Change model"
          className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-surface px-2 py-1 text-[13px] transition-colors hover:border-border-strong">
      <ProviderMark id={user.active_provider} className="size-6 text-[9px]" />
      <span className="max-w-44 truncate font-mono text-xs text-muted">{user.active_model}</span>
      <ChevronRight className="size-3.5 text-subtle" />
    </Link>
  );
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [newRepoOpen, setNewRepoOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 border-r border-border bg-surface lg:block">
        <Sidebar onNavigate={() => undefined} onNewRepo={() => setNewRepoOpen(true)} />
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-72 border-r border-border bg-surface animate-fade-up">
            <button onClick={() => setMobileOpen(false)} aria-label="Close menu"
                    className="absolute top-5 right-3 rounded-md p-1 text-muted hover:text-text cursor-pointer">
              <X className="size-4" />
            </button>
            <Sidebar onNavigate={() => setMobileOpen(false)}
                     onNewRepo={() => { setMobileOpen(false); setNewRepoOpen(true); }} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-bg/80 px-4 backdrop-blur-md sm:px-6">
          <button onClick={() => setMobileOpen(true)} aria-label="Open menu"
                  className="-ml-1 rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-text lg:hidden cursor-pointer">
            <Menu className="size-5" />
          </button>
          <div className="flex-1" />
          <ModelChip />
          <ThemeToggle />
          <Button size="sm" onClick={() => setNewRepoOpen(true)}>
            <Plus className="size-4" /> <span className="hidden sm:inline">New repository</span>
          </Button>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>

      <NewRepoDialog open={newRepoOpen} onClose={() => setNewRepoOpen(false)} />
    </div>
  );
}
