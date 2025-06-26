// app.js - Find Good Hikes Static Site

// State management
const state = {
    indexData: null,
    walkCache: new Map(),
    searchResults: []
};

// Configuration
const CONFIG = {
    // Use config.js settings or fallback to defaults
    dataPath: window.HIKES_CONFIG?.useLocalData ? 'data/' : (window.HIKES_CONFIG?.dataUrl || 'https://hikes-data.example.com/'),
    localStorageKey: 'find-good-hikes-preferences',
    cacheMinutes: window.HIKES_CONFIG?.cacheMinutes || 60
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
        maxRain: document.getElementById('max-rain').value,
        maxWind: document.getElementById('max-wind').value,
        minTemp: document.getElementById('min-temp').value,
        maxTemp: document.getElementById('max-temp').value,
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
    const container = document.getElementById('date-selector');
    container.innerHTML = '';
    
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    for (let i = 0; i < 7; i++) {
        const date = new Date(today);
        date.setDate(today.getDate() + i);
        
        const dateStr = date.toISOString().split('T')[0];
        const dayName = date.toLocaleDateString('en-GB', { weekday: 'short' });
        const dayNum = date.getDate();
        const month = date.toLocaleDateString('en-GB', { month: 'short' });
        
        const option = document.createElement('div');
        option.className = 'date-option';
        option.innerHTML = `
            <input type="checkbox" id="date-${dateStr}" value="${dateStr}" ${i < 3 ? 'checked' : ''}>
            <label for="date-${dateStr}">
                <strong>${dayName}</strong><br>
                ${dayNum} ${month}
            </label>
        `;
        container.appendChild(option);
    }
}

// Data loading
async function loadIndexData() {
    try {
        const response = await fetch(CONFIG.dataPath + 'index.json');
        if (!response.ok) throw new Error('Failed to load index data');
        
        state.indexData = await response.json();
        
        // Update timestamp
        const timestamp = new Date(state.indexData.generated_at);
        document.getElementById('data-timestamp').textContent = timestamp.toLocaleString();
        
        // Check if data is stale (>2 hours old)
        const ageHours = (Date.now() - timestamp) / (1000 * 60 * 60);
        if (ageHours > 2) {
            showError('Warning: Weather data is more than 2 hours old. Results may be outdated.');
        }
        
        return true;
    } catch (e) {
        showError('Failed to load hiking data. Please try again later.');
        console.error('Failed to load index:', e);
        return false;
    }
}

async function loadWalkData(walkId) {
    // Check cache first
    if (state.walkCache.has(walkId)) {
        return state.walkCache.get(walkId);
    }
    
    try {
        const response = await fetch(`${CONFIG.dataPath}walks/${walkId}.json`);
        if (!response.ok) return null;
        
        const data = await response.json();
        state.walkCache.set(walkId, data);
        return data;
    } catch (e) {
        console.error(`Failed to load walk ${walkId}:`, e);
        return null;
    }
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
        
        const windowsHtml = Object.entries(windowsByDay).map(([day, windows]) => `
            <div class="window-day">
                <h4>${day}</h4>
                <div class="window-times">
                    ${windows.map(w => {
                        const start = new Date(w.start);
                        const weather = w.weather;
                        return `
                            <div class="window-time">
                                ${start.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}
                                <div class="weather-info">
                                    ${Math.round(weather.temp_c)}°C, 
                                    ${weather.precip_mm}mm rain, 
                                    ${Math.round(weather.wind_kmh)}km/h wind
                                </div>
                            </div>
                        `;
                    }).join('')}
                </div>
            </div>
        `).join('');
        
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
}

// Main search function
async function searchHikes() {
    // Save preferences
    savePreferences();
    
    // Get search parameters
    const userLat = parseFloat(document.getElementById('latitude').value);
    const userLon = parseFloat(document.getElementById('longitude').value);
    const radius = parseFloat(document.getElementById('radius').value);
    
    const selectedDates = Array.from(document.querySelectorAll('#date-selector input[type="checkbox"]:checked'))
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
        maxRain: parseFloat(document.getElementById('max-rain').value),
        maxWind: parseFloat(document.getElementById('max-wind').value),
        minTemp: parseFloat(document.getElementById('min-temp').value),
        maxTemp: parseFloat(document.getElementById('max-temp').value),
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

// Initialize app
async function init() {
    // Generate date options
    generateDateOptions();
    
    // Load saved preferences
    loadPreferences();
    
    // Load index data
    const loaded = await loadIndexData();
    if (!loaded) {
        document.getElementById('search-btn').disabled = true;
        return;
    }
    
    // Set up event listeners
    document.getElementById('search-btn').addEventListener('click', searchHikes);
    
    // Allow Enter key to trigger search
    document.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && e.target.tagName === 'INPUT') {
            searchHikes();
        }
    });
}

// Start the app
document.addEventListener('DOMContentLoaded', init);