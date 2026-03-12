{{/*
Expand the name of the chart.
*/}}
{{- define "llama-cpp.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "llama-cpp.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "llama-cpp.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "llama-cpp.labels" -}}
helm.sh/chart: {{ include "llama-cpp.chart" . }}
{{ include "llama-cpp.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "llama-cpp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "llama-cpp.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
llama-server CLI arguments (shared between direct args and auto-discovery shell modes).
*/}}
{{- define "llama-cpp.serverArgs" -}}
--n-gpu-layers {{ .Values.server.nGpuLayers | quote }} \
--ctx-size {{ .Values.server.ctxSize | quote }} \
{{- if .Values.server.flashAttn }}
--flash-attn {{ .Values.server.flashAttn | quote }} \
{{- end }}
--cache-type-k {{ .Values.server.cacheTypeK | quote }} \
--cache-type-v {{ .Values.server.cacheTypeV | quote }} \
--threads {{ .Values.server.threads | quote }} \
{{- if .Values.server.jinja }}
--jinja \
{{- end }}
{{- if .Values.server.chatTemplate }}
--chat-template-file "/etc/llama-cpp/chat-template.jinja" \
{{- end }}
--host {{ .Values.server.host | quote }} \
--port {{ .Values.server.port | quote }}{{ range .Values.server.extraArgs }} \
{{ . | quote }}{{ end }}
{{- end }}
