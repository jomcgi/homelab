import { useState, useRef, useEffect } from "react";

export function useWeather(lat, lng) {
  const [weather, setWeather] = useState(null);
  const [loading, setLoading] = useState(false);
  const cacheRef = useRef({ key: null, data: null, timestamp: 0 });

  useEffect(() => {
    if (!lat || !lng) return;

    // Round coords to 2 decimals for caching (met.no recommends this)
    const roundedLat = Math.round(lat * 100) / 100;
    const roundedLng = Math.round(lng * 100) / 100;
    const cacheKey = `${roundedLat},${roundedLng}`;

    // Use cached data if same location and less than 10 minutes old
    const cache = cacheRef.current;
    if (cache.key === cacheKey && Date.now() - cache.timestamp < 600000) {
      setWeather(cache.data);
      return;
    }

    async function fetchWeather() {
      setLoading(true);
      try {
        const response = await fetch(
          `https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=${roundedLat}&lon=${roundedLng}`,
          {
            headers: {
              "User-Agent": "trips.jomcgi.dev/1.0 github.com/jomcgi/homelab",
            },
          },
        );

        if (!response.ok) throw new Error("Weather fetch failed");

        const data = await response.json();
        const current = data.properties.timeseries[0];
        const details = current.data.instant.details;
        const symbol =
          current.data.next_1_hours?.summary?.symbol_code ||
          current.data.next_6_hours?.summary?.symbol_code ||
          "cloudy";

        const weatherData = {
          temp: Math.round(details.air_temperature),
          windSpeed: Math.round(details.wind_speed * 3.6), // m/s to km/h
          humidity: Math.round(details.relative_humidity),
          symbol: symbol,
        };

        cacheRef.current = {
          key: cacheKey,
          data: weatherData,
          timestamp: Date.now(),
        };
        setWeather(weatherData);
      } catch (err) {
        console.error("Weather fetch error:", err);
        setWeather(null);
      } finally {
        setLoading(false);
      }
    }

    fetchWeather();
  }, [lat, lng]);

  return { weather, loading };
}
