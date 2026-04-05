import {
  WebTracerProvider,
  BatchSpanProcessor,
} from "@opentelemetry/sdk-trace-web";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { DocumentLoadInstrumentation } from "@opentelemetry/instrumentation-document-load";
import { FetchInstrumentation } from "@opentelemetry/instrumentation-fetch";
import { Resource } from "@opentelemetry/resources";
import {
  ATTR_SERVICE_NAME,
  ATTR_SERVICE_VERSION,
} from "@opentelemetry/semantic-conventions";
import { registerInstrumentations } from "@opentelemetry/instrumentation";

export function initTelemetry() {
  const resource = new Resource({
    [ATTR_SERVICE_NAME]: "monolith-frontend",
    [ATTR_SERVICE_VERSION]: "1.0.0",
  });

  const exporter = new OTLPTraceExporter({
    url: "/otel/v1/traces",
  });

  const provider = new WebTracerProvider({
    resource,
    spanProcessors: [new BatchSpanProcessor(exporter)],
  });

  provider.register();

  registerInstrumentations({
    instrumentations: [
      new DocumentLoadInstrumentation(),
      new FetchInstrumentation({
        // Only trace API calls to our backend, not external resources
        ignoreUrls: [/\/otel\//, /fonts\.googleapis/, /fonts\.gstatic/],
        // Propagate W3C trace context to backend for distributed tracing
        propagateTraceHeaderCorsUrls: [/.*/],
      }),
    ],
  });
}
