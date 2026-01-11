import { Router } from "express";
import { createLogger } from "@/services/logger.js";
import { getAuthTerminalService } from "@/services/auth-terminal-service.js";
import type { Server } from "http";

const logger = createLogger("AuthRoutes");

export function createAuthRoutes(): Router {
  const router = Router();
  const authService = getAuthTerminalService();

  // Get authentication status
  router.get("/status", (_req, res) => {
    try {
      const status = authService.getAuthStatus();
      logger.debug("Auth status requested", status);
      res.json(status);
    } catch (error) {
      logger.error("Failed to get auth status", error);
      res.status(500).json({ error: "Failed to get auth status" });
    }
  });

  // Start authentication terminal (spawns ttyd with Claude)
  router.post("/start", (_req, res) => {
    try {
      const success = authService.startTerminal();
      if (success) {
        // Give ttyd a moment to start
        setTimeout(() => {
          logger.info("Auth terminal started successfully");
          res.json({
            success: true,
            message: "Terminal started. Connect to /api/auth/terminal/ws",
          });
        }, 500);
      } else {
        res
          .status(500)
          .json({ success: false, error: "Failed to start terminal" });
      }
    } catch (error) {
      logger.error("Failed to start auth terminal", error);
      res
        .status(500)
        .json({ success: false, error: "Failed to start terminal" });
    }
  });

  // Stop authentication terminal
  router.post("/stop", (_req, res) => {
    try {
      authService.stopTerminal();
      logger.info("Auth terminal stopped");
      res.json({ success: true });
    } catch (error) {
      logger.error("Failed to stop auth terminal", error);
      res
        .status(500)
        .json({ success: false, error: "Failed to stop terminal" });
    }
  });

  return router;
}

/**
 * Set up WebSocket server for auth terminal
 * This should be called after the HTTP server is created
 */
export function setupAuthWebSocket(server: Server): void {
  const authService = getAuthTerminalService();
  authService.setupWebSocket(server);
  logger.info("Auth terminal WebSocket initialized");
}
