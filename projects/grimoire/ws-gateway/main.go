package main

import (
	"context"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"nhooyr.io/websocket"
)

func main() {
	// Structured logging.
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	})))

	// Graceful shutdown context — created early so it can be passed to hub.Run.
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	// Configuration from environment.
	addr := envOr("LISTEN_ADDR", ":8080")
	redisAddr := envOr("REDIS_ADDR", "redis:6379")
	redisPassword := envOr("REDIS_PASSWORD", "")
	cfTeam := envOr("CF_ACCESS_TEAM", "")

	if cfTeam == "" {
		slog.Error("CF_ACCESS_TEAM is required")
		os.Exit(1)
	}

	// Initialize Cloudflare Access JWT validator.
	auth := NewCFAccessAuth(cfTeam)

	// Initialize Redis relay.
	redis, err := NewRedisRelay(redisAddr, redisPassword)
	if err != nil {
		slog.Error("failed to connect to Redis", "addr", redisAddr, "error", err)
		os.Exit(1)
	}
	defer redis.Close()

	// Initialize the connection hub.
	hub := NewHub(redis)
	go hub.Run(ctx)

	// Start Redis subscription in background — routes incoming messages
	// from other replicas to local clients.
	go redis.Subscribe(hub.HandleRedisMessage)

	// HTTP routes.
	mux := http.NewServeMux()

	mux.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
		handleWebSocket(w, r, hub, auth)
	})

	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})

	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		if err := redis.Ping(); err != nil {
			w.WriteHeader(http.StatusServiceUnavailable)
			w.Write([]byte("redis unhealthy"))
			return
		}
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("ok"))
	})

	server := &http.Server{
		Addr:         addr,
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 0, // WebSocket connections are long-lived
		IdleTimeout:  120 * time.Second,
	}

	go func() {
		slog.Info("ws-gateway listening", "addr", addr)
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			slog.Error("server error", "error", err)
			os.Exit(1)
		}
	}()

	<-ctx.Done()
	slog.Info("shutting down")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		slog.Error("shutdown error", "error", err)
	}
}

// handleWebSocket upgrades an HTTP request to WebSocket, authenticates via
// Cloudflare Access JWT, and registers the client with the hub.
func handleWebSocket(w http.ResponseWriter, r *http.Request, hub *Hub, auth *CFAccessAuth) {
	// Authenticate via Cloudflare Access JWT.
	email, err := auth.Validate(r)
	if err != nil {
		slog.Warn("auth failed", "error", err, "remote", r.RemoteAddr)
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}

	// Upgrade to WebSocket.
	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		// Cloudflare tunnel handles origin checking; we allow the
		// tunneled origin through.
		InsecureSkipVerify: true,
	})
	if err != nil {
		slog.Error("websocket upgrade failed", "error", err)
		return
	}

	client := NewClient(hub, conn, email)
	hub.register <- client

	// Use a dedicated context for the client pumps instead of the HTTP
	// request context, which may be cancelled after the upgrade.
	clientCtx, clientCancel := context.WithCancel(context.Background())
	defer clientCancel()
	go client.writePump(clientCtx)
	client.readPump(clientCtx)
}

// envOr returns the value of the named environment variable, or the fallback.
func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
