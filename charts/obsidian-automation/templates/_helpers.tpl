{{/*
Expand the name of the chart.
*/}}
{{- define "obsidian-automation.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "obsidian-automation.fullname" -}}
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
{{- define "obsidian-automation.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "obsidian-automation.labels" -}}
helm.sh/chart: {{ include "obsidian-automation.chart" . }}
{{ include "obsidian-automation.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.labels }}
{{- toYaml . | nindent 0 }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "obsidian-automation.selectorLabels" -}}
app.kubernetes.io/name: {{ include "obsidian-automation.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app: obsidian-automation
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "obsidian-automation.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "obsidian-automation.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Create the namespace
*/}}
{{- define "obsidian-automation.namespace" -}}
{{- if .Values.namespace.create }}
{{- .Values.namespace.name }}
{{- else }}
{{- .Release.Namespace }}
{{- end }}
{{- end }}

{{/*
Secret name - consistent naming for OnePasswordItem and manual secrets
*/}}
{{- define "obsidian-automation.secretName" -}}
{{- if eq .Values.secrets.type "onepassword" }}
{{- .Values.secrets.onepassword.secretName }}
{{- else if eq .Values.secrets.type "manual" }}
{{- .Values.secrets.manual.secretName }}
{{- else }}
{{- printf "%s-secrets" (include "obsidian-automation.fullname" .) }}
{{- end }}
{{- end }}