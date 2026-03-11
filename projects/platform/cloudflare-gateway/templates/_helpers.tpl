{{/*
Expand the name of the chart.
*/}}
{{- define "cloudflare-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "cloudflare-gateway.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "cloudflare-gateway.labels" -}}
helm.sh/chart: {{ include "cloudflare-gateway.chart" . }}
app.kubernetes.io/name: {{ include "cloudflare-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Tunnel fullname - defaults to "cloudflared" to match existing naming.
*/}}
{{- define "cloudflare-gateway.tunnel.fullname" -}}
{{- default "cloudflared" .Values.tunnel.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Tunnel selector labels
*/}}
{{- define "cloudflare-gateway.tunnel.selectorLabels" -}}
app.kubernetes.io/name: cloudflare-tunnel
app.kubernetes.io/instance: {{ .Release.Name }}
app: cloudflared
{{- end }}

{{/*
Tunnel labels
*/}}
{{- define "cloudflare-gateway.tunnel.labels" -}}
helm.sh/chart: {{ include "cloudflare-gateway.chart" . }}
{{ include "cloudflare-gateway.tunnel.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
