/**
 * OpenTelemetry Instrumentation Setup
 *
 * This file MUST be imported at the very top of server.ts, before any other imports,
 * to ensure all libraries are properly instrumented.
 *
 * Uses environment variables injected by Kyverno:
 * - OTEL_EXPORTER_OTLP_ENDPOINT: signoz-otel-collector.signoz.svc.cluster.local:4317
 * - OTEL_EXPORTER_OTLP_PROTOCOL: grpc
 */

import { NodeSDK } from "@opentelemetry/sdk-node";
import { getNodeAutoInstrumentations } from "@opentelemetry/auto-instrumentations-node";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-grpc";
import { Resource } from "@opentelemetry/resources";
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from "@opentelemetry/semantic-conventions";
import { diag, DiagConsoleLogger, DiagLogLevel } from "@opentelemetry/api";

// Enable debug logging for OTEL if LOG_LEVEL is debug
if (process.env.LOG_LEVEL === "debug") {
  diag.setLogger(new DiagConsoleLogger(), DiagLogLevel.INFO);
}

// Check if OTEL endpoint is configured (injected by Kyverno)
const otlpEndpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT;

let sdk: NodeSDK | null = null;

if (otlpEndpoint) {
  console.log(`[OTEL] Initializing with endpoint: ${otlpEndpoint}`);

  // Create trace exporter
  const traceExporter = new OTLPTraceExporter({
    url: `http://${otlpEndpoint}`,
  });

  // Configure the SDK
  sdk = new NodeSDK({
    resource: new Resource({
      [ATTR_SERVICE_NAME]: "cui-server",
      [ATTR_SERVICE_VERSION]: process.env.npm_package_version || "0.0.0",
    }),
    traceExporter,
    instrumentations: [
      getNodeAutoInstrumentations({
        // Disable fs instrumentation to reduce noise
        "@opentelemetry/instrumentation-fs": {
          enabled: false,
        },
        // Configure HTTP instrumentation
        "@opentelemetry/instrumentation-http": {
          enabled: true,
        },
        // Configure Express instrumentation
        "@opentelemetry/instrumentation-express": {
          enabled: true,
        },
      }),
    ],
  });

  // Start the SDK
  sdk.start();
  console.log("[OTEL] SDK started successfully");

  // Graceful shutdown
  process.on("SIGTERM", () => {
    sdk
      ?.shutdown()
      .then(() => console.log("[OTEL] SDK shut down successfully"))
      .catch((error) =>
        console.error("[OTEL] Error shutting down SDK:", error),
      );
  });
} else {
  console.log(
    "[OTEL] No OTEL_EXPORTER_OTLP_ENDPOINT configured, tracing disabled",
  );
}

export { sdk };
