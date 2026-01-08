import { useEffect } from "react";

/**
 * Dynamically sets the favicon based on the current page context.
 * @param {"summary" | "detail"} variant - Which favicon to display
 */
export function useFavicon(variant) {
  useEffect(() => {
    const favicon = document.querySelector('link[rel="icon"]');
    if (favicon) {
      favicon.href =
        variant === "detail" ? "/favicon-detail.svg" : "/favicon-summary.svg";
    }
  }, [variant]);
}
