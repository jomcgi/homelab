{{/*
Common labels for a server.
Usage: {{- include "mcp-servers.labels" (dict "server" $server "Chart" $.Chart "Release" $.Release) }}
*/}}
{{- define "mcp-servers.labels" -}}
app.kubernetes.io/name: {{ .server.name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Selector labels for a server.
Usage: {{- include "mcp-servers.selectorLabels" (dict "server" . "Release" $.Release) }}
*/}}
{{- define "mcp-servers.selectorLabels" -}}
app.kubernetes.io/name: {{ .server.name }}
app.kubernetes.io/instance: {{ .Release.Name }}
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
