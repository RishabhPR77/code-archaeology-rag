import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate, Outlet, useLocation } from "react-router";

import { Spinner } from "./components/ui";
import { AppLayout } from "./layouts/AppLayout";
import { useMe } from "./lib/auth";
import { Landing } from "./pages/Landing";
import { Privacy, Terms } from "./pages/Legal";
import { ForgotPassword } from "./pages/auth/ForgotPassword";
import { Login } from "./pages/auth/Login";
import { Register } from "./pages/auth/Register";
import { TwoFactorPage } from "./pages/auth/TwoFactor";
import { NotFound } from "./pages/NotFound";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const Settings = lazy(() => import("./pages/settings/Settings"));
const Profile = lazy(() => import("./pages/Profile"));
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

// Just signed up (a code was emailed, no session yet), or signed in but not confirmed yet.
// The page itself sends anyone else on to the right place.
function VerifyGate({ children }: { children: ReactNode }) {
  const { isPending } = useMe();
  if (isPending) return <FullPageSpinner />;
  return <Suspense fallback={<FullPageSpinner />}>{children}</Suspense>;
}

// Signed-out visitors, and demo visitors who want their own account
function GuestOnly({ children }: { children: ReactNode }) {
  const { data, isPending } = useMe();
  if (isPending) return <FullPageSpinner />;
  if (data && !data.user.is_demo) return <Navigate to="/app" replace />;
  return children;
}

export const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/privacy", element: <Privacy /> },
  { path: "/terms", element: <Terms /> },
  { path: "/login", element: <GuestOnly><Login /></GuestOnly> },
  { path: "/register", element: <GuestOnly><Register /></GuestOnly> },
  { path: "/verify-email", element: <VerifyGate><VerifyEmail /></VerifyGate> },
  { path: "/forgot-password", element: <GuestOnly><ForgotPassword /></GuestOnly> },
  { path: "/two-factor", element: <GuestOnly><TwoFactorPage /></GuestOnly> },
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
      { path: "profile", element: <Profile /> },
      { path: "repos/:repoId/:tab?", element: <RepoPage /> },
    ],
  },
  { path: "*", element: <NotFound /> },
]);
