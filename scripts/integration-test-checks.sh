#!/bin/bash
set -e

echo "Starting health and configuration checks..."

# --- Pods Health Check ---
echo "Checking Pod statuses..."
# Adjust namespaces as per your actual setup
# Using kubectl to get all pods, then filtering.
# Output format: namespace<tab>pod-name<tab>status
all_pods_status=$(kubectl get pods --all-namespaces -o go-template='{{range .items}}{{.metadata.namespace}}{{"\t"}}{{.metadata.name}}{{"\t"}}{{.status.phase}}{{"\n"}}{{end}}')

# Define expected namespaces and a list of services to check.
# This helps focus the checks and can be expanded.
# For now, we'll just check all pods retrieved that are not in kube-system
# and expect them to be Running or Succeeded.

echo "$all_pods_status" | while IFS=$'\t' read -r ns name phase; do
  if [[ "$ns" == "kube-system" || "$ns" == "kube-public" || "$ns" == "minikube" ]]; then
    # Skip system namespaces for this generic check, unless specific checks are needed later
    continue
  fi

  echo "Checking pod: $ns/$name, Status: $phase"
  if [[ "$phase" != "Running" && "$phase" != "Succeeded" ]]; then
    echo "Error: Pod $ns/$name is not Running or Succeeded. Current status: $phase"
    kubectl logs "$name" -n "$ns" --tail=50 || echo "Could not retrieve logs for $ns/$name"
    kubectl describe pod "$name" -n "$ns" || echo "Could not describe pod $ns/$name"
    exit 1
  fi
done

echo "All checked pods are Running or Succeeded."

# --- Deployments/StatefulSets Health Check ---
echo "Checking Deployment and StatefulSet readiness..."

# Example: Check specific deployments/statefulsets
# Add more specific checks as needed for your services.
# This is a generic example. You'll need to list your actual deployments/statefulsets.
# Assumes services are deployed in namespaces named after them unless specified otherwise.
# Format: "namespace/deploymentOrStatefulSetName"
services_to_check_deployments=(
  "cloudflare-tunnel/cloudflare-tunnel"
  "github-webhook/github-webhook-handler"
  "grafana-cloud/grafana-cloud" # Assuming deployment name is 'grafana-cloud' in 'grafana-cloud' namespace
  "obsidian/obsidian"
  "open-webui/open-webui" # Assuming deployment name is 'open-webui' in 'open-webui' namespace
  "opentelemetry/otel-collector"
  "uptime-kuma/uptime-kuma" # Assuming deployment name is 'uptime-kuma' in 'uptime-kuma' namespace
)

for item in "${services_to_check_deployments[@]}"; do
  IFS='/' read -r ns name <<< "$item"
  # Try Deployment first
  if kubectl get deployment "$name" -n "$ns" &> /dev/null; then
    resource_type="deployment"
  # Then try StatefulSet
  elif kubectl get statefulset "$name" -n "$ns" &> /dev/null; then
    resource_type="statefulset"
  else
    echo "Warning: Neither Deployment nor StatefulSet found for $name in $ns. Skipping readiness check for it."
    continue
  fi

  echo "Checking $resource_type $name in namespace $ns..."
  # Fetch spec.replicas and status.readyReplicas
  # Default to 1 replica if not specified (e.g. for some statefulsets or if field is missing, though unlikely for deployments)
  spec_replicas=$(kubectl get $resource_type "$name" -n "$ns" -o jsonpath='{.spec.replicas}' 2>/dev/null)
  spec_replicas=${spec_replicas:-1} # Default to 1 if empty

  ready_replicas=$(kubectl get $resource_type "$name" -n "$ns" -o jsonpath='{.status.readyReplicas}' 2>/dev/null)
  ready_replicas=${ready_replicas:-0} # Default to 0 if empty

  if [[ "$spec_replicas" -ne "$ready_replicas" ]]; then
    echo "Error: $resource_type $name in $ns is not ready. Expected replicas: $spec_replicas, Ready replicas: $ready_replicas"
    kubectl describe $resource_type "$name" -n "$ns"
    exit 1
  else
    echo "$resource_type $name in $ns is ready ($ready_replicas/$spec_replicas replicas)."
  fi
done

echo "All checked Deployments/StatefulSets are ready."

# --- Services Accessibility (Placeholder) ---
echo "Service accessibility checks (placeholder)..."
# Example:
# echo "Checking accessibility of my-service..."
# kubectl port-forward svc/my-service -n my-namespace 8080:80 &
# PF_PID=$!
# sleep 5 # Give port-forward time to establish
# if curl --fail http://localhost:8080/health; then
#   echo "my-service is accessible."
# else
#   echo "Error: my-service is not accessible."
#   kill $PF_PID
#   exit 1
# fi
# kill $PF_PID

# --- ConfigMap/Secret Checks (Placeholder) ---
echo "ConfigMap/Secret checks (placeholder)..."
# Example:
# echo "Checking ConfigMap my-config in my-namespace..."
# if kubectl get configmap my-config -n my-namespace -o jsonpath='{.data.my-key}' | grep -q "expected-value"; then
#   echo "ConfigMap my-config has the expected value."
# else
#   echo "Error: ConfigMap my-config does not have the expected value."
#   exit 1
# fi
#
# echo "Checking Secret my-secret in my-namespace..."
# if kubectl get secret my-secret -n my-namespace &> /dev/null; then
#   echo "Secret my-secret exists."
# else
#   echo "Error: Secret my-secret does not exist."
#   exit 1
# fi

echo "All health and configuration checks passed successfully!"
exit 0
