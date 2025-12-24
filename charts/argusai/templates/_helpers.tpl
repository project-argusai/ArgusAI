{{/*
Expand the name of the chart.
*/}}
{{- define "argusai.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited.
*/}}
{{- define "argusai.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "argusai.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "argusai.labels" -}}
helm.sh/chart: {{ include "argusai.chart" . }}
{{ include "argusai.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "argusai.selectorLabels" -}}
app.kubernetes.io/name: {{ include "argusai.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "argusai.backendSelectorLabels" -}}
{{ include "argusai.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend selector labels
*/}}
{{- define "argusai.frontendSelectorLabels" -}}
{{ include "argusai.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "argusai.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "argusai.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Backend fullname
*/}}
{{- define "argusai.backendFullname" -}}
{{- printf "%s-backend" (include "argusai.fullname" .) }}
{{- end }}

{{/*
Frontend fullname
*/}}
{{- define "argusai.frontendFullname" -}}
{{- printf "%s-frontend" (include "argusai.fullname" .) }}
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "argusai.configMapName" -}}
{{- printf "%s-config" (include "argusai.fullname" .) }}
{{- end }}

{{/*
Secret name
*/}}
{{- define "argusai.secretName" -}}
{{- printf "%s-secrets" (include "argusai.fullname" .) }}
{{- end }}

{{/*
PVC name
*/}}
{{- define "argusai.pvcName" -}}
{{- printf "%s-data" (include "argusai.fullname" .) }}
{{- end }}
