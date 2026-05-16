import { describe, expect, it } from "vitest";

import { buildExpectedMarkers } from "../src/content/deployment";

describe("deployment smoke marker contract", () => {
  it("generates stable markers for post-deploy domain validation", () => {
    expect(
      buildExpectedMarkers({
        siteUrl: "https://breqy.com",
        deployEnv: "production",
        commitSha: "abc123def456",
      }),
    ).toEqual({
      title: "Breqy — Always-on AI runtime for Linux",
      siteMarker: "breqy-site-root",
      deployEnv: "production",
      commitSha: "abc123def456",
      canonicalUrl: "https://breqy.com/",
    });
  });
});