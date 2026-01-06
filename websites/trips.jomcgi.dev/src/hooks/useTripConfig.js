import { useState, useEffect } from "react";
import yaml from "js-yaml";

/**
 * Fetches and parses the config.yaml for a trip.
 * Config files are stored at: /trips/<tripSlug>/config.yaml
 */
export function useTripConfig(tripSlug) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!tripSlug) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    async function fetchConfig() {
      try {
        setLoading(true);
        setError(null);

        const configUrl = `/trips/${tripSlug}/config.yaml`;
        const response = await fetch(configUrl);

        if (!response.ok) {
          if (response.status === 404) {
            // Config not found - use defaults
            if (!cancelled) {
              setConfig(null);
              setLoading(false);
            }
            return;
          }
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const yamlText = await response.text();
        const parsed = yaml.load(yamlText);

        if (!cancelled) {
          setConfig(parsed);
        }
      } catch (err) {
        console.error("Failed to fetch trip config:", err);
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchConfig();

    return () => {
      cancelled = true;
    };
  }, [tripSlug]);

  return { config, loading, error };
}
