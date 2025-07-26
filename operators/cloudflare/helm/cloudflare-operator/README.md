# Cloudflare Operator Helm Chart

This Helm chart deploys the Cloudflare Tunnel Operator on a Kubernetes cluster.

## Prerequisites

- Kubernetes 1.19+
- Helm 3.2.0+
- Cloudflare API Token and Account ID

## Installation

### 1. Create Cloudflare Credentials Secret

First, create a secret containing your Cloudflare API credentials:

```bash
kubectl create secret generic cloudflare-credentials \
  --from-literal=CLOUDFLARE_API_TOKEN=your_api_token_here \
  --from-literal=CLOUDFLARE_ACCOUNT_ID=your_account_id_here \
  -n cloudflare-operator-system
```

### 2. Install the Chart

Add the chart repository (if hosted) or install from local directory:

```bash
# Install from local directory
helm install cloudflare-operator ./helm/cloudflare-operator \
  --create-namespace \
  --namespace cloudflare-operator-system
```

### 3. Verify Installation

Check that the operator is running:

```bash
kubectl get pods -n cloudflare-operator-system
kubectl get crd | grep cloudflare
```

## Configuration

The following table lists the configurable parameters and their default values:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `controllerManager.image.repository` | Controller manager image repository | `cloudflare-operator` |
| `controllerManager.image.tag` | Controller manager image tag | `latest` |
| `controllerManager.image.pullPolicy` | Image pull policy | `IfNotPresent` |
| `controllerManager.replicas` | Number of controller manager replicas | `1` |
| `controllerManager.resources.limits.cpu` | CPU limit | `500m` |
| `controllerManager.resources.limits.memory` | Memory limit | `128Mi` |
| `controllerManager.resources.requests.cpu` | CPU request | `10m` |
| `controllerManager.resources.requests.memory` | Memory request | `64Mi` |
| `serviceAccount.create` | Create service account | `true` |
| `serviceAccount.annotations` | Service account annotations | `{}` |
| `serviceAccount.name` | Service account name | `""` |
| `rbac.create` | Create RBAC resources | `true` |
| `crds.install` | Install CRDs | `true` |
| `namespace.name` | Operator namespace | `cloudflare-operator-system` |
| `namespace.create` | Create namespace | `true` |

## Usage

After installation, you can create CloudflareTunnel resources:

```yaml
apiVersion: tunnels.tunnels.cloudflare.io/v1
kind: CloudflareTunnel
metadata:
  name: my-tunnel
  namespace: default
spec:
  accountId: "your-account-id"
  name: "my-tunnel"
  ingress:
    - hostname: "example.com"
      service: "http://my-service:80"
    - service: "http_status:404"
```

## Uninstallation

To uninstall the chart:

```bash
helm uninstall cloudflare-operator -n cloudflare-operator-system
```

Note: This will not remove the CRDs. To remove them manually:

```bash
kubectl delete crd cloudflaretunnels.tunnels.tunnels.cloudflare.io
```

## Development

To build and test the operator locally:

```bash
# Build the operator image
make docker-build IMG=cloudflare-operator:dev

# Load image into kind cluster (if using kind)
kind load docker-image cloudflare-operator:dev

# Install with custom image
helm install cloudflare-operator ./helm/cloudflare-operator \
  --set controllerManager.image.repository=cloudflare-operator \
  --set controllerManager.image.tag=dev \
  --set controllerManager.image.pullPolicy=Never \
  --create-namespace \
  --namespace cloudflare-operator-system
```