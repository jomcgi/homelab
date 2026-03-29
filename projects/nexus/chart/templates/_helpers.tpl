{{- define "nexus.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "nexus.labels" -}}
app.kubernetes.io/name: nexus
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "nexus.selectorLabels" -}}
app.kubernetes.io/name: nexus
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
