# CoreDNS Configuration Chart

This Helm chart manages the CoreDNS configuration for the K3s cluster.

## Overview

**Important:** This chart does NOT deploy CoreDNS itself. CoreDNS is bundled and managed by K3s. This chart only manages the ConfigMap that configures CoreDNS behavior.

## What This Chart Does

- Deploys a ConfigMap (`coredns` in `kube-system` namespace)
- Configures DNS resolution behavior
- Sets up DNS forwarding to public resolvers (Cloudflare + Google)
- Enables Prometheus metrics on port 9153

## Configuration

See `values.yaml` for all configuration options.

### Key Settings

- **DNS Forwarders:** By default uses Cloudflare (1.1.1.1) and Google (8.8.8.8)
- **Cache TTL:** 300 seconds (5 minutes)
- **Max Concurrent:** 1000 concurrent DNS requests
- **Prometheus:** Metrics exposed on `:9153/metrics`

### Custom DNS Configuration

To customize DNS settings, override values in `overlays/cluster-critical/coredns/values.yaml`:

```yaml
# Use different DNS forwarders
forwarders:
  - 9.9.9.9 # Quad9
  - 8.8.8.8 # Google

# Increase cache TTL
cacheTTL: 300
```

## ArgoCD Integration

The ArgoCD Application has special configuration:

- `prune: false` - K3s owns the CoreDNS Deployment/Service, so we don't prune
- `ignoreDifferences` - Ignores fields that K3s manages (NodeHosts, annotations, labels)

This ensures we only manage the Corefile configuration, not the entire CoreDNS deployment.

## Troubleshooting

### Check DNS Resolution

```bash
# Test DNS from within cluster
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup kubernetes.default

# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns

# Check Prometheus metrics
kubectl port-forward -n kube-system svc/kube-dns 9153:9153
curl http://localhost:9153/metrics
```

### Verify Configuration

```bash
# Check the ConfigMap
kubectl get configmap coredns -n kube-system -o yaml

# Render the Helm chart locally
helm template coredns charts/coredns/ \
  --values charts/coredns/values.yaml \
  --values overlays/cluster-critical/coredns/values.yaml
```

## References

- [CoreDNS Documentation](https://coredns.io/manual/toc/)
- [K3s CoreDNS](https://docs.k3s.io/networking#coredns)
- [CoreDNS Plugins](https://coredns.io/plugins/)
