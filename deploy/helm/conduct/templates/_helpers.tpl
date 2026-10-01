{{/* Use the release name for service names. */}}
{{- define "conduct.fullname" -}}
{{- .Release.Name | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "conduct.name" -}}
conduct
{{- end -}}

{{- define "conduct.labels" -}}
app.kubernetes.io/name: {{ include "conduct.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "conduct.selectorLabels" -}}
app.kubernetes.io/name: {{ include "conduct.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Serviceaccount name resolver. */}}
{{- define "conduct.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{ default (include "conduct.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
{{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/* Resolve the Secret name (external vs chart-owned). */}}
{{- define "conduct.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{ .Values.secrets.existingSecret }}
{{- else -}}
{{ include "conduct.fullname" . }}
{{- end -}}
{{- end -}}

{{/* Image tag defaults to Chart.appVersion. */}}
{{- define "conduct.apiImage" -}}
{{ required "image.api.repository is required" .Values.image.api.repository }}:{{ required "image.api.tag is required" .Values.image.api.tag }}
{{- end -}}

{{- define "conduct.webImage" -}}
{{ required "image.web.repository is required" .Values.image.web.repository }}:{{ required "image.web.tag is required" .Values.image.web.tag }}
{{- end -}}
