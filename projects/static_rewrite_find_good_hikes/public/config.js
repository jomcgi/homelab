// Configuration file for Find Good Hikes
// This file can be updated without rebuilding the entire app

window.HIKES_CONFIG = {
    // R2 data URL - update this to your actual R2 public URL
    // Example: https://pub-abc123.r2.dev/
    dataUrl: 'https://hikes-data.example.com/',
    
    // Fallback to local data for development
    useLocalData: window.location.hostname === 'localhost',
    
    // Cache duration in minutes
    cacheMinutes: 60
};