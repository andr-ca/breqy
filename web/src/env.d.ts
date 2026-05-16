/// <reference types="astro/client" />

interface ImportMetaEnv {
  readonly PUBLIC_BREQY_SITE_URL?: string;
  readonly PUBLIC_BREQY_DEPLOY_ENV?: string;
  readonly PUBLIC_BREQY_COMMIT_SHA?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}