{{/*
ArgoCD Image Updater CRD.
Renders an ImageUpdater resource for automatic digest-based image updates.
Requires .Values.imageUpdater.enabled, .images[], and .writeBack config.
*/}}
{{- define "homelab.imageupdater" -}}
{{- if .Values.imageUpdater.enabled }}
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata:
  name: {{ include "homelab.fullname" . }}
  namespace: argocd
spec:
  applicationRefs:
    - images:
        {{- range .Values.imageUpdater.images }}
        - alias: {{ .alias }}
          commonUpdateSettings:
            updateStrategy: {{ .updateStrategy | default "digest" }}
            forceUpdate: {{ .forceUpdate | default false }}
          imageName: {{ .imageName }}
          manifestTargets:
            helm:
              name: {{ .helm.name }}
              tag: {{ .helm.tag }}
        {{- end }}
      namePattern: {{ include "homelab.fullname" . }}
  namespace: argocd
  writeBackConfig:
    method: {{ .Values.imageUpdater.writeBack.method }}
    gitConfig:
      repository: {{ .Values.imageUpdater.writeBack.repository }}
      branch: {{ .Values.imageUpdater.writeBack.branch }}
      writeBackTarget: {{ .Values.imageUpdater.writeBack.target }}
{{- end }}
{{- end }}
