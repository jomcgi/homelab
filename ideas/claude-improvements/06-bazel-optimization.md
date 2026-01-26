# Bazel Tooling Optimization with BuildBuddy

## Overview

Deploy BuildBuddy for remote caching and execution, significantly improving build performance and developer experience through shared build artifacts and distributed compilation.

## Current State Analysis

### Pain Points

- **Cold Builds**: Every developer/CI run rebuilds everything
- **Duplicate Work**: Same targets built multiple times across team
- **Resource Usage**: Local machines struggle with large builds
- **CI Wait Times**: Long feedback loops on pull requests

### Current Setup

```yaml
# buildbuddy.yaml
actions:
  - name: "Test and push"
    container_image: "ubuntu-24.04"
    resource_requests:
      disk: "50GB"
    steps:
      - run: bazel test //...
      - run: bazel run //images:push_all
```

## BuildBuddy Architecture

### Deployment Components

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: buildbuddy
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: buildbuddy-server
  namespace: buildbuddy
spec:
  serviceName: buildbuddy
  replicas: 3
  template:
    spec:
      containers:
        - name: buildbuddy
          image: gcr.io/flame-build/buildbuddy-app-onprem:latest
          ports:
            - containerPort: 1985 # gRPC
            - containerPort: 8080 # HTTP
          env:
            - name: CACHE_BACKEND
              value: "disk"
            - name: CACHE_DISK_ROOT_DIR
              value: "/data/cache"
          volumeMounts:
            - name: cache-volume
              mountPath: /data/cache
  volumeClaimTemplates:
    - metadata:
        name: cache-volume
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: longhorn
        resources:
          requests:
            storage: 500Gi
```

### Remote Cache Configuration

#### Bazel RC Configuration

```bash
# .bazelrc
# BuildBuddy remote cache
build --remote_cache=grpcs://buildbuddy.jomcgi.dev:443
build --remote_cache_compression
build --remote_download_minimal
build --remote_timeout=3600
build --remote_header=x-buildbuddy-api-key=${BUILDBUDDY_API_KEY}

# Remote execution (optional)
build:remote --remote_executor=grpcs://buildbuddy.jomcgi.dev:443
build:remote --remote_default_exec_properties=OSFamily=linux
build:remote --remote_default_exec_properties=Arch=amd64
build:remote --jobs=200
```

#### Authentication & API Keys

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: buildbuddy-api-keys
  namespace: buildbuddy
type: Opaque
stringData:
  claude-api-key: "bb-api-key-claude-XXXXX"
  ci-api-key: "bb-api-key-ci-XXXXX"
  developer-api-key: "bb-api-key-dev-XXXXX"
```

## Cache Warming Strategy

### Scheduled Cache Warmer

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cache-warmer
  namespace: buildbuddy
spec:
  schedule: "0 */6 * * *" # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: warmer
              image: ghcr.io/jomcgi/cache-warmer:latest
              command:
                - /bin/bash
                - -c
                - |
                  # Build common targets to warm cache
                  bazel build //...
                  bazel test //...
                  bazel build //images:all
```

### Intelligent Cache Warming

```python
# cache_warmer.py
import subprocess
import json
from datetime import datetime, timedelta

class CacheWarmer:
    def __init__(self, buildbuddy_api):
        self.api = buildbuddy_api

    def get_frequently_used_targets(self):
        """Analyze build history to find frequently built targets"""
        query = """
        SELECT target, COUNT(*) as build_count
        FROM builds
        WHERE timestamp > NOW() - INTERVAL '7 days'
        GROUP BY target
        ORDER BY build_count DESC
        LIMIT 100
        """
        return self.api.query(query)

    def warm_targets(self, targets):
        """Build targets to populate cache"""
        for target in targets:
            subprocess.run([
                "bazel", "build",
                "--remote_cache=grpcs://buildbuddy.jomcgi.dev:443",
                target
            ])

    def smart_warm(self):
        """Warm cache based on usage patterns"""
        # Get frequently used targets
        targets = self.get_frequently_used_targets()

        # Also include critical path targets
        critical_targets = [
            "//charts/claude/...",
            "//operators/cloudflare/...",
            "//images:all"
        ]

        all_targets = list(set(targets + critical_targets))
        self.warm_targets(all_targets)
```

## Remote Execution Setup

### Executor Pool Configuration

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: buildbuddy-executor
  namespace: buildbuddy
spec:
  replicas: 5 # Scale based on workload
  template:
    spec:
      containers:
        - name: executor
          image: gcr.io/flame-build/buildbuddy-executor-onprem:latest
          env:
            - name: EXECUTOR_APP_TARGET
              value: "grpcs://buildbuddy-server:1985"
            - name: EXECUTOR_POOL_SIZE
              value: "10"
          resources:
            requests:
              cpu: "4"
              memory: "8Gi"
            limits:
              cpu: "8"
              memory: "16Gi"
```

### Docker-in-Docker for Container Builds

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: executor-config
  namespace: buildbuddy
data:
  config.yaml: |
    executor:
      docker_in_docker: true
      docker_socket: /var/run/docker.sock
      enable_container_builds: true
      container_registries:
        - url: ghcr.io
          username: ${GITHUB_USERNAME}
          password: ${GITHUB_TOKEN}
```

## Developer Experience

### Local Development Integration

```bash
# Developer .bazelrc.local
# Use shared remote cache
build --remote_cache=grpcs://buildbuddy.jomcgi.dev:443
build --remote_cache_compression
build --remote_download_minimal

