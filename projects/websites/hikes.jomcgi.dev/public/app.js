// app.js - Find Good Hikes Static Site
import HIKES_CONFIG from "./config.js?v=2";

// State management
const state = {
  indexData: null,
  walkCache: new Map(),
  searchResults: [],
};

// Configuration
const CONFIG = {
  // Use config.js settings or fallback to defaults
  dataPath: HIKES_CONFIG?.useLocalData
    ? "data/"
    : HIKES_CONFIG?.dataUrl || "https://hikes-data.example.com/",
  localStorageKey: "find-good-hikes-preferences",
  cacheMinutes: HIKES_CONFIG?.cacheMinutes || 60,
};

// Utility functions
function savePreferences() {
  const prefs = {
    latitude: document.getElementById("latitude").value,
    longitude: document.getElementById("longitude").value,
    radius: document.getElementById("radius").value,
    minDuration: document.getElementById("min-duration").value,
    maxDuration: document.getElementById("max-duration").value,
    minDistance: document.getElementById("min-distance").value,
    maxDistance: document.getElementById("max-distance").value,
    maxAscent: document.getElementById("max-ascent").value,
    maxRain: document.getElementById("max-precipitation-mm").value,
    maxWind: document.getElementById("max-wind-speed-kmh").value,
    minTemp: document.getElementById("min-temperature-c").value,
    maxTemp: document.getElementById("max-temperature-c").value,
    startAfter: document.getElementById("start-after").value,
    finishBefore: document.getElementById("finish-before").value,
  };
  localStorage.setItem(CONFIG.localStorageKey, JSON.stringify(prefs));
}

function loadPreferences() {
  const saved = localStorage.getItem(CONFIG.localStorageKey);
  if (!saved) return;

  try {
    const prefs = JSON.parse(saved);
    Object.entries(prefs).forEach(([key, value]) => {
      const elem = document.getElementById(
        key.replace(/([A-Z])/g, "-$1").toLowerCase(),
      );
      if (elem) elem.value = value;
    });
  } catch (e) {
    // Silently fail if preferences can't be loaded
  }
}

// Haversine distance calculation
function calculateDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // Earth's radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

// Date generation
function generateDateOptions() {
  const container = document.getElementById("available-dates");
  container.innerHTML = "";

  // Use UK timezone for Scotland-based walks
  const today = new Date();
  const ukToday = new Date(
    today.toLocaleString("en-US", { timeZone: "Europe/London" }),
  );
  ukToday.setHours(0, 0, 0, 0);

  for (let i = 0; i < 7; i++) {
    const date = new Date(ukToday);
    date.setDate(ukToday.getDate() + i);

    // Use UK timezone for date string to match filtering logic
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const dateStr = `${year}-${month}-${day}`;

    const dayName = date.toLocaleDateString("en-GB", {
      weekday: "long",
      timeZone: "Europe/London",
    });
    const dayNum = date.getDate();
    const monthName = date.toLocaleDateString("en-GB", {
      month: "short",
      timeZone: "Europe/London",
    });

    const option = document.createElement("div");
    option.className = "checkbox-group";
    option.innerHTML = `
            <input type="checkbox" id="date-${dateStr}" name="available_dates" value="${dateStr}">
            <label for="date-${dateStr}">
                ${dayName}, ${monthName} ${dayNum}
            </label>
        `;
    container.appendChild(option);
  }
}

// Bundle data parsing
function parseBundleData(bundle) {
  // Parse the optimized bundle format
  // Bundle format: { v: 2, g: timestamp, d: [[walk data]...] }
  // Walk format: [id, lat, lng, dur, dist, asc, name, url, summary, windows]
  // Window format: [timestamp, temp, precip, wind, cloud]

  const walks = [];
  const walkMap = new Map();

  for (const walkData of bundle.d) {
    const [
      id,
      lat,
      lng,
      duration_h,
      distance_km,
      ascent_m,
      name,
      url,
      summary,
      windows,
    ] = walkData;

    // Create index entry
    walks.push({
      id,
      lat,
      lng,
      duration_h,
      distance_km,
      ascent_m,
    });

    // Create full walk data with expanded windows
    const expandedWindows = windows.map((w) => {
      const [timestamp, temp_c, precip_mm, wind_kmh, cloud_pct] = w;
      const startDate = new Date(timestamp * 1000);
      const endDate = new Date(startDate.getTime() + 3600000); // +1 hour

      return {
        start: startDate.toISOString(),
        end: endDate.toISOString(),
        weather: {
          temp_c,
          precip_mm,
          wind_kmh,
          cloud_pct: cloud_pct !== undefined ? cloud_pct : 50, // Use actual data or fallback to 50
        },
      };
    });

    walkMap.set(id, {
      name,
      url,
      summary,
      windows: expandedWindows,
    });
  }

  return { walks, walkMap };
}

