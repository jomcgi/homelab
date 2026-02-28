package main

import (
	"fmt"
	"os"

	"go.uber.org/zap"

	"github.com/jomcgi/homelab/services/signoz_mcp_server/internal/client"
	"github.com/jomcgi/homelab/services/signoz_mcp_server/internal/config"
	"github.com/jomcgi/homelab/services/signoz_mcp_server/internal/handler/tools"
	"github.com/jomcgi/homelab/services/signoz_mcp_server/internal/logger"
	mcpserver "github.com/jomcgi/homelab/services/signoz_mcp_server/internal/mcp-server"
	"github.com/jomcgi/homelab/services/signoz_mcp_server/pkg/dashboard"
)

func main() {
	cfg, err := config.LoadConfig()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load config: %v\n", err)
		os.Exit(1)
	}

	if err := cfg.ValidateConfig(); err != nil {
		fmt.Fprintf(os.Stderr, "Configuration validation failed: %v\n", err)
		os.Exit(1)
	}

	log, err := logger.NewLogger(logger.LogLevel(cfg.LogLevel))
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize logger: %v\n", err)
		os.Exit(1)
	}

	log.Info("Starting SigNoz MCP Server",
		zap.String("log_level", cfg.LogLevel),
		zap.String("transport_mode", cfg.TransportMode))

	sigNozClient := client.NewClient(log, cfg.URL, cfg.APIKey)
	handler := tools.NewHandler(log, sigNozClient, cfg.URL)

	dashboard.InitClickhouseSchema()

	if err := mcpserver.NewMCPServer(log, handler, cfg).Start(); err != nil {
		log.Fatal(fmt.Sprintf("Failed to start server: %v", err))
	}
}
