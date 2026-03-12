{{/*
cf-ingress.rate-limit generates a BackendTrafficPolicy with rate limiting.

Usage:
  {{- include "cf-ingress.rate-limit" . }}

Required values:
  name: HTTPRoute name to target
Optional:
  rateLimit.requests: requests per unit (default: 100)
  rateLimit.unit: rate limit unit (default: "Minute")
*/}}
{{- define "cf-ingress.rate-limit" -}}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: BackendTrafficPolicy
metadata:
  name: {{ .name }}-rate-limit
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .name }}
  rateLimit:
    global:
      rules:
        - limit:
            requests: {{ .rateLimit.requests | default 100 }}
            unit: {{ .rateLimit.unit | default "Minute" }}
{{- end }}
