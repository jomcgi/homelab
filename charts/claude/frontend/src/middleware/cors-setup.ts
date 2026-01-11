import cors from 'cors';

export function createCorsMiddleware() {
  return cors({
    origin: true, // Allow all origins
    credentials: true // Allow credentials
  });
}