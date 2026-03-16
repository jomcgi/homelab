{{- define "stargazer.name" -}}{{ include "homelab.name" . }}{{- end }}
{{- define "stargazer.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "stargazer.chart" -}}{{ include "homelab.chart" . }}{{- end }}
{{- define "stargazer.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "stargazer.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
{{- define "stargazer.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}
