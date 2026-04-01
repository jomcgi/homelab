{{/*
cf-ingress.httproute generates an HTTPRoute with the ingress-tier label.

Usage:
  {{- include "cf-ingress.httproute" . }}

Required values:
  name: resource name
  tier: "trusted" or "public"
  hostname: "app.jomcgi.dev"
  serviceName: "my-service"
  servicePort: 80
  gateway:
    name: "cloudflare-ingress"
    namespace: "envoy-gateway-system"

Optional values:
  pathPrefix: "/todo" (defaults to "/")
  rewritePrefix: "/public/" (rewrites matched pathPrefix to this value)
*/}}
{{- define "cf-ingress.httproute" -}}
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: {{ .name }}
  labels:
    ingress-tier: {{ .tier }}
spec:
  parentRefs:
    - name: {{ .gateway.name }}
      namespace: {{ .gateway.namespace }}
  hostnames:
    - {{ .hostname | quote }}
  rules:
    - matches:
        - path:
            type: PathPrefix
            value: {{ .pathPrefix | default "/" }}
      {{- if .rewritePrefix }}
      filters:
        - type: URLRewrite
          urlRewrite:
            path:
              type: ReplacePrefixMatch
              replacePrefixMatch: {{ .rewritePrefix }}
      {{- end }}
      backendRefs:
        - name: {{ .serviceName }}
          port: {{ .servicePort }}
{{- end }}
