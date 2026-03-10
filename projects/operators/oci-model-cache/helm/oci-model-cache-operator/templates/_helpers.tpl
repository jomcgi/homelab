{{- define "oci-model-cache-operator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "oci-model-cache-operator.fullname" -}}
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

{{- define "oci-model-cache-operator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "oci-model-cache-operator.labels" -}}
helm.sh/chart: {{ include "oci-model-cache-operator.chart" . }}
{{ include "oci-model-cache-operator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "oci-model-cache-operator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "oci-model-cache-operator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "oci-model-cache-operator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (printf "%s-controller-manager" (include "oci-model-cache-operator.fullname" .)) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{- define "oci-model-cache-operator.hfTokenSecretName" -}}
{{- if .Values.hfToken.existingSecret }}
{{- .Values.hfToken.existingSecret }}
{{- else }}
{{- printf "%s-hf-token" (include "oci-model-cache-operator.fullname" .) }}
{{- end }}
{{- end }}

{{- define "oci-model-cache-operator.syncServiceAccountName" -}}
{{- if .Values.syncServiceAccount.create }}
{{- default (printf "%s-sync" (include "oci-model-cache-operator.fullname" .)) .Values.syncServiceAccount.name }}
{{- else }}
{{- default "default" .Values.syncServiceAccount.name }}
{{- end }}
{{- end }}