# Optional: Use remote execution for heavy builds
build:heavy --config=remote
build:heavy --remote_executor=grpcs://buildbuddy.jomcgi.dev:443
```

### IDE Integration

```json
// .vscode/settings.json
{
  "bazel.buildifierExecutable": "buildifier",
  "bazel.enableCodeLens": true,
  "bazel.commandLine.queryExpression": "//...",
  "bazel.commandLine.buildArgs": [
    "--remote_cache=grpcs://buildbuddy.jomcgi.dev:443"
  ]
}
```

### Build Analytics Dashboard

```typescript
interface BuildMetrics {
  cacheHitRate: number;
  avgBuildTime: number;
  savedComputeHours: number;
  topCacheMisses: Target[];
}

// Dashboard components
const BuildBuddyDashboard = () => {
  return (
    <div className="dashboard">
      <MetricCard title="Cache Hit Rate" value="87%" />
      <MetricCard title="Avg Build Time" value="2.3 min" />
      <MetricCard title="Compute Saved" value="142 hrs/week" />

      <TopMissesChart data={topCacheMisses} />
      <BuildTimeGraph data={buildTimeHistory} />
      <CacheGrowthChart data={cacheGrowth} />
    </div>
  );
};
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
name: Build and Test
on: [push, pull_request]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup Bazel
        uses: bazelbuild/setup-bazelisk@v2

      - name: Configure BuildBuddy
        run: |
          echo "build --remote_cache=grpcs://buildbuddy.jomcgi.dev:443" >> .bazelrc.ci
          echo "build --remote_header=x-buildbuddy-api-key=${{ secrets.BUILDBUDDY_API_KEY }}" >> .bazelrc.ci

      - name: Build and Test
        run: |
          bazel --bazelrc=.bazelrc.ci test //...
          bazel --bazelrc=.bazelrc.ci build //images:all
```

### Claude Integration

```typescript
// Claude session with BuildBuddy
interface ClaudeSession {
  buildbuddyApiKey: string;
  cacheNamespace: string; // Isolate cache per session
}

// Bazel commands automatically use remote cache
const runBazel = async (command: string, session: ClaudeSession) => {
  const env = {
    BUILDBUDDY_API_KEY: session.buildbuddyApiKey,
    BAZEL_REMOTE_CACHE: `grpcs://buildbuddy.jomcgi.dev:443`,
    BAZEL_REMOTE_CACHE_NAMESPACE: session.cacheNamespace,
  };

  return exec(`bazel ${command}`, { env });
};
```

## Monitoring & Optimization

### Metrics Collection

```yaml
apiVersion: v1
kind: ServiceMonitor
metadata:
  name: buildbuddy-metrics
  namespace: buildbuddy
spec:
  selector:
    matchLabels:
      app: buildbuddy
  endpoints:
    - port: metrics
      interval: 30s
```

### Key Performance Indicators

- **Cache Hit Rate**: Target > 80%
- **Build Time Reduction**: Target 50-70% improvement
- **Storage Efficiency**: Monitor cache size vs. value
- **Network Bandwidth**: Track cache download/upload rates

### Cache Optimization Rules

```python
class CacheOptimizer:
    def analyze_cache_efficiency(self):
        """Identify inefficient cache entries"""
        # Find large, rarely-used artifacts
        inefficient = self.api.query("""
            SELECT artifact_id, size_bytes, last_accessed
            FROM cache_entries
            WHERE size_bytes > 100000000  -- 100MB
            AND last_accessed < NOW() - INTERVAL '30 days'
        """)
        return inefficient

    def optimize_cache(self):
        """Remove inefficient entries and optimize storage"""
        inefficient = self.analyze_cache_efficiency()
        for entry in inefficient:
            self.api.evict(entry.artifact_id)
```

## Cost Analysis

### Resource Requirements

- **Storage**: 500GB-2TB for cache (Longhorn)
- **Compute**: 5-10 executor pods (4-8 CPU each)
- **Network**: ~100GB/day bandwidth
- **Memory**: 8-16GB per executor

### ROI Calculation

```
Developer Time Saved:
- 10 developers × 30 min/day saved = 5 hrs/day
- 5 hrs/day × $100/hr = $500/day
- Monthly savings: ~$10,000

CI/CD Time Saved:
- 100 builds/day × 10 min saved = 16.7 hrs/day
- Faster feedback = higher productivity
```

## Security Considerations

### Access Control

- **API Key Management**: Unique keys per user/service
- **Namespace Isolation**: Separate cache namespaces
- **Audit Logging**: Track all cache operations
- **Encryption**: TLS for all connections

### Cache Poisoning Prevention

```yaml
# BuildBuddy configuration
security:
  verify_artifacts: true
  artifact_signatures: true
  trusted_executors_only: true
  max_artifact_size: 1GB
```

## Migration Plan

### Phase 1: Setup (Week 1)

- Deploy BuildBuddy to Kubernetes
- Configure storage with Longhorn
- Set up ingress with Cloudflare Tunnel

### Phase 2: Integration (Week 2)

- Update .bazelrc files
- Configure CI/CD pipelines
- Distribute API keys

### Phase 3: Optimization (Week 3)

- Implement cache warming
- Set up monitoring
- Tune cache policies

### Phase 4: Remote Execution (Week 4)

- Deploy executor pool
- Enable for heavy builds
- Monitor and optimize

## Success Metrics

- Build time reduction: > 50%
- Cache hit rate: > 80%
- Developer satisfaction: > 90%
- CI pipeline speed: 2x improvement
- Cost per build: 70% reduction
