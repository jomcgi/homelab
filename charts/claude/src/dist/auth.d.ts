import { Express } from "express";
import { IncomingMessage } from "http";
import { Socket } from "net";
export declare const ttydWss: import("ws").Server<
  typeof import("ws"),
  typeof IncomingMessage
>;
export declare function handleTtydUpgrade(
  req: IncomingMessage,
  socket: Socket,
  head: Buffer,
): void;
export declare function setupAuthRoutes(app: Express): void;
