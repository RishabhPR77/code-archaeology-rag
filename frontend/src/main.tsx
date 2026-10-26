import "./index.css";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router/dom";
import { Toaster } from "sonner";

import { router } from "./App";
import { ApiError } from "./lib/api";
import { meKey } from "./lib/auth";

// A 401 anywhere means the session ended — drop the user so guards redirect to login
function onError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) queryClient.setQueryData(meKey, null);
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: {
    queries: {
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster
        position="bottom-right"
        toastOptions={{
          className: "!bg-surface !text-text !border-border !shadow-card",
          descriptionClassName: "!text-muted",
        }}
      />
    </QueryClientProvider>
  </StrictMode>,
);
