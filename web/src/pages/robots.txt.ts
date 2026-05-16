import { siteMeta } from "../content/site";

const siteUrl = import.meta.env.PUBLIC_BREQY_SITE_URL ?? siteMeta.productionUrl;

export const GET = () =>
  new Response(
    [`User-agent: *`, `Allow: /`, `Sitemap: ${siteUrl.replace(/\/+$/, "")}/sitemap-index.xml`].join(
      "\n",
    ),
    {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
      },
    },
  );