{{/*
Common labels for a server.
Uses homelab.chart from the library for the chart label, but overrides
app.kubernetes.io/name with the per-server name (since each server is its own Deployment).
Usage: {{- include "agent-platform-mcp-servers.labels" (dict "name" $name "Chart" $.Chart "Release" $.Release) }}
*/}}
{{- define "agent-platform-mcp-servers.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: mcp-server
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ include "homelab.chart" . }}
{{- end }}

{{/*
Selector labels for a server.
Usage: {{- include "agent-platform-mcp-servers.selectorLabels" (dict "name" $name "Release" $.Release) }}
*/}}
{{- define "agent-platform-mcp-servers.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: mcp-server
{{- end }}

{{/*
Effective port for a server — translate port when enabled, otherwise server port.
Call with the server object directly: {{ include "agent-platform-mcp-servers.port" $server }}
*/}}
{{- define "agent-platform-mcp-servers.port" -}}
{{- if and .translate .translate.enabled -}}
{{- .translate.port | default 8080 -}}
{{- else -}}
{{- .port -}}
{{- end -}}
{{- end }}
