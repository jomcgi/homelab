{{/*
Expand the name of the chart.
*/}}
{{- define "homelab.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "homelab.fullname" -}}
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
{{- define "homelab.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "homelab.labels" -}}
helm.sh/chart: {{ include "homelab.chart" . }}
{{ include "homelab.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- with .Values.extraLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "homelab.selectorLabels" -}}
app.kubernetes.io/name: {{ include "homelab.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "homelab.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "homelab.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Component labels — adds app.kubernetes.io/component to common labels.
Usage: {{ include "homelab.componentLabels" (dict "context" . "component" "api") }}
*/}}
{{- define "homelab.componentLabels" -}}
{{ include "homelab.labels" .context }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Component selector labels — adds app.kubernetes.io/component to selector labels.
Usage: {{ include "homelab.componentSelectorLabels" (dict "context" . "component" "api") }}
*/}}
{{- define "homelab.componentSelectorLabels" -}}
{{ include "homelab.selectorLabels" .context }}
app.kubernetes.io/component: {{ .component }}
{{- end }}
