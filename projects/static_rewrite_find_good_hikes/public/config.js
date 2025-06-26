// Configuration file for Find Good Hikes
// This file can be updated without rebuilding the entire app

window.HIKES_CONFIG = {
    // R2 data URL with custom domain and bucket path
    dataUrl: 'https://hike-assets.jomcgi.dev/jomcgi-hikes/',
    
    // Don't use local data - we have R2 working
    useLocalData: false,
    
    // Cache duration in minutes
    cacheMinutes: 30
};