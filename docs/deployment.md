# Breqy Website Deployment

## Scope

The public website is a static Astro + Tailwind marketing/docs site in `web/`. It does not deploy the Breqy runtime itself. Breqy remains a local-first Linux daemon, agent process, and TUI system.

## Branch to environment mapping

| Branch | GitHub Environment | Cloudflare Pages target | Custom domain |
|---|---|---|---|
| `develop` | `pre-prod` | `${CLOUDFLARE_PAGES_PROJECT_PREPROD}` | `https://develop.breqy.com` |
| `main` | `production` | `${CLOUDFLARE_PAGES_PROJECT_PROD}` | `https://breqy.com` |

The deployment workflow runs on pushes to `develop` and `main`. In normal use those pushes should happen by merging pull requests, not direct commits.

## Required GitHub configuration

Create the following repository or environment secrets and variables before the first deployment.

### Secrets

| Name | Purpose |
|---|---|
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token with Cloudflare Pages write permission. The deploy workflow uses it to create/verify Pages projects, add custom domains, and publish direct-upload deployments. |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID. This may also be a GitHub variable if the account ID is not treated as secret. |

### Variables

| Name | Value |
|---|---|
| `CLOUDFLARE_PAGES_PROJECT_PREPROD` | Cloudflare Pages project for pre-prod. |
| `CLOUDFLARE_PAGES_PROJECT_PROD` | Cloudflare Pages project for production. |
| `BREQY_PREPROD_SITE_URL` | `https://develop.breqy.com` |
| `BREQY_PROD_SITE_URL` | `https://breqy.com` |

Recommended GitHub Environments:

- `pre-prod`
- `production`

Use environment protection on `production` if a manual approval gate is desired before publishing `main` to `breqy.com`.

## Required Cloudflare setup

The deploy workflow creates missing Cloudflare Pages projects and adds missing custom domains before publishing. Operators still need to ensure:

1. The Cloudflare API token has Pages write permission for the target account.
2. The `breqy.com` zone is active in the same Cloudflare account.
3. DNS records and TLS for `develop.breqy.com` and `breqy.com` can be managed by Cloudflare.
4. The project names are configured in the GitHub variables above.

Using two Pages projects keeps pre-prod and production domain ownership explicit and avoids depending on preview-branch domain behavior for production validation.

## Local website development

```bash
cd web
npm ci
npm run dev
```

Useful checks:

```bash
cd web
npm test
npm run check
PUBLIC_BREQY_SITE_URL=https://breqy.com \
PUBLIC_BREQY_DEPLOY_ENV=local \
PUBLIC_BREQY_COMMIT_SHA=local \
npm run build
npm run smoke:build
```

The local `.env` sample for website-only public values is `web/.env.sample`.

## CI gates

The main CI workflow runs:

- Python tests with coverage
- runtime/source lint for `breqy`, `system`, and `scripts`
- `mypy breqy/`
- website unit tests
- Astro type checks
- static website build
- built-site smoke checks

The website deploy workflow repeats the website checks before publishing.

## Post-deploy validation

Every Cloudflare deployment embeds stable metadata in the generated HTML:

- `breqy:site-marker`
- `breqy:deploy-env`
- `breqy:commit-sha`

After publishing, the workflow calls `web/scripts/check-url.mjs` against the custom domain. The job fails unless the custom domain returns the expected site marker, deployment environment, and exact GitHub commit SHA.

This means the production workflow does not pass until `https://breqy.com` serves the website built from the merge commit.

## Rollback

Use Cloudflare Pages deployment history to promote a previous successful deployment, then rerun the relevant workflow when the repository is fixed. If the rollback should be reflected in git, revert the offending pull request and merge the revert into the affected protected branch.