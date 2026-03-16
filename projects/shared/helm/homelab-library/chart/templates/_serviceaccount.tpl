{{/*
ServiceAccount resource.
Renders a complete ServiceAccount if .Values.serviceAccount.create is true.
Supports optional annotations and automountServiceAccountToken.
*/}}
{{- define "homelab.serviceaccount" -}}
{{- if .Values.serviceAccount.create -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "homelab.serviceAccountName" . }}
  labels:
    {{- include "homelab.labels" . | nindent 4 }}
  {{- with .Values.serviceAccount.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- if hasKey .Values.serviceAccount "automount" }}
automountServiceAccountToken: {{ .Values.serviceAccount.automount }}
{{- end }}
{{- end }}
{{- end }}
