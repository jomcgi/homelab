{{/*
Deployment resource.
Renders a complete Deployment for a named component.
All config is read from .Values.<component> by convention.

Usage:
  {{- include "homelab.deployment" (dict "context" . "component" "api") }}

Required values under .<component>:
  image.repository, image.tag, image.pullPolicy

Optional values (with defaults):
  enabled (true), replicas (1), containerPort (8080),
  probes.liveness.path ("/health"), probes.readiness.path ("/health"),
  env ([]), resources ({}), volumes ([]), volumeMounts ([]),
  podAnnotations ({}), podSecurityContext (falls back to global),
  securityContext (falls back to global)
*/}}
{{- define "homelab.deployment" -}}
{{- $ctx := .context -}}
{{- $component := .component -}}
{{- $vals := index $ctx.Values $component -}}
{{- if (default true $vals.enabled) }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "homelab.fullname" $ctx }}-{{ $component }}
  labels:
    {{- include "homelab.componentLabels" (dict "context" $ctx "component" $component) | nindent 4 }}
spec:
  replicas: {{ $vals.replicas | default 1 }}
  selector:
    matchLabels:
      {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $component) | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "homelab.componentSelectorLabels" (dict "context" $ctx "component" $component) | nindent 8 }}
      {{- with $vals.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
    spec:
      {{- if $ctx.Values.imagePullSecret.enabled }}
      imagePullSecrets:
        - name: ghcr-imagepull-secret
      {{- else if $ctx.Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml $ctx.Values.imagePullSecrets | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "homelab.serviceAccountName" $ctx }}
      securityContext:
        {{- $podSec := default $ctx.Values.podSecurityContext $vals.podSecurityContext -}}
        {{- toYaml $podSec | nindent 8 }}
      containers:
        - name: {{ $component }}
          image: "{{ $vals.image.repository }}:{{ $vals.image.tag }}"
          imagePullPolicy: {{ $vals.image.pullPolicy }}
          securityContext:
            {{- $sec := default $ctx.Values.securityContext $vals.securityContext -}}
            {{- toYaml $sec | nindent 12 }}
          ports:
            - name: http
              containerPort: {{ $vals.containerPort | default 8080 }}
              protocol: TCP
          {{- with $vals.env }}
          env:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          livenessProbe:
            httpGet:
              path: {{ dig "probes" "liveness" "path" "/health" $vals }}
              port: http
            initialDelaySeconds: {{ dig "probes" "liveness" "initialDelaySeconds" 10 $vals }}
            periodSeconds: {{ dig "probes" "liveness" "periodSeconds" 10 $vals }}
            timeoutSeconds: {{ dig "probes" "liveness" "timeoutSeconds" 1 $vals }}
            failureThreshold: {{ dig "probes" "liveness" "failureThreshold" 3 $vals }}
          readinessProbe:
            httpGet:
              path: {{ dig "probes" "readiness" "path" "/health" $vals }}
              port: http
            initialDelaySeconds: {{ dig "probes" "readiness" "initialDelaySeconds" 5 $vals }}
            periodSeconds: {{ dig "probes" "readiness" "periodSeconds" 5 $vals }}
            timeoutSeconds: {{ dig "probes" "readiness" "timeoutSeconds" 1 $vals }}
            failureThreshold: {{ dig "probes" "readiness" "failureThreshold" 3 $vals }}
          {{- with $vals.resources }}
          resources:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
            {{- with $vals.volumeMounts }}
            {{- toYaml . | nindent 12 }}
            {{- end }}
      volumes:
        - name: tmp
          emptyDir: {}
        {{- with $vals.volumes }}
        {{- toYaml . | nindent 8 }}
        {{- end }}
      {{- with $ctx.Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $ctx.Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with $ctx.Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
{{- end }}
{{- end }}
