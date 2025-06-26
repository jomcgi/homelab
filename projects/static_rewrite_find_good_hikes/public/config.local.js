// Local configuration for Find Good Hikes
// Copy this to config.js and update with your R2 URL

window.HIKES_CONFIG = {
    // UPDATE THIS: Replace with your actual R2 public URL
    // You can find this in your Cloudflare dashboard under R2 > your bucket > Settings
    // It will look something like: https://pub-abc123def456.r2.dev/
    dataUrl: 'https://YOUR-R2-PUBLIC-URL-HERE.r2.dev/',
    
    // Set to false when using real R2 data
    useLocalData: false,
    
    // Cache duration in minutes
    cacheMinutes: 60
};