package main

import (
	"net/http"
	"os"
	"strings"
)

// uiDir is the directory containing the built UI assets.
// Configurable via UI_DIR environment variable for flexibility.
var uiDir = getUIDir()

func getUIDir() string {
	if dir := os.Getenv("UI_DIR"); dir != "" {
		return dir
	}
	return "/opt/ui"
}

// registerUI mounts the UI assets at "/" on the given mux.
// API routes must be registered before calling this function.
func registerUI(mux *http.ServeMux) {
	uiContent := os.DirFS(uiDir)
	fileServer := http.FileServer(http.FS(uiContent))

	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/")
		if path == "" {
			path = "index.html"
		}

		// If the file exists, serve it directly.
		f, err := uiContent.Open(path)
		if err != nil {
			// SPA fallback: serve index.html for any unknown route.
			r.URL.Path = "/"
			fileServer.ServeHTTP(w, r)
			return
		}
		f.Close()
		fileServer.ServeHTTP(w, r)
	})
}
