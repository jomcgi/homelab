{{/*
cf-ingress.security-policy generates a SecurityPolicy for JWT validation
against Cloudflare Access.

Usage:
  {{- include "cf-ingress.security-policy" . }}

Required values:
  name: HTTPRoute name to target
  team: Cloudflare Access team name (default: "jomcgi")
*/}}
{{- define "cf-ingress.security-policy" -}}
apiVersion: gateway.envoyproxy.io/v1alpha1
kind: SecurityPolicy
metadata:
  name: {{ .name }}-cf-access
spec:
  targetRefs:
    - group: gateway.networking.k8s.io
      kind: HTTPRoute
      name: {{ .name }}
  jwt:
    providers:
      - name: cloudflare-access
        issuer: https://{{ .team | default "jomcgi" }}.cloudflareaccess.com
        remoteJWKS:
          uri: https://{{ .team | default "jomcgi" }}.cloudflareaccess.com/cdn-cgi/access/certs
        extractFrom:
          headers:
            - name: Cf-Access-Jwt-Assertion
        claimToHeaders:
          - claim: email
            header: X-Auth-Email
{{- end }}
