# Trips Web App

Interactive trip viewer for exploring travel routes and photos.

## Features

- **Photo Timeline** - Scroll through photos with playback controls
- **Route Visualization** - See routes on an interactive map (MapLibre)
- **Real-time Sync** - WebSocket updates as new photos are added
- **Mobile-friendly** - Responsive design with touch navigation

## Tech Stack

- React 18 + TypeScript
- Vite for bundling
- MapLibre GL for maps
- TailwindCSS for styling

## Development

```bash
# Install dependencies
pnpm install

# Start dev server
pnpm dev
```

The app connects to the trips API (`trips.jomcgi.dev/api`) for photo and route data.

## Deployment

Deployed to Cloudflare Pages via GitHub Actions. See `.github/workflows/cf-pages-deploy-trips.yaml`.

## Related

- `services/trips_api/` - Backend API serving photo data
- `scripts/publish-trip-images/` - CLI for uploading trip photos
