import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { NewPasswordFields, passwordsReady, passwordStrength } from "./shared";

describe("password rules", () => {
  it("rates length first", () => {
    expect(passwordStrength("short")).toBe(0);
    expect(passwordStrength("abcdefgh")).toBe(1);
    expect(passwordStrength("correct horse")).toBe(2);
    expect(passwordStrength("correct horse battery staple")).toBe(3);
  });
  it("needs both copies to match", () => {
    expect(passwordsReady("long-enough-1", "long-enough-1")).toBe(true);
    expect(passwordsReady("long-enough-1", "long-enough-2")).toBe(false);
    expect(passwordsReady("short", "short")).toBe(false);
  });
});

function Form() {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  return <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />;
}

describe("NewPasswordFields", () => {
  it("says when the confirmation doesn't match", () => {
    render(<Form />);
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: "first-password-1" } });
    fireEvent.change(screen.getByLabelText(/Confirm password/), { target: { value: "first-password-2" } });
    expect(screen.getByText("The passwords don't match.")).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Confirm password/), { target: { value: "first-password-1" } });
    expect(screen.queryByText("The passwords don't match.")).toBeNull();
  });
});
