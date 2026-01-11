import { Transform } from 'stream';

interface LogObject {
  level: number;
  time: number | string;
  msg: string;
  component?: string;
  requestId?: string;
  sessionId?: string;
  streamingId?: string;
  err?: {
    message?: string;
    stack?: string;
  };
  error?: {
    message?: string;
    stack?: string;
  };
  [key: string]: unknown;
}

const RESET = '\x1b[0m';
const GRAY = '\x1b[90m';
const BOLD = '\x1b[1m';
const BLUE = '\x1b[34m';

export class LogFormatter extends Transform {
  constructor() {
    super({
      writableObjectMode: true,
      transform(chunk: unknown, _encoding: string, callback: (error?: Error | null, data?: unknown) => void) {
        try {
          const logLine = String(chunk).trim();
          if (!logLine) {
            callback();
            return;
          }

          const log: LogObject = JSON.parse(logLine);
          const formatted = formatLog(log);
          callback(null, formatted + '\n');
        } catch (_err) {
          // If we can't parse it, pass it through as-is
          callback(null, chunk);
        }
      }
    });
  }
}

function formatLog(log: LogObject): string {
  // Format timestamp in 12-hour format with AM/PM
  const time = new Date(typeof log.time === 'string' ? log.time : log.time);
  const hours = time.getHours();
  const minutes = time.getMinutes().toString().padStart(2, '0');
  const seconds = time.getSeconds().toString().padStart(2, '0');
  const ampm = hours >= 12 ? 'PM' : 'AM';
  const displayHours = (hours % 12 || 12).toString().padStart(2, '0');
  const timestamp = `${displayHours}:${minutes}:${seconds} ${ampm}`;

  // Build the formatted message
  let formatted = `${GRAY}${timestamp}${RESET}`;

  // Add component in bold blue brackets if present
  if (log.component) {
    formatted += ` ${BOLD}${BLUE}[${log.component}]${RESET}`;
  }

  // Add the main message
  formatted += ` ${log.msg}`;

  // Add context fields (filter out only pino internals)
  const excludedFields = ['level', 'time', 'msg', 'component', 'pid', 'hostname', 'v'];
  const contextFields = Object.keys(log)
    .filter(key => !excludedFields.includes(key) && log[key] !== undefined && log[key] !== null);

  if (contextFields.length > 0) {
    const contextPairs = contextFields.map(key => {
      const value = log[key];
      
      // Special handling for error objects
      if ((key === 'err' || key === 'error') && typeof value === 'object' && value !== null && 'message' in value) {
        return `${key}="${(value as { message: string }).message}"`;
      }
      
      // Format based on value type
      if (typeof value === 'string') {
        return `${key}="${value}"`;
      } else if (typeof value === 'number' || typeof value === 'boolean') {
        return `${key}=${value}`;
      } else {
        // For objects and arrays, use JSON.stringify
        return `${key}=${JSON.stringify(value)}`;
      }
    });
    
    formatted += ` ${GRAY}${contextPairs.join(' ')}${RESET}`;
  }

  // Handle error stack traces
  if (log.err && typeof log.err === 'object' && 'stack' in log.err && log.err.stack) {
    formatted += `\n${log.err.stack}`;
  }

  return formatted;
}