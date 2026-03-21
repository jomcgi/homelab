{{- define "agent-orchestrator.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "agent-orchestrator.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "agent-orchestrator.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "agent-orchestrator.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "agent-orchestrator.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
{{- define "agent-orchestrator.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}
