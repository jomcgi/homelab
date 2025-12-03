{{/*
Expand the name of the chart.
*/}}
{{- define "fizzy.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "fizzy.fullname" -}}
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
{{- define "fizzy.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "fizzy.labels" -}}
helm.sh/chart: {{ include "fizzy.chart" . }}
{{ include "fizzy.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "fizzy.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fizzy.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Web selector labels
*/}}
{{- define "fizzy.webSelectorLabels" -}}
{{ include "fizzy.selectorLabels" . }}
app.kubernetes.io/component: web
{{- end }}

{{/*
Worker selector labels
*/}}
{{- define "fizzy.workerSelectorLabels" -}}
{{ include "fizzy.selectorLabels" . }}
app.kubernetes.io/component: worker
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "fizzy.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "fizzy.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the name of the secret containing Rails credentials
*/}}
{{- define "fizzy.secretName" -}}
{{- printf "%s-credentials" (include "fizzy.fullname" .) }}
{{- end }}

{{/*
Database URL construction
*/}}
{{- define "fizzy.databaseUrl" -}}
{{- if .Values.database.existingSecret }}
{{- /* Use existing secret */ -}}
{{- else if and .Values.database.host .Values.database.username }}
{{- printf "mysql2://%s:%s@%s:%d/%s" .Values.database.username .Values.database.password .Values.database.host (int .Values.database.port) .Values.database.name }}
{{- end }}
{{- end }}
