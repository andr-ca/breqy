import { readFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const distDir = resolve(process.argv[2] ?? "dist");
const indexPath = join(distDir, "index.html");
const html = await readFile(indexPath, "utf8");

const expectedCommit = process.env.PUBLIC_BREQY_COMMIT_SHA ?? process.env.GITHUB_SHA ?? "local";
const expectedEnv = process.env.PUBLIC_BREQY_DEPLOY_ENV ?? "local";

const checks = [
  ["title", /<title>Breqy — Always-on AI runtime for Linux<\/title>/.test(html)],
  ["site marker", html.includes("breqy-site-root")],
  ["deployment environment", html.includes(`name="breqy:deploy-env" content="${expectedEnv}"`)],
  ["commit sha", html.includes(`name="breqy:commit-sha" content="${expectedCommit}"`)],
  ["early access", html.includes("Early Access")],
];

const failed = checks.filter(([, passed]) => !passed).map(([name]) => name);

if (failed.length > 0) {
  console.error(`Built-site smoke check failed for: ${failed.join(", ")}`);
  process.exit(1);
}

console.log(`Built-site smoke check passed for ${indexPath}`);