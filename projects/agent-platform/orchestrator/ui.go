package main

import (
	"io/fs"
	"net/http"
	"strings"

	orchestratorui "github.com/jomcgi/homelab/projects/agent-platform/orchestrator/ui"
)

// registerUI mounts the embedded Vite build at "/" on the given mux.
// API routes must be registered before calling this function.
func registerUI(mux *http.ServeMux) {
	uiContent, err := fs.Sub(orchestratorui.FS, "dist")
	if err != nil {
		panic("failed to sub dist from embedded UI FS: " + err.Error())
	}
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
