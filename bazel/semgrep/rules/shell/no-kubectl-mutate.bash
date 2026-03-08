#!/usr/bin/env bash

# ruleid: no-kubectl-mutate
kubectl apply -f manifest.yaml

# ruleid: no-kubectl-mutate
kubectl delete pod my-pod -n default

# ruleid: no-kubectl-mutate
kubectl patch deployment nginx -p '{"spec":{"replicas":3}}'

# ruleid: no-kubectl-mutate
kubectl scale deployment nginx --replicas=5

# ruleid: no-kubectl-mutate
kubectl edit configmap my-config

# ruleid: no-kubectl-mutate
kubectl create namespace test

# ruleid: no-kubectl-mutate
kubectl replace -f deployment.yaml

# ruleid: no-kubectl-mutate
kubectl set image deployment/nginx nginx=nginx:1.25

# ok: no-kubectl-mutate
kubectl get pods -n argocd

# ok: no-kubectl-mutate
kubectl describe node worker-01

# ok: no-kubectl-mutate
kubectl logs -f deployment/api-gateway -n prod

# ok: no-kubectl-mutate
kubectl top pods -n signoz

# ok: no-kubectl-mutate
kubectl explain deployment.spec
