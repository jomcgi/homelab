{{/*
Common labels for a server.
Usage: {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart) }}
*/}}
{{- define "mcp-servers.labels" -}}
app.kubernetes.io/name: {{ .server.name }}
app.kubernetes.io/managed-by: {{ .Chart.Name }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Selector labels for a server.
Usage: {{- include "mcp-servers.selectorLabels" .server }}
*/}}
{{- define "mcp-servers.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
{{- end }}

{{/*
Effective port for a server (translate port if enabled, otherwise server port).
Usage: {{ include "mcp-servers.port" $server }}
*/}}
{{- define "mcp-servers.port" -}}
{{- if and .translate .translate.enabled -}}
{{- .translate.port | default 8080 -}}
{{- else -}}
{{- .port -}}
{{- end -}}
{{- end }}
