{{- define "monolith.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "monolith.labels" -}}
app.kubernetes.io/name: monolith
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "monolith.selectorLabels" -}}
app.kubernetes.io/name: monolith
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
