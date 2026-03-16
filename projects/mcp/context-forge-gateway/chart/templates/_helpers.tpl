{{- define "context-forge.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "context-forge.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "context-forge.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "context-forge.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "context-forge.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
