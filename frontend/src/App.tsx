import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, Outlet, useLocation } from "react-router";

import { Spinner } from "./components/ui";
import { AppLayout } from "./layouts/AppLayout";
import { useMe } from "./lib/auth";
import { Landing } from "./pages/Landing";
import { Login, Register } from "./pages/Auth";
import { NotFound } from "./pages/NotFound";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Settings = lazy(() => import("./pages/Settings"));
const RepoPage = lazy(() => import("./pages/repo/RepoPage"));
const VerifyEmail = lazy(() => import("./pages/VerifyEmail"));

function FullPageSpinner() {
  return (
    <div className="grid h-full place-items-center">
      <Spinner className="size-5" />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { data, isPending } = useMe();
  const location = useLocation();
  if (isPending) return <FullPageSpinner />;
  if (!data) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (!data.user.email_verified) return <Navigate to="/verify-email" replace />;
  return children;
}

// Signed in but email not confirmed yet
function RequireUnverified({ children }: { children: ReactNode }) {
  const { data, isPending } = useMe();
  if (isPending) return <FullPageSpinner />;
  if (!data) return <Navigate to="/login" replace />;
  if (data.user.email_verified) return <Navigate to="/app" replace />;
  return <Suspense fallback={<FullPageSpinner />}>{children}</Suspense>;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { data, isPending } = useMe();
  if (isPending) return <FullPageSpinner />;
  if (data) return <Navigate to="/app" replace />;
  return children;
}

export const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/login", element: <GuestOnly><Login /></GuestOnly> },
  { path: "/register", element: <GuestOnly><Register /></GuestOnly> },
  { path: "/verify-email", element: <RequireUnverified><VerifyEmail /></RequireUnverified> },
  {
    path: "/app",
    element: (
      <RequireAuth>
        <AppLayout>
          <Suspense fallback={<FullPageSpinner />}>
            <Outlet />
          </Suspense>
        </AppLayout>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Dashboard /> },
      { path: "settings", element: <Settings /> },
      { path: "repos/:repoId/:tab?", element: <RepoPage /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
