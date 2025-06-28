// app.js - Find Good Hikes Static Site
import HIKES_CONFIG from './config.js?v=2';

// State management
const state = {
    indexData: null,
    walkCache: new Map(),
    searchResults: []
};

// Configuration
const CONFIG = {
    // Use config.js settings or fallback to defaults
    dataPath: HIKES_CONFIG?.useLocalData ? 'data/' : (HIKES_CONFIG?.dataUrl || 'https://hikes-data.example.com/'),
    localStorageKey: 'find-good-hikes-preferences',
    cacheMinutes: HIKES_CONFIG?.cacheMinutes || 60
};

// Utility functions
function savePreferences() {
    const prefs = {
        latitude: document.getElementById('latitude').value,
        longitude: document.getElementById('longitude').value,
        radius: document.getElementById('radius').value,
        minDuration: document.getElementById('min-duration').value,
        maxDuration: document.getElementById('max-duration').value,
        minDistance: document.getElementById('min-distance').value,
        maxDistance: document.getElementById('max-distance').value,
        maxAscent: document.getElementById('max-ascent').value,
        maxRain: document.getElementById('max-precipitation-mm').value,
        maxWind: document.getElementById('max-wind-speed-kmh').value,
        minTemp: document.getElementById('min-temperature-c').value,
        maxTemp: document.getElementById('max-temperature-c').value,
        startAfter: document.getElementById('start-after').value,
        finishBefore: document.getElementById('finish-before').value
    };
    localStorage.setItem(CONFIG.localStorageKey, JSON.stringify(prefs));
}

function loadPreferences() {
    const saved = localStorage.getItem(CONFIG.localStorageKey);
    if (!saved) return;
    
    try {
        const prefs = JSON.parse(saved);
        Object.entries(prefs).forEach(([key, value]) => {
            const elem = document.getElementById(key.replace(/([A-Z])/g, '-$1').toLowerCase());
            if (elem) elem.value = value;
        });
    } catch (e) {
        console.error('Failed to load preferences:', e);
    }
}

// Haversine distance calculation
function calculateDistance(lat1, lon1, lat2, lon2) {
    const R = 6371; // Earth's radius in km
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
        Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    return R * c;
}

