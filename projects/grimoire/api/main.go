package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()

	projectID := requireEnv("GCP_PROJECT_ID")
	firestoreDB := requireEnv("FIRESTORE_DATABASE")
	cfAccessTeam := requireEnv("CF_ACCESS_TEAM")

	fs, err := newFirestoreClient(ctx, projectID, firestoreDB)
	if err != nil {
		log.Fatalf("firestore: %v", err)
	}
	defer fs.Close()

	mux := http.NewServeMux()

	// Health check (unauthenticated — Cloud Run needs this).
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	// All /api routes require CF Access authentication.
	api := http.NewServeMux()

	registerCampaignRoutes(api, fs)
	registerSessionRoutes(api, fs)
	registerCharacterRoutes(api, fs)
	registerEncounterRoutes(api, fs)
	registerDiceRoutes(api, fs)
	registerFeedRoutes(api, fs)

	mux.Handle("/api/", cfAccessMiddleware(cfAccessTeam, api))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		<-ctx.Done()
		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer shutdownCancel()
		srv.Shutdown(shutdownCtx)
	}()

	log.Printf("grimoire-api listening on :%s", port)
	if err := srv.ListenAndServe(); err != http.ErrServerClosed {
		log.Fatalf("server: %v", err)
	}
}

func requireEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		log.Fatalf("required env var %s is not set", key)
	}
	return v
}
