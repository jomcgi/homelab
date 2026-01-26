# Linkerd Bootstrap Instructions

## Prerequisites

Before deploying Linkerd with ArgoCD, you must manually create the trust roots ConfigMap.

## Why Manual Creation?

When using cert-manager as the external CA for Linkerd (`certManager.enabled: true`):

1. cert-manager creates the trust anchor certificate in a Secret
2. Linkerd control plane pods need this certificate in a ConfigMap to bootstrap
3. Helm templates cannot read Secret data to populate ConfigMap values
4. Helm hooks don't execute in ArgoCD (hooks are stripped during rendering)

Therefore, the `linkerd-identity-trust-roots` ConfigMap must be created manually **once per cluster** before Linkerd can start.

## Bootstrap Steps

### 1. Ensure cert-manager is installed and healthy

```bash
kubectl get pods -n cert-manager
```

### 2. Wait for Linkerd trust anchor certificate to be created

```bash
# Watch for the certificate to become Ready
kubectl get certificate -n linkerd -w

# Should show:
# NAME                      READY   AGE
# linkerd-trust-anchor      True    1m
# linkerd-identity-issuer   True    1m
```

### 3. Create the trust roots ConfigMap

```bash
kubectl get secret linkerd-trust-anchor -n linkerd -o jsonpath='{.data.ca\.crt}' | \
  base64 -d | \
  kubectl create configmap linkerd-identity-trust-roots \
    --from-file=ca-bundle.crt=/dev/stdin \
    -n linkerd \
    --dry-run=client -o yaml | \
  kubectl apply -f -
```

### 4. Verify the ConfigMap was created

```bash
kubectl get configmap linkerd-identity-trust-roots -n linkerd
kubectl describe configmap linkerd-identity-trust-roots -n linkerd
```

You should see a `ca-bundle.crt` field containing a PEM-encoded certificate.

### 5. Deploy Linkerd via ArgoCD

```bash
kubectl get application linkerd -n argocd
# Should show Healthy after deployment completes
```

### 6. Verify Linkerd pods are running

```bash
kubectl get pods -n linkerd

# Should show all pods as Running:
# linkerd-destination-*       4/4     Running
# linkerd-identity-*          2/2     Running
# linkerd-proxy-injector-*    2/2     Running
```

## Troubleshooting

### Pods stuck in CreateContainerConfigError or Init:0/1

```bash
kubectl describe pod <pod-name> -n linkerd
```

Look for errors like:

- `configmap "linkerd-identity-trust-roots" not found` → Re-create the ConfigMap
- `secret "linkerd-identity-issuer" not found` → Wait for cert-manager to create certificates

### ConfigMap exists but pods still failing

Verify the ConfigMap has the correct certificate:

```bash
kubectl get configmap linkerd-identity-trust-roots -n linkerd -o yaml
```

The `ca-bundle.crt` field should contain a PEM certificate starting with `-----BEGIN CERTIFICATE-----`.

If it's empty, recreate it using the command in step 3.

## Future Improvements

This manual step could be eliminated by:

1. **Installing cert-manager trust-manager**: Automatically syncs certificates from Secrets to ConfigMaps/Bundles
2. **Using a Kubernetes Job**: A regular (non-hook) Job that runs once to create the ConfigMap
3. **Using an init container**: In the Linkerd deployments to copy the secret data

For now, the one-time manual creation is the simplest and most reliable approach for this homelab environment.
