import { describe, expect, it } from "vitest";

import {
  deploymentTargets,
  homepageSections,
  productClaims,
  siteMeta,
} from "../src/content/site";

describe("Breqy website content contract", () => {
  it("positions the website as an early-access marketing/docs site for a local runtime", () => {
    expect(siteMeta.launchStage).toBe("Early Access");
    expect(siteMeta.productionUrl).toBe("https://breqy.com");
    expect(siteMeta.preProductionUrl).toBe("https://develop.breqy.com");
    expect(siteMeta.positioning.toLowerCase()).toContain("local-first");
    expect(siteMeta.positioning.toLowerCase()).toContain("marketing/docs");
    expect(siteMeta.positioning.toLowerCase()).not.toContain("cloud-hosted app");
  });

  it("contains the required homepage sections from the project docs", () => {
    expect(homepageSections.map((section) => section.id)).toEqual([
      "hero",
      "runtime",
      "agents",
      "sessions",
      "approvals",
      "control",
      "architecture",
      "quickstart",
      "roadmap",
      "source",
    ]);
  });

  it("does not present deferred Slice 2 capabilities as available today", () => {
    const deferredCapabilities = productClaims.filter((claim) => claim.status === "deferred");
    expect(deferredCapabilities.map((claim) => claim.name)).toEqual([
      "Rich WebUI channel",
      "SSH operations",
      "Docker inspection workflows",
      "Agent delegation depth",
    ]);

    for (const claim of deferredCapabilities) {
      expect(claim.copy.toLowerCase()).toMatch(/future|deferred|planned|slice 2/);
      expect(claim.copy.toLowerCase()).not.toMatch(/available now|shipped today/);
    }
  });

  it("maps branch deployments to explicit Cloudflare Pages environments", () => {
    expect(deploymentTargets).toEqual({
      develop: {
        environment: "pre-prod",
        url: "https://develop.breqy.com",
        projectVariable: "CLOUDFLARE_PAGES_PROJECT_PREPROD",
      },
      main: {
        environment: "production",
        url: "https://breqy.com",
        projectVariable: "CLOUDFLARE_PAGES_PROJECT_PROD",
      },
    });
  });
});