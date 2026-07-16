{{- define "marty.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "marty.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "marty.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "marty.labels" -}}
app.kubernetes.io/name: {{ include "marty.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