// Data loading
async function loadIndexData() {
  try {
    const brotliPath = `${CONFIG.dataPath}bundle.brotli`;
    const response = await fetch(brotliPath, {
      headers: {
        Accept: "application/octet-stream",
      },
    });

    if (!response.ok) {
      throw new Error(
        `Failed to load bundle: ${response.status} ${response.statusText}`,
      );
    }

    const brotliBuffer = await response.arrayBuffer();

    const decompressedString = await BrotliDecompress(brotliBuffer);
    const bundle = JSON.parse(decompressedString);

    // Parse bundle into index and walk data
    const { walks, walkMap } = parseBundleData(bundle);

    // Set up state
    state.indexData = {
      generated_at: bundle.g * 1000, // Convert to milliseconds
      walks: walks,
    };

    // Pre-populate walk cache with all data
    state.walkCache = walkMap;

    // Update timestamp
    const timestamp = new Date(state.indexData.generated_at);
    document.getElementById("data-timestamp").textContent =
      timestamp.toLocaleString();

    // Check if data is stale (>2 hours old)
    const ageHours = (Date.now() - timestamp) / (1000 * 60 * 60);
    if (ageHours > 2) {
      showError(
        "Warning: Weather data is more than 2 hours old. Results may be outdated.",
      );
    }

    return true;
  } catch (error) {
    showError(
      `Failed to load hike data. The server returned an error: ${error.message}. Please try again later.`,
    );
    return false;
  }
}

async function loadWalkData(walkId) {
  // All walk data is pre-loaded from the bundle
  if (state.walkCache.has(walkId)) {
    return state.walkCache.get(walkId);
  }

  // Walk not found in bundled data
  return null;
}

// Filtering functions
function filterWalksByLocation(walks, userLat, userLon, radius) {
  return walks
    .filter((walk) => {
      const distance = calculateDistance(userLat, userLon, walk.lat, walk.lng);
      walk.distance_from_user = distance;
      return distance <= radius;
    })
    .sort((a, b) => a.distance_from_user - b.distance_from_user);
}

function filterWalksByCharacteristics(walks, filters) {
  return walks.filter((walk) => {
    if (
      walk.duration_h < filters.minDuration ||
      walk.duration_h > filters.maxDuration
    )
      return false;
    if (
      walk.distance_km < filters.minDistance ||
      walk.distance_km > filters.maxDistance
    )
      return false;
    if (walk.ascent_m > filters.maxAscent) return false;
    return true;
  });
}

function filterWindowsByWeather(windows, filters, selectedDates) {
  const startHour = parseInt(filters.startAfter.split(":")[0]);
  const startMin = parseInt(filters.startAfter.split(":")[1]);
  const endHour = parseInt(filters.finishBefore.split(":")[0]);
  const endMin = parseInt(filters.finishBefore.split(":")[1]);

  const now = new Date();

  return windows.filter((window) => {
    const startTime = new Date(window.start);

    // Exclude windows that have already started
    if (startTime < now) return false;

    // Convert UTC window time to UK timezone for date comparison
    const ukTime = new Date(
      startTime.toLocaleString("en-US", { timeZone: "Europe/London" }),
    );
    const year = ukTime.getFullYear();
    const month = String(ukTime.getMonth() + 1).padStart(2, "0");
    const day = String(ukTime.getDate()).padStart(2, "0");
    const dateStr = `${year}-${month}-${day}`;

    // Check if date is selected
    if (!selectedDates.includes(dateStr)) return false;

    // Check time constraints (use UK timezone)
    const hour = ukTime.getHours();
    const min = ukTime.getMinutes();
    if (hour < startHour || (hour === startHour && min < startMin))
      return false;
    if (hour >= endHour || (hour === endHour && min >= endMin)) return false;

    // Check weather constraints
    const weather = window.weather;
    if (weather.precip_mm > filters.maxRain) return false;
    if (weather.wind_kmh > filters.maxWind) return false;
    if (weather.temp_c < filters.minTemp || weather.temp_c > filters.maxTemp)
      return false;
    if (weather.cloud_pct > filters.maxCloud) return false;

    return true;
  });
}