// Date generation
function generateDateOptions() {
    const container = document.getElementById('available-dates');
    container.innerHTML = '';
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    for (let i = 0; i < 5; i++) {  // Changed to 5 days to match original
        const date = new Date(today);
        date.setDate(today.getDate() + i);
        
        const dateStr = date.toISOString().split('T')[0];
        const dayName = date.toLocaleDateString('en-GB', { weekday: 'long' });
        const dayNum = date.getDate();
        const month = date.toLocaleDateString('en-GB', { month: 'short' });
        
        const option = document.createElement('div');
        option.className = 'checkbox-group';  // Changed to match original class
        option.innerHTML = `
            <input type="checkbox" id="date-${dateStr}" name="available_dates" value="${dateStr}" ${i < 5 ? 'checked' : ''}>
            <label for="date-${dateStr}">
                ${dayName}, ${month} ${dayNum}
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
    // Window format: [timestamp, temp, precip, wind]
    
    const walks = [];
    const walkMap = new Map();
    
    for (const walkData of bundle.d) {
        const [id, lat, lng, duration_h, distance_km, ascent_m, name, url, summary, windows] = walkData;
        
        // Create index entry
        walks.push({
            id,
            lat,
            lng,
            duration_h,
            distance_km,
            ascent_m
        });
        
        // Create full walk data with expanded windows
        const expandedWindows = windows.map(w => {
            const [timestamp, temp_c, precip_mm, wind_kmh] = w;
            const startDate = new Date(timestamp * 1000);
            const endDate = new Date(startDate.getTime() + 3600000); // +1 hour
            
            return {
                start: startDate.toISOString(),
                end: endDate.toISOString(),
                weather: {
                    temp_c,
                    precip_mm,
                    wind_kmh,
                    cloud_pct: 50  // Default value since we removed it for space
                }
            };
        });
        
        walkMap.set(id, {
            name,
            url,
            summary,
            windows: expandedWindows
        });
    }
    
    return { walks, walkMap };
}

// Data loading
async function loadIndexData() {
    const bundlePath = `${CONFIG.dataPath}bundle.json.br`;
    
    try {
        console.log('Attempting to fetch:', bundlePath);
        const response = await fetch(bundlePath);
        
        if (!response.ok) {
            throw new Error(`Failed to load bundle: ${response.status} ${response.statusText}`);
        }
        
        console.log('Bundle fetch successful');
        
        const bundle = await response.json();
        
        // Parse bundle into index and walk data
        const { walks, walkMap } = parseBundleData(bundle);
        
        // Set up state
        state.indexData = {
            generated_at: bundle.g * 1000,  // Convert to milliseconds
            walks: walks
        };
        
        // Pre-populate walk cache with all data
        state.walkCache = walkMap;
        
        // Update timestamp
        const timestamp = new Date(state.indexData.generated_at);
        document.getElementById('data-timestamp').textContent = timestamp.toLocaleString();
        
        // Check if data is stale (>2 hours old)
        const ageHours = (Date.now() - timestamp) / (1000 * 60 * 60);
        if (ageHours > 2) {
            showError('Warning: Weather data is more than 2 hours old. Results may be outdated.');
        }
        
        return true;
    } catch (error) {
        console.error('Failed to load data bundle:', error);
        showError(`Failed to load hike data. The server returned an error: ${error.message}. Please try again later.`);
        return false;
    }
}


async function loadWalkData(walkId) {
    // All walk data is pre-loaded from the bundle
    if (state.walkCache.has(walkId)) {
        return state.walkCache.get(walkId);
    }
    
    // Walk not found in bundled data
    console.warn(`Walk ${walkId} not found in bundled data`);
    return null;
}

// Filtering functions
function filterWalksByLocation(walks, userLat, userLon, radius) {
    return walks.filter(walk => {
        const distance = calculateDistance(userLat, userLon, walk.lat, walk.lng);
        walk.distance_from_user = distance;
        return distance <= radius;
    }).sort((a, b) => a.distance_from_user - b.distance_from_user);
}

function filterWalksByCharacteristics(walks, filters) {
    return walks.filter(walk => {
        if (walk.duration_h < filters.minDuration || walk.duration_h > filters.maxDuration) return false;
        if (walk.distance_km < filters.minDistance || walk.distance_km > filters.maxDistance) return false;
        if (walk.ascent_m > filters.maxAscent) return false;
        return true;
    });
}

function filterWindowsByWeather(windows, filters, selectedDates) {
    const startHour = parseInt(filters.startAfter.split(':')[0]);
    const startMin = parseInt(filters.startAfter.split(':')[1]);
    const endHour = parseInt(filters.finishBefore.split(':')[0]);
    const endMin = parseInt(filters.finishBefore.split(':')[1]);
    
    return windows.filter(window => {
        const startTime = new Date(window.start);
        const dateStr = startTime.toISOString().split('T')[0];
        
        // Check if date is selected
        if (!selectedDates.includes(dateStr)) return false;
        
        // Check time constraints
        const hour = startTime.getHours();
        const min = startTime.getMinutes();
        if (hour < startHour || (hour === startHour && min < startMin)) return false;
        if (hour >= endHour || (hour === endHour && min >= endMin)) return false;
        
        // Check weather constraints
        const weather = window.weather;
        if (weather.precip_mm > filters.maxRain) return false;
        if (weather.wind_kmh > filters.maxWind) return false;
        if (weather.temp_c < filters.minTemp || weather.temp_c > filters.maxTemp) return false;
        
        return true;
    });
}

// UI functions
function showLoading(show) {
    document.getElementById('loading').classList.toggle('hidden', !show);
}

function showError(message) {
    const errorDiv = document.getElementById('error');
    errorDiv.textContent = message;
    errorDiv.classList.remove('hidden');
    setTimeout(() => errorDiv.classList.add('hidden'), 10000);
}

function groupConsecutiveWindows(windows) {
    if (!windows || windows.length === 0) {
        return [];
    }
    windows.sort((a, b) => new Date(a.start) - new Date(b.start));
    const grouped = [];
    let currentGroup = [windows[0]];
    for (let i = 1; i < windows.length; i++) {
        const prevEnd = new Date(currentGroup[currentGroup.length - 1].start).getTime() + 3600000;
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

function summarizeWindowGroup(group) {
    const start = new Date(group[0].start);
    const end = new Date(new Date(group[group.length - 1].start).getTime() + 3600000);
    let totalTemp = 0;
    let totalWind = 0;
    let totalCloud = 0;
    let maxPrecip = 0;
    group.forEach(w => {
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
            cloud_pct: avgCloud
        }
    };
}

function showResults(results) {
    const resultsSection = document.getElementById('results');
    const summaryDiv = document.getElementById('results-summary');
    const listDiv = document.getElementById('results-list');
    
    resultsSection.classList.remove('hidden');
    
    if (results.length === 0) {
        summaryDiv.textContent = 'No hikes found matching your criteria.';
        listDiv.innerHTML = '';
        return;
    }
    
    summaryDiv.textContent = `Found ${results.length} hike${results.length > 1 ? 's' : ''} with good weather conditions.`;
    
    // Group windows by day for each hike
    const hikeCards = results.map(result => {
        const windowsByDay = {};
        result.windows.forEach(window => {
            const date = new Date(window.start);
            const dateStr = date.toLocaleDateString('en-GB', { 
                weekday: 'long', 
                day: 'numeric', 
                month: 'short' 
            });
            
            if (!windowsByDay[dateStr]) {
                windowsByDay[dateStr] = [];
            }
            windowsByDay[dateStr].push(window);
        });
        
        const windowsHtml = Object.entries(windowsByDay).map(([day, windows]) => {
            const grouped = groupConsecutiveWindows(windows);
            const summarized = grouped.map(summarizeWindowGroup);

            return `
            <div class="window-day">
                <h4>${day}</h4>
                <div class="window-times">
                    ${summarized.map(w => {
                        const start = w.start;
                        const end = w.end;
                        const weather = w.weather;
                        const startTime = start.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
                        const endTime = end.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
                        const displayEndTime = endTime === '00:00' ? '24:00' : endTime;

                        return `
                            <div class="window-time">
                                ${startTime} - ${displayEndTime}
                                <div class="weather-info">
                                    🌡️ ${Math.round(weather.temp_c)}°C 💧 ${weather.precip_mm.toFixed(1)}mm 💨 ${Math.round(weather.wind_kmh)}km/h ☁️ ${Math.round(weather.cloud_pct)}%
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `}).join('');
        
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
    }).join('');
    
    listDiv.innerHTML = hikeCards;
    
    // Scroll to results anchor to show the full Results section
    const anchor = document.getElementById('results-anchor');
    if (anchor) {
        anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
        console.warn('Results anchor not found, falling back to results section');
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

// Main search function
async function searchHikes() {
    // Save preferences
    savePreferences();
    
    // Get search parameters
    const userLat = parseFloat(document.getElementById('latitude').value);
    const userLon = parseFloat(document.getElementById('longitude').value);
    const radius = parseFloat(document.getElementById('radius').value);
    
    const selectedDates = Array.from(document.querySelectorAll('#available-dates input[type="checkbox"]:checked'))
        .map(cb => cb.value);
    
    if (selectedDates.length === 0) {
        showError('Please select at least one date.');
        return;
    }
    
    const filters = {
        minDuration: parseFloat(document.getElementById('min-duration').value),
        maxDuration: parseFloat(document.getElementById('max-duration').value),
        minDistance: parseFloat(document.getElementById('min-distance').value),
        maxDistance: parseFloat(document.getElementById('max-distance').value),
        maxAscent: parseInt(document.getElementById('max-ascent').value),
        maxRain: parseFloat(document.getElementById('max-precipitation-mm').value) || 2,  // Default to 2mm if empty
        maxWind: parseFloat(document.getElementById('max-wind-speed-kmh').value) || 50,  // Default to 50km/h if empty
        minTemp: parseFloat(document.getElementById('min-temperature-c').value) || -10,  // Default to -10°C if empty
        maxTemp: parseFloat(document.getElementById('max-temperature-c').value) || 40,   // Default to 40°C if empty
        startAfter: document.getElementById('start-after').value,
        finishBefore: document.getElementById('finish-before').value
    };
    
    showLoading(true);
    document.getElementById('results').classList.add('hidden');
    
    try {
        // Filter walks by location and characteristics
        let nearbyWalks = filterWalksByLocation(state.indexData.walks, userLat, userLon, radius);
        nearbyWalks = filterWalksByCharacteristics(nearbyWalks, filters);
        
        // Load walk data and filter windows
        const results = [];
        for (const walk of nearbyWalks) {
            const walkData = await loadWalkData(walk.id);
            if (!walkData) continue;
            
            const viableWindows = filterWindowsByWeather(walkData.windows, filters, selectedDates);
            if (viableWindows.length > 0) {
                results.push({
                    walk,
                    walkData,
                    windows: viableWindows,
                    distance_from_user: walk.distance_from_user
                });
            }
        }
        
        // Sort by distance and limit results
        results.sort((a, b) => a.distance_from_user - b.distance_from_user);
        const topResults = results.slice(0, 20);
        
        showResults(topResults);
    } catch (e) {
        showError('An error occurred while searching. Please try again.');
        console.error('Search error:', e);
    } finally {
        showLoading(false);
    }
}

function getUserLocation() {
    const locationStatus = document.getElementById('location-status');
    const latitudeInput = document.getElementById('latitude');
    const longitudeInput = document.getElementById('longitude');
    const useLocationBtn = document.getElementById('use-location-btn');

    if (!navigator.geolocation) {
        locationStatus.innerHTML = '<span class="error">❌ Geolocation not supported by this browser</span>';
        return;
    }

    useLocationBtn.disabled = true;
    useLocationBtn.textContent = '🔄 Getting location...';
    locationStatus.innerHTML = '<span class="info">📍 Requesting location access...</span>';

    navigator.geolocation.getCurrentPosition(
        function(position) {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;
            const accuracy = Math.round(position.coords.accuracy);

            latitudeInput.value = lat.toFixed(4);
            longitudeInput.value = lon.toFixed(4);

            useLocationBtn.disabled = false;
            useLocationBtn.textContent = '✅ Location Updated';
            locationStatus.innerHTML = `<span class="success">✅ Location found (±${accuracy}m accuracy)</span>`;

            // Reset button text after 3 seconds
            setTimeout(() => {
                useLocationBtn.textContent = '📍 Use My Location';
            }, 3000);
        },
        function(error) {
            console.log('Geolocation error:', error);
            let errorMessage = '';
            let helpMessage = '';
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    errorMessage = '❌ Location access denied by user';
                    helpMessage = 'Please allow location access and try again';
                    break;
                case error.POSITION_UNAVAILABLE:
                    errorMessage = '❌ Location information unavailable';
                    helpMessage = window.location.protocol === 'http:' && window.location.hostname !== 'localhost' 
                        ? 'Try using HTTPS or localhost' 
                        : 'Check if location services are enabled';
                    break;
                case error.TIMEOUT:
                    errorMessage = '❌ Location request timed out';
                    helpMessage = 'Please try again';
                    break;
                default:
                    errorMessage = '❌ Unknown error occurred';
                    helpMessage = 'Please try again';
                    break;
            }
            useLocationBtn.disabled = false;
            useLocationBtn.textContent = '📍 Use My Location';
            locationStatus.innerHTML = `<span class="error">${errorMessage}</span><br><small>${helpMessage}</small>`;
        },
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 300000 // 5 minutes
        }
    );
}

// Initialize app
async function init() {
    console.log('Init function starting...');
    
    // Generate date options
    generateDateOptions();
    console.log('Date options generated');
    
    // Load saved preferences
    loadPreferences();
    
    // Load index data
    const loaded = await loadIndexData();
    if (!loaded) {
        document.getElementById('search-btn').disabled = true;
        return;
    }
    
    // Set up event listeners
    const searchBtn = document.getElementById('search-btn');
    const locationBtn = document.getElementById('use-location-btn');
    
    console.log('Search button found:', searchBtn);
    console.log('Location button found:', locationBtn);
    
    if (searchBtn) {
        searchBtn.addEventListener('click', searchHikes);
        console.log('Search button event listener attached');
    } else {
        console.error('Search button not found!');
    }
    
    if (locationBtn) {
        locationBtn.addEventListener('click', getUserLocation);
        console.log('Location button event listener attached');
    } else {
        console.error('Location button not found!');
    }
    
    // Allow Enter key to trigger search
    document.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
            searchHikes();
        }
    });
}

// Start the app
console.log('Setting up DOMContentLoaded listener...');
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        console.log('DOM loaded (via event), calling init...');
        init();
    });
} else {
    console.log('DOM already loaded, calling init immediately...');
    init();
}
