{{- define "grimoire.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "grimoire.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "grimoire.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "grimoire.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "grimoire.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
{{- define "grimoire.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}
