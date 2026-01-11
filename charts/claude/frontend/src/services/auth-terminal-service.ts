import { spawn, ChildProcess } from 'child_process';
import { WebSocket as WsWebSocket, WebSocketServer } from 'ws';
import { createLogger } from './logger.js';
import { existsSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';
import type { Server } from 'http';
import type { IncomingMessage } from 'http';
import type { Socket } from 'net';

const logger = createLogger('AuthTerminalService');

const HOME = process.env.HOME || homedir();
const CLAUDE_BIN = join(HOME, '.npm-global', 'bin', 'claude');
const TTYD_PORT = 7681;

interface AuthStatus {
  authenticated: boolean;
  terminalActive: boolean;
}

/**
 * Service for managing Claude authentication terminal sessions using ttyd
 */
export class AuthTerminalService {
  private ttydProcess: ChildProcess | null = null;
  private wss: WebSocketServer | null = null;

  /**
   * Check if Claude is authenticated by looking for credentials
   */
  getAuthStatus(): AuthStatus {
    // Check for the credentials file that Claude creates after authentication
    const credentialsFile = join(HOME, '.claude', '.credentials.json');
    const authFile = join(HOME, '.claude', 'auth.json');

    // Either file indicates authentication
    const authenticated = existsSync(credentialsFile) || existsSync(authFile);

    logger.debug('Auth status check', {
      credentialsFile,
      authFile,
      authenticated,
      terminalActive: this.ttydProcess !== null
    });

    return {
      authenticated,
      terminalActive: this.ttydProcess !== null
    };
  }

  /**
   * Start ttyd with Claude for authentication
   */
  startTerminal(): boolean {
    // Clean up any existing process
    if (this.ttydProcess) {
      logger.warn('Killing existing ttyd process');
      this.ttydProcess.kill();
      this.ttydProcess = null;
    }

    try {
      logger.info('Starting ttyd on port', { port: TTYD_PORT });

      // Spawn ttyd with claude
      // -W: Start immediately (don't wait for initial connection)
      // -p: Port to listen on
      // -t: Set terminal title
      this.ttydProcess = spawn(
        'ttyd',
        [
          '-p', TTYD_PORT.toString(),
          '-W', // Start immediately
          '-t', 'titleFixed=Claude Authentication',
          CLAUDE_BIN,
        ],
        {
          cwd: HOME,
          env: { ...process.env, HOME },
          stdio: ['ignore', 'pipe', 'pipe'],
        }
      );

      this.ttydProcess.stdout?.on('data', (data) => {
        logger.debug('ttyd stdout', { output: data.toString().trim() });
      });

      this.ttydProcess.stderr?.on('data', (data) => {
        logger.debug('ttyd stderr', { output: data.toString().trim() });
      });

      this.ttydProcess.on('close', (code) => {
        logger.info('ttyd process exited', { code });
        this.ttydProcess = null;
      });

      this.ttydProcess.on('error', (err) => {
        logger.error('ttyd process error', err);
        this.ttydProcess = null;
      });

      return true;
    } catch (error) {
      logger.error('Failed to start ttyd', error);
      return false;
    }
  }

  /**
   * Stop the ttyd process
   */
  stopTerminal(): void {
    if (this.ttydProcess) {
      logger.info('Stopping ttyd process');
      this.ttydProcess.kill();
      this.ttydProcess = null;
    }
  }

  /**
   * Check if terminal is active
   */
  isTerminalActive(): boolean {
    return this.ttydProcess !== null;
  }

  /**
   * Set up WebSocket server for proxying to ttyd
   */
  setupWebSocket(server: Server): void {
    // Create WebSocket server for auth terminal
    this.wss = new WebSocketServer({
      noServer: true,
      perMessageDeflate: false,
      handleProtocols: (protocols) => {
        // Accept "tty" subprotocol if client requests it (ttyd always does)
        if (protocols.has('tty')) {
          return 'tty';
        }
        return false;
      },
    });

    this.wss.on('connection', (clientWs: WsWebSocket) => {
      logger.info('Client WebSocket connected, connecting to ttyd...');

      // Connect to ttyd using WebSocket protocol with "tty" subprotocol
      const ttydWs = new WsWebSocket(`ws://localhost:${TTYD_PORT}/ws`, ['tty'], {
        perMessageDeflate: false,
      });

      ttydWs.binaryType = 'arraybuffer';

      let ttydConnected = false;

      ttydWs.on('open', () => {
        logger.info('Connected to ttyd WebSocket');
        ttydConnected = true;
      });

      ttydWs.on('message', (data: Buffer, isBinary: boolean) => {
        // Forward ttyd messages to client
        if (clientWs.readyState === WsWebSocket.OPEN) {
          clientWs.send(data, { binary: isBinary });
        }
      });

      ttydWs.on('close', (code, reason) => {
        logger.info('ttyd WebSocket closed', { code, reason: reason.toString() });
        ttydConnected = false;
        if (clientWs.readyState === WsWebSocket.OPEN) {
          clientWs.close(code, reason.toString());
        }
      });

      ttydWs.on('error', (err) => {
        logger.error('ttyd WebSocket error', err);
        ttydConnected = false;
        if (clientWs.readyState === WsWebSocket.OPEN) {
          clientWs.close(1011, 'ttyd connection error');
        }
      });

      clientWs.on('message', (data: Buffer, isBinary: boolean) => {
        // Forward client messages to ttyd
        if (ttydWs.readyState === WsWebSocket.OPEN) {
          ttydWs.send(data, { binary: isBinary });
        }
      });

      clientWs.on('close', (code, reason) => {
        logger.info('Client WebSocket closed', { code, reason: reason.toString() });
        if (ttydConnected || ttydWs.readyState === WsWebSocket.CONNECTING) {
          ttydWs.close();
        }
      });

      clientWs.on('error', (err) => {
        logger.error('Client WebSocket error', err);
        if (ttydConnected || ttydWs.readyState === WsWebSocket.CONNECTING) {
          ttydWs.close();
        }
      });
    });

    // Handle upgrade requests for auth terminal
    server.on('upgrade', (req: IncomingMessage, socket: Socket, head: Buffer) => {
      const url = req.url || '';

      if (url.startsWith('/api/auth/terminal/ws')) {
        if (!this.isTerminalActive()) {
          logger.warn('No active terminal for WebSocket connection');
          socket.write('HTTP/1.1 503 Service Unavailable\r\n\r\n');
          socket.destroy();
          return;
        }

        logger.info('Handling WebSocket upgrade for auth terminal');
        this.wss!.handleUpgrade(req, socket, head, (ws) => {
          this.wss!.emit('connection', ws, req);
        });
      }
      // Other upgrade requests are handled elsewhere (streaming routes, etc.)
    });

    logger.info('Auth terminal WebSocket server initialized');
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
