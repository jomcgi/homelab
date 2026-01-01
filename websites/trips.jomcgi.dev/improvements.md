# Trips App Improvements

## High Priority

- [ ] **Deep linking** - Sync URL with current frame (`?frame=500`) for shareability
- [ ] **Photo fullscreen** - Click to expand photo, escape/click to close
- [ ] **Swipe gestures** - Left/right swipe on mobile to navigate photos
- [ ] **Fix WebSocket reconnect** - Don't hijack view when WS reconnects; preserve user's position
- [ ] **Multi-day route distinction** - Color-code routes by day and offset overlapping segments so parallel routes appear side-by-side rather than stacked
- [ ] **Event tags** - Support filtering and navigation by tags (e.g., `?tags=hotspring,buffalo`); backend adding `tags: list[tag]` to images for grouping related moments

## Medium Priority

- [ ] **Trip stats** - Show distance traveled, elapsed time, current speed/elevation
- [ ] **Map style toggle** - Add satellite/terrain/street view options
- [ ] **Mobile header** - Show trip title on mobile (currently hidden)
- [ ] **Loading indicator** - Show spinner when next image is loading during fast scrub

## Nice to Have

- [ ] **Dark mode** - Theme toggle for night viewing
- [ ] **Elevation profile** - Small chart showing terrain changes along route
- [ ] **Photo gallery view** - Grid layout alternative to filmstrip
- [ ] **Multi-trip support** - Trip selector for archived trips
- [ ] **GPX export** - Download route as GPX file
- [ ] **Social sharing** - Share button with OG preview image
