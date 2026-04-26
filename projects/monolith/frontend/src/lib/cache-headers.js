const ONE_DAY = 86_400;
const ONE_YEAR = 31_536_000;

// 60s fresh · 24h SWR (background refresh) · 1y SIE (cluster-down resilience)
export const PAGE_CACHE_CONTROL = `public, s-maxage=60, stale-while-revalidate=${ONE_DAY}, stale-if-error=${ONE_YEAR}`;
