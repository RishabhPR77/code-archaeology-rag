import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../lib/api", () => ({
  api: {
    authConfig: async () => ({ github_enabled: false, google_enabled: false, email_verification: true,
                               contact_email: null, demo_available: false }),
    login: vi.fn(async () => ({ two_factor_required: true })),
    twoFactor: { verify: vi.fn() },
  },
}));

import { Login } from "./Login";

describe("Login", () => {
  it("asks for the authenticator code after a right password on a two-step account", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><Login /></MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "me@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-good-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => expect(screen.getByText("Two-step sign-in")).toBeTruthy());
    expect(screen.getByLabelText("6-digit code")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Use a recovery code" })).toBeTruthy();
  });
});
