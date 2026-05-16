const targetUrl = process.env.TARGET_URL;
const expectedCommit = process.env.EXPECTED_COMMIT_SHA ?? process.env.GITHUB_SHA;
const expectedEnv = process.env.EXPECTED_DEPLOY_ENV;
const retries = Number.parseInt(process.env.SMOKE_RETRIES ?? "30", 10);
const delayMs = Number.parseInt(process.env.SMOKE_DELAY_MS ?? "10000", 10);

if (!targetUrl) {
  console.error("TARGET_URL is required for URL smoke checks.");
  process.exit(2);
}

if (!expectedCommit) {
  console.error("EXPECTED_COMMIT_SHA or GITHUB_SHA is required for URL smoke checks.");
  process.exit(2);
}

if (!expectedEnv) {
  console.error("EXPECTED_DEPLOY_ENV is required for URL smoke checks.");
  process.exit(2);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const readUrl = async () => {
  const response = await fetch(targetUrl, {
    headers: {
      "User-Agent": "breqy-deploy-smoke/1.0",
      Accept: "text/html",
    },
    redirect: "follow",
  });
  const body = await response.text();
  return { response, body };
};

const hasMeta = (html, name, value) =>
  html.includes(`name="${name}" content="${value}"`) ||
  html.includes(`name='${name}' content='${value}'`);

let lastError = "unknown";

for (let attempt = 1; attempt <= retries; attempt += 1) {
  try {
    const { response, body } = await readUrl();
    const checks = [
      ["2xx status", response.ok],
      ["title", body.includes("Breqy — Always-on AI runtime for Linux")],
      ["site marker", body.includes("breqy-site-root")],
      ["deploy env", hasMeta(body, "breqy:deploy-env", expectedEnv)],
      ["commit sha", hasMeta(body, "breqy:commit-sha", expectedCommit)],
    ];
    const failed = checks.filter(([, passed]) => !passed).map(([name]) => name);
    if (failed.length === 0) {
      console.log(`URL smoke check passed for ${targetUrl} at commit ${expectedCommit}`);
      process.exit(0);
    }
    lastError = `attempt ${attempt}: failed checks: ${failed.join(", ")}`;
  } catch (error) {
    lastError = `attempt ${attempt}: ${error instanceof Error ? error.message : String(error)}`;
  }

  if (attempt < retries) {
    await sleep(delayMs);
  }
}

console.error(`URL smoke check failed for ${targetUrl}: ${lastError}`);
process.exit(1);