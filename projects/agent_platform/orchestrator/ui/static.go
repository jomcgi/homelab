// Package ui embeds the built Vite + React dashboard assets.
// The dist/ directory is produced by `vite build` and embedded at compile time.
package ui

import "embed"

// FS contains the embedded Vite build output (dist/).
//
//go:embed dist
var FS embed.FS
