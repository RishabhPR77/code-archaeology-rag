import { Link } from "react-router";

import { Logo } from "../components/brand";
import { Button } from "../components/ui";

export function NotFound() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-6 px-4 text-center">
      <Logo />
      <div>
        <p className="font-mono text-sm text-subtle">404</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">Nothing was ever committed here.</h1>
        <p className="mt-2 text-sm text-muted">The page you're looking for doesn't exist.</p>
      </div>
      <Link to="/"><Button variant="secondary">Back to home</Button></Link>
    </div>
  );
}
