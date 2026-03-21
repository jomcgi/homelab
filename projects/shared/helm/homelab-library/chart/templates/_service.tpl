{{/*
Service resource.
Renders a complete Service for a named component.
All config is read from .Values.<component>.service by convention.

Usage:
  {{- include "homelab.service" (dict "context" . "component" "api") }}
  {{- include "homelab.service" (dict "context" . "component" "wsGateway" "componentName" "ws-gateway") }}

Required values under .<component>.service:
  port (int)

Optional values (with defaults):
  type (ClusterIP), portName ("http"), targetPort (portName value)

Multi-port alternative — set .service.ports list instead of port/portName/targetPort:
  ports: [{port: 6379, name: redis, targetPort: redis}, ...]
*/}}
{{- define "homelab.service" -}}
{{- $ctx := .context -}}
{{- $component := .component -}}
{{- $name := default $component .componentName -}}
{{- $vals := index $ctx.Values $component -}}
{{- $svc := $vals.service -}}
{{- if (default true $vals.enabled) }}
apiVersion: v1
kind: Service
metadata:
  name: {{ include "homelab.fullname" $ctx }}-{{ $name }}
  labels:
    {{- include "homelab.componentLabels" (dict "context" $ctx "component" $name) | nindent 4 }}
spec:
  type: {{ $svc.type | default "ClusterIP" }}
  ports:
    {{- if $svc.ports }}
    {{- range $svc.ports }}
    - port: {{ .port }}
      targetPort: {{ .targetPort | default .name }}
      protocol: TCP
      name: {{ .name }}
    {{- end }}
    {{- else }}
    {{- $portName := $svc.portName | default "http" }}
    - port: {{ $svc.port }}
      targetPort: {{ $svc.targetPort | default $portName }}
      protocol: TCP
      name: {{ $portName }}
    {{- end }}
  selector:
    {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $name) | nindent 4 }}
{{- end }}
{{- end }}
