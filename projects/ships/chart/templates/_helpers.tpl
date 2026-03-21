{{- define "marine.fullname" -}}{{ include "homelab.fullname" . }}{{- end }}
{{- define "marine.labels" -}}{{ include "homelab.labels" . }}{{- end }}
{{- define "marine.serviceAccountName" -}}{{ include "homelab.serviceAccountName" . }}{{- end }}

{{/*
Component label aliases — these call the library's component helpers.
*/}}
{{- define "marine.ingest.labels" -}}
{{ include "homelab.componentLabels" (dict "context" . "component" "ingest") }}
{{- end }}

{{- define "marine.ingest.selectorLabels" -}}
{{ include "homelab.componentSelectorLabels" (dict "context" . "component" "ingest") }}
{{- end }}

{{- define "marine.api.labels" -}}
{{ include "homelab.componentLabels" (dict "context" . "component" "api") }}
{{- end }}

{{- define "marine.api.selectorLabels" -}}
{{ include "homelab.componentSelectorLabels" (dict "context" . "component" "api") }}
{{- end }}

{{- define "marine.frontend.labels" -}}
{{ include "homelab.componentLabels" (dict "context" . "component" "frontend") }}
{{- end }}

{{- define "marine.frontend.selectorLabels" -}}
{{ include "homelab.componentSelectorLabels" (dict "context" . "component" "frontend") }}
{{- end }}
