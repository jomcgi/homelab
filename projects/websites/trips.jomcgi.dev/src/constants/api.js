// API Configuration
export const API_BASE_URL =
  import.meta.env.VITE_API_URL || "https://api.jomcgi.dev/trips";
export const WS_BASE_URL =
  import.meta.env.VITE_WS_URL || "wss://api.jomcgi.dev/trips";
export const IMAGE_BASE_URL =
  import.meta.env.VITE_IMAGE_URL || "https://img.jomcgi.dev";

// Feature flags
export const LIVE_FEATURES_ENABLED = false;
