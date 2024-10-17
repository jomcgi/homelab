import { serve } from "https://deno.land/std@0.140.0/http/server.ts";
import { serveFile } from "https://deno.land/std@0.140.0/http/file_server.ts";

const port = 8000;

async function handleRequest(request: Request): Promise<Response> {
  const url = new URL(request.url);
  const pathname = url.pathname;

  // Serve index.html for the root path
  if (pathname === "/" || pathname === "/index.html") {
    return await serveFile(request, "./index.html");
  }

  // Serve static files from the public directory
  if (pathname.startsWith("/static/")) {
    return await serveFile(request, `.${pathname}`);
  }

  // Serve the bundled JavaScript file
  if (pathname.endsWith(".js")) {
    return await serveFile(request, `./dist${pathname}`);
  }

  // If no matching route, return 404
  return new Response("Not Found", { status: 404 });
}

console.log(`HTTP server running on http://localhost:${port}`);
await serve(handleRequest, { port });