// UI functions
function showLoading(show) {
  document.getElementById("loading").classList.toggle("hidden", !show);
}

function showError(message) {
  const errorDiv = document.getElementById("error");
  errorDiv.textContent = message;
  errorDiv.classList.remove("hidden");
  setTimeout(() => errorDiv.classList.add("hidden"), 10000);
}

function groupConsecutiveWindows(windows) {
  if (!windows || windows.length === 0) {
    return [];
  }
  windows.sort((a, b) => new Date(a.start) - new Date(b.start));
  const grouped = [];
  let currentGroup = [windows[0]];
  for (let i = 1; i < windows.length; i++) {
    const prevEnd =
      new Date(currentGroup[currentGroup.length - 1].start).getTime() + 3600000;
    const currentStart = new Date(windows[i].start).getTime();
    if (currentStart === prevEnd) {
      currentGroup.push(windows[i]);
    } else {
      grouped.push(currentGroup);
      currentGroup = [windows[i]];
    }
  }
  grouped.push(currentGroup);
  return grouped;
}

function findBestWindow(windows) {
  if (!windows || windows.length === 0) return null;

  let bestWindow = null;
  let bestScore = Infinity;

  for (const window of windows) {
    const weather = window.weather;
    // Score based on criteria: precip (lower is better), cloud (lower is better), wind (lower is better)
    // Prioritize precip, then cloud, then wind
    let score =
      weather.precip_mm * 100 + weather.cloud_pct * 1 + weather.wind_kmh * 0.1;

    // Add a penalty for higher precipitation if it's not near zero
    if (weather.precip_mm > 0.1) {
      score += 1000; // Significant penalty for noticeable rain
    }

    if (score < bestScore) {
      bestScore = score;
      bestWindow = window;
    }
  }
  return bestWindow;
}

function summarizeWindowGroup(group) {
  const start = new Date(group[0].start);
  const end = new Date(
    new Date(group[group.length - 1].start).getTime() + 3600000,
  );
  let totalTemp = 0;
  let totalWind = 0;
  let totalCloud = 0;
  let maxPrecip = 0;
  group.forEach((w) => {
    totalTemp += w.weather.temp_c;
    totalWind += w.weather.wind_kmh;
    totalCloud += w.weather.cloud_pct;
    if (w.weather.precip_mm > maxPrecip) {
      maxPrecip = w.weather.precip_mm;
    }
  });
  const avgTemp = totalTemp / group.length;
  const avgWind = totalWind / group.length;
  const avgCloud = totalCloud / group.length;
  return {
    start: start,
    end: end,
    weather: {
      temp_c: avgTemp,
      precip_mm: maxPrecip,
      wind_kmh: avgWind,
      cloud_pct: avgCloud,
    },
  };
}

