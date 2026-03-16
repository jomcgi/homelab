{{- define "mcp-oauth-proxy.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "mcp-oauth-proxy.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "mcp-oauth-proxy.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "mcp-oauth-proxy.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "mcp-oauth-proxy.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
