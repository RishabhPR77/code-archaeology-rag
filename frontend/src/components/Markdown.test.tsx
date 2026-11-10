import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "./Markdown";

describe("Markdown answers", () => {
  it("never turns HTML from the model into real elements", () => {
    const { container } = render(<Markdown>{'Hello <img src=x onerror="alert(1)"> <script>alert(2)</script>'}</Markdown>);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });
  it("links commit SHAs to GitHub", () => {
    const { container } = render(<Markdown repoUrl="https://github.com/pallets/flask">{"See `8999295`."}</Markdown>);
    expect(container.querySelector("a")?.getAttribute("href")).toBe("https://github.com/pallets/flask/commit/8999295");
  });
});
