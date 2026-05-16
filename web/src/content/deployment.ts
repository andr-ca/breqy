export type DeploymentMarkerInput = {
  siteUrl: string;
  deployEnv: string;
  commitSha: string;
};

export type DeploymentMarkers = {
  title: string;
  siteMarker: string;
  deployEnv: string;
  commitSha: string;
  canonicalUrl: string;
};

const normalizeSiteUrl = (siteUrl: string): string => {
  const trimmed = siteUrl.trim().replace(/\/+$/, "");
  return `${trimmed}/`;
};

export const buildExpectedMarkers = ({
  siteUrl,
  deployEnv,
  commitSha,
}: DeploymentMarkerInput): DeploymentMarkers => ({
  title: "Breqy — Always-on AI runtime for Linux",
  siteMarker: "breqy-site-root",
  deployEnv,
  commitSha,
  canonicalUrl: normalizeSiteUrl(siteUrl),
});