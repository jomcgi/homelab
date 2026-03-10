{{/*
Expand the name of the chart.
*/}}
{{- define "marine.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "marine.fullname" -}}
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
{{- define "marine.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "marine.labels" -}}
helm.sh/chart: {{ include "marine.chart" . }}
{{ include "marine.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "marine.selectorLabels" -}}
app.kubernetes.io/name: {{ include "marine.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Ingest component labels
*/}}
{{- define "marine.ingest.labels" -}}
{{ include "marine.labels" . }}
app.kubernetes.io/component: ingest
{{- end }}

{{/*
Ingest component selector labels
*/}}
{{- define "marine.ingest.selectorLabels" -}}
{{ include "marine.selectorLabels" . }}
app.kubernetes.io/component: ingest
{{- end }}

{{/*
API component labels
*/}}
{{- define "marine.api.labels" -}}
{{ include "marine.labels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
API component selector labels
*/}}
{{- define "marine.api.selectorLabels" -}}
{{ include "marine.selectorLabels" . }}
app.kubernetes.io/component: api
{{- end }}

{{/*
Frontend component labels
*/}}
{{- define "marine.frontend.labels" -}}
{{ include "marine.labels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Frontend component selector labels
*/}}
{{- define "marine.frontend.selectorLabels" -}}
{{ include "marine.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "marine.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "marine.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
