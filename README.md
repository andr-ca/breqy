# Breqy

Breqy is a Linux-first, always-on multi-agent AI runtime. It runs as a local engine daemon, separate agent processes, and a Textual TUI client over typed A2A messages.

The public website is a separate static marketing/docs site in [web](web). It is not the Breqy runtime and does not introduce a cloud dependency for the product.

## Runtime quick start

```bash
uv sync
breqy engine start
breqy tui
```

Authenticate model providers as needed:

```bash
breqy auth copilot
```

## Website quick start

```bash
cd web
npm ci
npm run dev
```

Validate the website locally:

```bash
cd web
npm test
npm run check
npm run build
npm run smoke:build
```

## Deployment

Website deployment uses Cloudflare Pages and GitHub Actions:

- `develop` deploys pre-prod to `https://develop.breqy.com`
- `main` deploys production to `https://breqy.com`

See [docs/deployment.md](docs/deployment.md) for required Cloudflare projects, GitHub secrets/variables, and post-deploy validation.

## Core docs

- [docs/intent.md](docs/intent.md)
- [docs/prd.md](docs/prd.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/roadmap.md](docs/roadmap.md)