function showResults(results) {
  const resultsSection = document.getElementById("results");
  const summaryDiv = document.getElementById("results-summary");
  const listDiv = document.getElementById("results-list");

  resultsSection.classList.remove("hidden");

  if (results.length === 0) {
    summaryDiv.textContent = "No hikes found matching your criteria.";
    listDiv.innerHTML = "";
    return;
  }

  summaryDiv.textContent = `Found ${results.length} hike${results.length > 1 ? "s" : ""} with good weather conditions.`;

  // Group windows by day for each hike
  const hikeCards = results
    .map((result) => {
      const windowsByDay = {};
      result.windows.forEach((window) => {
        const date = new Date(window.start);
        const dateStr = date.toLocaleDateString("en-GB", {
          weekday: "long",
          day: "numeric",
          month: "short",
        });

        if (!windowsByDay[dateStr]) {
          windowsByDay[dateStr] = [];
        }
        windowsByDay[dateStr].push(window);
      });

      const windowsHtml = Object.entries(windowsByDay)
        .map(([day, windows]) => {
          const grouped = groupConsecutiveWindows(windows);
          const summarized = grouped.map(summarizeWindowGroup);

          const bestWindow = findBestWindow(summarized);
          const otherWindows = summarized.filter((w) => w !== bestWindow);

          const bestWindowHtml = bestWindow
            ? `
                <div class="best-weather-window">
                    <span class="best-time">${bestWindow.start.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })} - ${bestWindow.end.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}</span>
                    <div class="weather-info">
                        ${Math.round(bestWindow.weather.temp_c)}C / ${bestWindow.weather.precip_mm.toFixed(1)}mm / ${Math.round(bestWindow.weather.wind_kmh)}km/h / ${Math.round(bestWindow.weather.cloud_pct)}% cloud
                    </div>
                </div>
            `
            : "";

          const otherWindowsHtml =
            otherWindows.length > 0
              ? `
                <div class="expand-more" onclick="this.classList.toggle('expanded'); this.nextElementSibling.classList.toggle('hidden');">
                    <span class="expand-text">Show ${otherWindows.length} other viable windows</span>
                    <span class="weather-toggle">▼</span>
                </div>
                <div class="additional-weather-content hidden">
                    ${otherWindows
                      .map((w) => {
                        const start = w.start;
                        const end = w.end;
                        const weather = w.weather;
                        const startTime = start.toLocaleTimeString("en-GB", {
                          hour: "2-digit",
                          minute: "2-digit",
                        });
                        const endTime = end.toLocaleTimeString("en-GB", {
                          hour: "2-digit",
                          minute: "2-digit",
                        });
                        const displayEndTime =
                          endTime === "00:00" ? "24:00" : endTime;

                        return `
                            <div class="window-time">
                                ${startTime} - ${displayEndTime}
                                <div class="weather-info">
                                    ${Math.round(weather.temp_c)}C / ${weather.precip_mm.toFixed(1)}mm / ${Math.round(weather.wind_kmh)}km/h / ${Math.round(weather.cloud_pct)}% cloud
                                </div>
                            </div>
                        `;
                      })
                      .join("")}
                </div>
            `
              : "";

          return `
            <div class="window-day">
                <h4>${day}</h4>
                ${bestWindowHtml}
                ${otherWindowsHtml}
            </div>
        `;
        })
        .join("");

      return `
            <div class="hike-card">
                <div class="hike-header">
                    <div>
                        <h3 class="hike-name">
                            <a href="${result.walkData.url}" target="_blank" class="hike-link">
                                ${result.walkData.name}
                            </a>
                        </h3>
                        <div class="hike-distance">${result.distance_from_user.toFixed(1)} km away</div>
                    </div>
                </div>
                <div class="hike-details">
                    ${result.walk.distance_km} km • ${result.walk.ascent_m}m ascent • ${result.walk.duration_h} hours
                </div>
                <div class="hike-summary">${result.walkData.summary}</div>
                <div class="hike-windows">
                    <h4>Good Weather Windows:</h4>
                    ${windowsHtml}
                </div>
            </div>
        `;
    })
    .join("");

  listDiv.innerHTML = hikeCards;

  // Scroll to results anchor to show the full Results section
  const anchor = document.getElementById("results-anchor");
  if (anchor) {
    anchor.scrollIntoView({ behavior: "smooth", block: "start" });
  } else {
    resultsSection.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

// Main search function
async function searchHikes() {
  // Save preferences
  savePreferences();

  // Get search parameters
  const userLat = parseFloat(document.getElementById("latitude").value);
  const userLon = parseFloat(document.getElementById("longitude").value);
  const radius = parseFloat(document.getElementById("radius").value);

  const selectedDates = Array.from(
    document.querySelectorAll(
      '#available-dates input[type="checkbox"]:checked',
    ),
  ).map((cb) => cb.value);

  if (selectedDates.length === 0) {
    showError("Please select at least one date.");
    return;
  }

  const filters = {
    minDuration: parseFloat(document.getElementById("min-duration").value),
    maxDuration: parseFloat(document.getElementById("max-duration").value),
    minDistance: parseFloat(document.getElementById("min-distance").value),
    maxDistance: parseFloat(document.getElementById("max-distance").value),
    maxAscent: parseInt(document.getElementById("max-ascent").value),
    maxRain: ((v) => (isNaN(v) ? 2 : v))(
      parseFloat(document.getElementById("max-precipitation-mm").value),
    ),
    maxWind: ((v) => (isNaN(v) ? 50 : v))(
      parseFloat(document.getElementById("max-wind-speed-kmh").value),
    ),
    minTemp: ((v) => (isNaN(v) ? -10 : v))(
      parseFloat(document.getElementById("min-temperature-c").value),
    ),
    maxTemp: ((v) => (isNaN(v) ? 40 : v))(
      parseFloat(document.getElementById("max-temperature-c").value),
    ),
    maxCloud: ((v) => (isNaN(v) ? 100 : v))(
      parseFloat(document.getElementById("max-cloud-cover-percent").value),
    ),
    startAfter: document.getElementById("start-after").value,
    finishBefore: document.getElementById("finish-before").value,
  };

  showLoading(true);
  document.getElementById("results").classList.add("hidden");

  try {
    // Filter walks by location and characteristics
    let nearbyWalks = filterWalksByLocation(
      state.indexData.walks,
      userLat,
      userLon,
      radius,
    );
    nearbyWalks = filterWalksByCharacteristics(nearbyWalks, filters);

    // Load walk data and filter windows
    const results = [];
    for (const walk of nearbyWalks) {
      const walkData = await loadWalkData(walk.id);
      if (!walkData) continue;

      const viableWindows = filterWindowsByWeather(
        walkData.windows,
        filters,
        selectedDates,
      );

      // Check if there are consecutive windows long enough for the hike duration
      if (viableWindows.length > 0) {
        const consecutiveGroups = groupConsecutiveWindows(viableWindows);
        const validGroups = consecutiveGroups.filter(
          (group) => group.length >= walk.duration_h,
        );

        if (validGroups.length > 0) {
          // Flatten valid groups back to individual windows for display
          const validWindows = validGroups.flat();
          results.push({
            walk,
            walkData,
            windows: validWindows,
            distance_from_user: walk.distance_from_user,
          });
        }
      }
    }

    // Sort by distance and limit results
    results.sort((a, b) => a.distance_from_user - b.distance_from_user);
    // Sort by distance and limit results
    results.sort((a, b) => a.distance_from_user - b.distance_from_user);
    const topResults = results.slice(0, 20);

    showResults(topResults);
  } catch (e) {
    showError("An error occurred while searching. Please try again.");
  } finally {
    showLoading(false);
  }
}

function getUserLocation() {
  const locationStatus = document.getElementById("location-status");
  const latitudeInput = document.getElementById("latitude");
  const longitudeInput = document.getElementById("longitude");
  const useLocationBtn = document.getElementById("use-location-btn");

  if (!navigator.geolocation) {
    locationStatus.innerHTML =
      '<span class="error">Geolocation not supported by this browser</span>';
    return;
  }

  useLocationBtn.disabled = true;
  useLocationBtn.textContent = "Getting location...";
  locationStatus.innerHTML =
    '<span class="info">Requesting location access...</span>';

  navigator.geolocation.getCurrentPosition(
    function (position) {
      const lat = position.coords.latitude;
      const lon = position.coords.longitude;
      const accuracy = Math.round(position.coords.accuracy);

      latitudeInput.value = lat.toFixed(4);
      longitudeInput.value = lon.toFixed(4);

      useLocationBtn.disabled = false;
      useLocationBtn.textContent = "Location Updated";
      locationStatus.innerHTML = `<span class="success">Location found (${accuracy}m accuracy)</span>`;

      // Reset button text after 3 seconds
      setTimeout(() => {
        useLocationBtn.textContent = "Use My Location";
      }, 3000);
    },
    function (error) {
      let errorMessage = "";
      let helpMessage = "";
      switch (error.code) {
        case error.PERMISSION_DENIED:
          errorMessage = "Location access denied";
          helpMessage = "Please allow location access and try again";
          break;
        case error.POSITION_UNAVAILABLE:
          errorMessage = "Location unavailable";
          helpMessage =
            window.location.protocol === "http:" &&
            window.location.hostname !== "localhost"
              ? "Try using HTTPS or localhost"
              : "Check if location services are enabled";
          break;
        case error.TIMEOUT:
          errorMessage = "Location request timed out";
          helpMessage = "Please try again";
          break;
        default:
          errorMessage = "Unknown error occurred";
          helpMessage = "Please try again";
          break;
      }
      useLocationBtn.disabled = false;
      useLocationBtn.textContent = "Use My Location";
      locationStatus.innerHTML = `<span class="error">${errorMessage}</span><br><small>${helpMessage}</small>`;
    },
    {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: 300000, // 5 minutes
    },
  );
}

// Initialize app
async function init() {
  // Generate date options
  generateDateOptions();

  // Load saved preferences
  loadPreferences();

  // Load index data
  const loaded = await loadIndexData();
  if (!loaded) {
    document.getElementById("search-btn").disabled = true;
    return;
  }

  // Set up event listeners
  const searchBtn = document.getElementById("search-btn");
  const locationBtn = document.getElementById("use-location-btn");

  if (searchBtn) {
    searchBtn.addEventListener("click", searchHikes);
  }

  if (locationBtn) {
    locationBtn.addEventListener("click", getUserLocation);
  }

  // Allow Enter key to trigger search
  document.addEventListener("keypress", (e) => {
    if (e.key === "Enter" && e.target.tagName === "INPUT") {
      searchHikes();
    }
  });
}

// Start the app
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
