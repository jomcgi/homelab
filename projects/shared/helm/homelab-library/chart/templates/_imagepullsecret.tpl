{{/*
GHCR image pull secret via 1Password Operator.
Renders a OnePasswordItem of type kubernetes.io/dockerconfigjson.
Requires .Values.imagePullSecret.enabled, .create, and .onepassword.itemPath.
*/}}
{{- define "homelab.imagepullsecret" -}}
{{- if and .Values.imagePullSecret.enabled .Values.imagePullSecret.create }}
apiVersion: onepassword.com/v1
kind: OnePasswordItem
type: kubernetes.io/dockerconfigjson
metadata:
  name: ghcr-imagepull-secret
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "homelab.labels" . | nindent 4 }}
spec:
  itemPath: {{ .Values.imagePullSecret.onepassword.itemPath | quote }}
{{- end }}
{{- end }}
