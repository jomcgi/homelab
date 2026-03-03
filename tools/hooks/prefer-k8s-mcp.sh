#!/bin/bash
# PreToolUse hook: redirects kubectl read commands to Kubernetes MCP tools.
# Blocks kubectl get/describe/logs/top and suggests MCP equivalents.
# Allows write operations and other safe commands through.
#
# Input: JSON on stdin from Claude Code hook system
# Exit 0: allow the command
# Exit 2: block the command (reason shown to Claude)

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

# Only check commands that contain kubectl
if [[ ! "$COMMAND" =~ kubectl ]]; then
	exit 0
fi

# Extract the kubectl segment from chained commands (handles && and ;)
KUBECTL_SEGMENT="$COMMAND"
if [[ "$COMMAND" == *"&&"* ]] || [[ "$COMMAND" == *";"* ]]; then
	KUBECTL_SEGMENT=$(echo "$COMMAND" | tr ';&' '\n' | grep 'kubectl' | head -1 | xargs)
fi

# Strip kubectl and all flags to find the verb.
# Handles flexible flag ordering: kubectl -n ns get pods, kubectl get pods -n ns, etc.
# Remove "kubectl" prefix, then strip all known flags and their values.
ARGS=$(echo "$KUBECTL_SEGMENT" | sed -E 's/^[[:space:]]*kubectl[[:space:]]+//')
# Strip flags with values: -n <val>, --namespace <val>, --namespace=<val>, -o <val>, etc.
ARGS=$(echo "$ARGS" | sed -E 's/(-n|--namespace|--context|-o|--output|--selector|-l|--field-selector|--sort-by|--chunk-size|-c|--container|--tail|--since|--since-time|--timestamps|-A|--all-namespaces|--no-headers|--show-labels|--watch|-w|-f|--follow|--previous|-p)(=[^[:space:]]*|[[:space:]]+[^[:space:]-][^[:space:]]*)?//g')
# Strip remaining standalone flags
ARGS=$(echo "$ARGS" | sed -E 's/--[a-z][-a-z]*//g')
ARGS=$(echo "$ARGS" | xargs) # trim whitespace

# The verb is the first remaining word
VERB=$(echo "$ARGS" | awk '{print $1}')

case "$VERB" in
get)
	cat >&2 <<-'EOF'
		BLOCKED: Use Kubernetes MCP tools instead of `kubectl get`.

		MCP equivalents (use ToolSearch with +kubernetes to load):
		  - kubernetes-mcp-resources-list     General resource listing
		  - kubernetes-mcp-pods-list           List pods across all namespaces
		  - kubernetes-mcp-pods-list-in-namespace  List pods in a specific namespace
		  - kubernetes-mcp-namespaces-list     List namespaces
		  - kubernetes-mcp-events-list         List events
		  - kubernetes-mcp-helm-list           List Helm releases

		These provide structured data without shell parsing.
	EOF
	exit 2
	;;
describe)
	cat >&2 <<-'EOF'
		BLOCKED: Use Kubernetes MCP tools instead of `kubectl describe`.

		MCP equivalents (use ToolSearch with +kubernetes to load):
		  - kubernetes-mcp-resources-get       Get detailed resource info

		This returns structured data instead of unstructured text.
	EOF
	exit 2
	;;
logs)
	cat >&2 <<-'EOF'
		BLOCKED: Use MCP tools instead of `kubectl logs`.

		MCP equivalents:
		  - kubernetes-mcp-pods-log            Recent pod logs (use ToolSearch with +kubernetes)
		  - signoz-search-logs-by-service      Historical logs (use ToolSearch with +signoz)
		  - signoz-get-error-logs              Error logs only

		SigNoz provides searchable, filtered, correlated logs across services.
	EOF
	exit 2
	;;
top)
	cat >&2 <<-'EOF'
		BLOCKED: Use Kubernetes MCP tools instead of `kubectl top`.

		MCP equivalents (use ToolSearch with +kubernetes to load):
		  - kubernetes-mcp-pods-top            Pod resource usage
		  - kubernetes-mcp-nodes-top           Node resource usage

		These return structured metrics data.
	EOF
	exit 2
	;;
*)
	# Allow all other verbs: create, apply, delete, label, port-forward, exec,
	# cp, run, explain, api-resources, config, version, rollout, auth, wait,
	# patch, edit, scale, annotate, taint, cordon, uncordon, drain
	exit 0
	;;
esac
