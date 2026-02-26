{{/*
Expand the name of the chart.
*/}}
{{- define "openhands.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "openhands.fullname" -}}
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
{{- define "openhands.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "openhands.labels" -}}
helm.sh/chart: {{ include "openhands.chart" . }}
{{ include "openhands.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "openhands.selectorLabels" -}}
app.kubernetes.io/name: {{ include "openhands.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
App component labels
*/}}
{{- define "openhands.app.labels" -}}
{{ include "openhands.labels" . }}
app.kubernetes.io/component: app
{{- end }}

{{/*
App component selector labels
*/}}
{{- define "openhands.app.selectorLabels" -}}
{{ include "openhands.selectorLabels" . }}
app.kubernetes.io/component: app
{{- end }}

{{/*
LiteLLM component labels
*/}}
{{- define "openhands.litellm.labels" -}}
{{ include "openhands.labels" . }}
app.kubernetes.io/component: litellm
{{- end }}

{{/*
LiteLLM component selector labels
*/}}
{{- define "openhands.litellm.selectorLabels" -}}
{{ include "openhands.selectorLabels" . }}
app.kubernetes.io/component: litellm
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "openhands.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "openhands.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
