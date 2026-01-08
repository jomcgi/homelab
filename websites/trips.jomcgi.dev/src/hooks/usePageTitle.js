import { useEffect } from "react";

/**
 * Dynamically sets the page title based on trip and page context.
 * @param {string} shortTitle - Short trip name (e.g., "Liard")
 * @param {string} [suffix] - Optional suffix (e.g., "Day 5", "Timeline")
 */
export function usePageTitle(shortTitle, suffix = null) {
  useEffect(() => {
    if (!shortTitle) return;
    document.title = suffix ? `${shortTitle} | ${suffix}` : shortTitle;
  }, [shortTitle, suffix]);
}
