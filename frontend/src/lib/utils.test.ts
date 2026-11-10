import { describe, expect, it } from "vitest";

import { commitSpan, relativeTime, shortSha } from "./utils";

describe("commitSpan", () => {
  it("names the latest commits plainly", () => {
    expect(commitSpan({ commit_count: 300 })).toBe("300 commits");
  });
  it("names a range counted back from the newest commit", () => {
    expect(commitSpan({ commit_count: 201, skip_commits: 499 })).toBe("commits 500–700");
  });
});

describe("small formatters", () => {
  it("shortens a SHA to seven characters", () => {
    expect(shortSha("8999295abcdef0123")).toBe("8999295");
  });
  it("says just now for the last minute", () => {
    expect(relativeTime(new Date(Date.now() - 5_000).toISOString())).toBe("just now");
    expect(relativeTime(null)).toBe("—");
  });
});
