// Day colors for multi-day route visualization
export const DAY_COLORS = [
  "#3b82f6", // Blue - Day 1
  "#10b981", // Emerald - Day 2
  "#f59e0b", // Amber - Day 3
  "#ef4444", // Red - Day 4
  "#8b5cf6", // Violet - Day 5
  "#06b6d4", // Cyan - Day 6
  "#f97316", // Orange - Day 7
  "#ec4899", // Pink - Day 8
  "#16a34a", // Green - Day 9
  "#14b8a6", // Teal - Day 10
  "#a855f7", // Purple - Day 11
  "#0ea5e9", // Sky - Day 12
];

// Weather symbol to description mapping
export const weatherDescriptions = {
  clearsky: "Clear",
  fair: "Fair",
  partlycloudy: "Partly Cloudy",
  cloudy: "Cloudy",
  lightrainshowers: "Light Showers",
  rainshowers: "Showers",
  heavyrainshowers: "Heavy Showers",
  lightrain: "Light Rain",
  rain: "Rain",
  heavyrain: "Heavy Rain",
  lightsnowshowers: "Light Snow",
  snowshowers: "Snow Showers",
  heavysnowshowers: "Heavy Snow",
  lightsnow: "Light Snow",
  snow: "Snow",
  heavysnow: "Heavy Snow",
  fog: "Fog",
  thunder: "Thunderstorm",
};

export function getWeatherDescription(symbol) {
  const base = symbol?.replace(/_day|_night/g, "") || "cloudy";
  return weatherDescriptions[base] || "Cloudy";
}
