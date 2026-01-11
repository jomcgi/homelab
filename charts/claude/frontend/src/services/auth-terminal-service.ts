import { spawn, IPty } from 'node-pty';
import { createLogger } from './logger.js';
import { existsSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';

const logger = createLogger('AuthTerminalService');

interface AuthStatus {
  authenticated: boolean;
  terminalActive: boolean;
}

/**
 * Service for managing Claude authentication terminal sessions
 */
export class AuthTerminalService {
  private pty: IPty | null = null;
  private clients: Set<WebSocket> = new Set();

  /**
   * Check if Claude is authenticated by looking for OAuth tokens
   */
  getAuthStatus(): AuthStatus {
    const claudeDir = join(homedir(), '.claude');
    const authFile = join(claudeDir, '.credentials.json');

    // Check for the credentials file that Claude creates after authentication
    const authenticated = existsSync(authFile);

    logger.debug('Auth status check', {
      claudeDir,
      authFile,
      authenticated,
      terminalActive: this.pty !== null
    });

    return {
      authenticated,
      terminalActive: this.pty !== null
    };
  }

  /**
   * Start an interactive terminal session for Claude authentication
   */
  startTerminal(): boolean {
    if (this.pty) {
      logger.warn('Terminal already active');
      return true;
    }

    try {
      // Spawn an interactive Claude session for authentication
      this.pty = spawn('claude', [], {
        name: 'xterm-256color',
        cols: 80,
        rows: 24,
        cwd: homedir(),
        env: {
          ...process.env,
          TERM: 'xterm-256color',
          COLORTERM: 'truecolor'
        }
      });

      logger.info('Auth terminal started', { pid: this.pty.pid });

      // Handle PTY data
      this.pty.onData((data) => {
        this.broadcastToClients('0' + data); // ttyd protocol: '0' prefix for output
      });

      // Handle PTY exit
      this.pty.onExit(({ exitCode }) => {
        logger.info('Auth terminal exited', { exitCode });
        this.pty = null;
        // Notify clients that terminal closed
        this.broadcastToClients('\r\n\x1b[33mTerminal session ended.\x1b[0m\r\n');
      });

      return true;
    } catch (error) {
      logger.error('Failed to start auth terminal', error);
      return false;
    }
  }

  /**
   * Stop the active terminal session
   */
  stopTerminal(): void {
    if (this.pty) {
      logger.info('Stopping auth terminal', { pid: this.pty.pid });
      this.pty.kill();
      this.pty = null;
    }

    // Close all client connections
    for (const client of this.clients) {
      try {
        client.close();
      } catch (e) {
        // Ignore close errors
      }
    }
    this.clients.clear();
  }

  /**
   * Handle a new WebSocket client connection
   */
  handleClient(ws: WebSocket): void {
    if (!this.pty) {
      logger.warn('No active terminal for client connection');
      ws.close();
      return;
    }

    this.clients.add(ws);
    logger.debug('Client connected to auth terminal', { clientCount: this.clients.size });

    // Handle incoming messages from client (ttyd protocol)
    ws.addEventListener('message', (event) => {
      const data = event.data;

      // Handle initial auth message (JSON with dimensions)
      if (typeof data === 'string') {
        try {
          const parsed = JSON.parse(data);
          if (parsed.columns && parsed.rows) {
            this.pty?.resize(parsed.columns, parsed.rows);
            logger.debug('Terminal resized', { cols: parsed.columns, rows: parsed.rows });
            return;
          }
        } catch {
          // Not JSON, treat as regular input
        }
      }

      // Handle binary or string input (ttyd protocol)
      let inputData: string;
      if (data instanceof ArrayBuffer) {
        const view = new Uint8Array(data);
        const messageType = view[0];
        const payload = new TextDecoder().decode(view.slice(1));

        if (messageType === 48) { // '0' - INPUT
          inputData = payload;
        } else if (messageType === 49) { // '1' - RESIZE
          try {
            const resize = JSON.parse(payload);
            this.pty?.resize(resize.columns, resize.rows);
            logger.debug('Terminal resized', { cols: resize.columns, rows: resize.rows });
          } catch (e) {
            logger.warn('Failed to parse resize message', e);
          }
          return;
        } else {
          return;
        }
      } else if (typeof data === 'string' && data.length > 0) {
        const messageType = data[0];
        const payload = data.substring(1);

        if (messageType === '0') { // INPUT
          inputData = payload;
        } else if (messageType === '1') { // RESIZE
          try {
            const resize = JSON.parse(payload);
            this.pty?.resize(resize.columns, resize.rows);
          } catch (e) {
            logger.warn('Failed to parse resize message', e);
          }
          return;
        } else {
          return;
        }
      } else {
        return;
      }

      // Write input to PTY
      if (inputData && this.pty) {
        this.pty.write(inputData);
      }
    });

    // Handle client disconnect
    ws.addEventListener('close', () => {
      this.clients.delete(ws);
      logger.debug('Client disconnected from auth terminal', { clientCount: this.clients.size });
    });

    ws.addEventListener('error', (error) => {
      logger.error('WebSocket error', error);
      this.clients.delete(ws);
    });
  }

  /**
   * Broadcast data to all connected clients
   */
  private broadcastToClients(data: string): void {
    for (const client of this.clients) {
      try {
        if (client.readyState === WebSocket.OPEN) {
          client.send(data);
        }
      } catch (e) {
        logger.warn('Failed to send to client', e);
      }
    }
  }

  /**
   * Check if terminal is active
   */
  isTerminalActive(): boolean {
    return this.pty !== null;
  }
}

// Singleton instance
let instance: AuthTerminalService | null = null;

export function getAuthTerminalService(): AuthTerminalService {
  if (!instance) {
    instance = new AuthTerminalService();
  }
  return instance;
}
