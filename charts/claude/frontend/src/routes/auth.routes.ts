import { Router } from 'express';
import { WebSocketServer, WebSocket } from 'ws';
import { createLogger } from '@/services/logger.js';
import { getAuthTerminalService } from '@/services/auth-terminal-service.js';
import type { Server } from 'http';

const logger = createLogger('AuthRoutes');

export function createAuthRoutes(): Router {
  const router = Router();
  const authService = getAuthTerminalService();

  // Get authentication status
  router.get('/status', (_req, res) => {
    try {
      const status = authService.getAuthStatus();
      logger.debug('Auth status requested', status);
      res.json(status);
    } catch (error) {
      logger.error('Failed to get auth status', error);
      res.status(500).json({ error: 'Failed to get auth status' });
    }
  });

  // Start authentication terminal
  router.post('/start', (_req, res) => {
    try {
      const success = authService.startTerminal();
      if (success) {
        logger.info('Auth terminal started successfully');
        res.json({ success: true });
      } else {
        res.status(500).json({ success: false, error: 'Failed to start terminal' });
      }
    } catch (error) {
      logger.error('Failed to start auth terminal', error);
      res.status(500).json({ success: false, error: 'Failed to start terminal' });
    }
  });

  // Stop authentication terminal
  router.post('/stop', (_req, res) => {
    try {
      authService.stopTerminal();
      logger.info('Auth terminal stopped');
      res.json({ success: true });
    } catch (error) {
      logger.error('Failed to stop auth terminal', error);
      res.status(500).json({ success: false, error: 'Failed to stop terminal' });
    }
  });

  return router;
}

/**
 * Set up WebSocket server for auth terminal
 * This should be called after the HTTP server is created
 */
export function setupAuthWebSocket(server: Server): void {
  const wss = new WebSocketServer({
    server,
    path: '/api/auth/terminal/ws'
  });

  const authService = getAuthTerminalService();

  wss.on('connection', (ws: WebSocket, req) => {
    logger.info('New auth terminal WebSocket connection', {
      remoteAddress: req.socket.remoteAddress
    });

    // Check if terminal is active
    if (!authService.isTerminalActive()) {
      logger.warn('No active terminal for WebSocket connection');
      ws.close(1000, 'No active terminal');
      return;
    }

    // Verify protocol
    const protocol = req.headers['sec-websocket-protocol'];
    if (protocol !== 'tty') {
      logger.warn('Invalid WebSocket protocol', { protocol });
      // Still allow connection but log warning
    }

    authService.handleClient(ws as unknown as globalThis.WebSocket);
  });

  wss.on('error', (error) => {
    logger.error('Auth WebSocket server error', error);
  });

  logger.info('Auth terminal WebSocket server initialized on /api/auth/terminal/ws');
}
