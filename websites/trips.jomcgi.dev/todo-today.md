# Trips App Improvements

## TODO TODAY
- [ ] **Deep linking** - Sync URL with current frame (`?frame=500`) for shareability, allow filtering / sharing by tag (`?tags=hotspring`)
- [ ] **Photo fullscreen** - Click to expand photo, escape/click to close
- [ ] **Swipe gestures** - Left/right swipe on mobile to navigate photos
- [ ] **Fix WebSocket reconnect** - Don't hijack view when WS reconnects; preserve user's position
- [ ] **Multi-day route distinction** - Color-code routes by day and offset overlapping segments so parallel routes appear side-by-side rather than stacked
- [ ] **Event tags** - Support filtering and navigation by tags (e.g., `?tags=hotspring,buffalo`); backend adding `tags: list[tag]` to images for grouping related moments