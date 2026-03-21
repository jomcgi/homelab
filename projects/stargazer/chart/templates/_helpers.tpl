{{- define "stargazer.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "stargazer.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "stargazer.selectorLabels" -}}{{ include "homelab.selectorLabels" . }}{{- end }}
{{- define "stargazer.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}
