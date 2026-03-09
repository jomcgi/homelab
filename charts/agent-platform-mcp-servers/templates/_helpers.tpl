{{/*
Common labels for a server.
Usage: {{- include "agent-platform-mcp-servers.labels" (dict "name" $name "Chart" $.Chart "Release" $.Release) }}
*/}}
{{- define "agent-platform-mcp-servers.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Selector labels for a server.
Usage: {{- include "agent-platform-mcp-servers.selectorLabels" (dict "name" $name "Release" $.Release) }}
*/}}
{{- define "agent-platform-mcp-servers.selectorLabels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
