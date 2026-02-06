# Bazel Tooling Optimization with BuildBuddy

## Overview

Deploy BuildBuddy for remote caching and execution to significantly improve build performance through shared artifacts and distributed compilation.

## Current Pain Points

- Cold builds rebuild everything per developer/CI run
- Duplicate work across team members
- Local machines struggle with large builds
- Long CI feedback loops

## BuildBuddy Architecture

```
┌─────────────────────────────────────────────────────────┐
│ BuildBuddy Server (StatefulSet)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ HTTP Server  │  │ gRPC Server  │  │ Executor Pool│  │
│  │   :8080      │  │   :1985      │  │   (5 pods)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                 │                   │         │
│         ├─────────────────┴───────────────────┤         │
│         │                                     │         │
│  ┌──────▼─────────────────────────────────────▼──────┐  │
│  │ Cache Storage (Longhorn 500GB-2TB)               │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         ▲                                     ▲
         │                                     │
    ┌────┴──────┐                         ┌───┴────┐
    │ CI Runner │                         │  Dev   │
    │  (bazel)  │                         │ (bazel)│
    └───────────┘                         └────────┘

Flow: Build request → Cache check → Hit: Return / Miss: Build + Cache
```

### Deployment Configuration

```yaml
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

## Bazel Configuration

### Remote Cache Setup

```bash
# .bazelrc
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

### Authentication

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

### Scheduled Warmer

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
                  bazel build //...
                  bazel test //...
                  bazel build //images:all
```

### Intelligent Warming

```python
# cache_warmer.py
class CacheWarmer:
    def get_frequently_used_targets(self):
        """Analyze build history to find frequent targets"""
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
```

## Remote Execution

### Executor Pool

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: buildbuddy-executor
  namespace: buildbuddy
spec:
  replicas: 5
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

### Container Build Support

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

### Local Integration

```bash
# Developer .bazelrc.local
build --remote_cache=grpcs://buildbuddy.jomcgi.dev:443
build --remote_cache_compression
build --remote_download_minimal

# Optional: Use remote execution for heavy builds
build:heavy --config=remote
```

### IDE Integration

```json
// .vscode/settings.json
{
  "bazel.commandLine.buildArgs": [
    "--remote_cache=grpcs://buildbuddy.jomcgi.dev:443"
  ]
}
```

## CI/CD Integration

### GitHub Actions

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

### Key Metrics

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

### Performance Targets

- **Cache Hit Rate**: > 80%
- **Build Time Reduction**: 50-70% improvement
- **Storage Efficiency**: Monitor cache size vs. value
- **Network Bandwidth**: Track download/upload rates

### Cache Optimization

```python
class CacheOptimizer:
    def analyze_cache_efficiency(self):
        """Identify inefficient cache entries"""
        inefficient = self.api.query("""
            SELECT artifact_id, size_bytes, last_accessed
            FROM cache_entries
            WHERE size_bytes > 100000000  -- 100MB
            AND last_accessed < NOW() - INTERVAL '30 days'
        """)
        return inefficient

    def optimize_cache(self):
        """Remove inefficient entries"""
        inefficient = self.analyze_cache_efficiency()
        for entry in inefficient:
            self.api.evict(entry.artifact_id)
```

## Security

### Access Control

- API key management per user/service
- Namespace isolation for cache separation
- Audit logging for all operations
- TLS encryption for connections

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

1. **Week 1**: Deploy BuildBuddy to Kubernetes, configure storage
2. **Week 2**: Update .bazelrc, configure CI/CD, distribute API keys
3. **Week 3**: Implement cache warming, set up monitoring
4. **Week 4**: Deploy executor pool, enable remote execution

## Resource Requirements

- **Storage**: 500GB-2TB for cache (Longhorn)
- **Compute**: 5-10 executor pods (4-8 CPU each)
- **Network**: ~100GB/day bandwidth
- **Memory**: 8-16GB per executor

## Success Metrics

- Build time reduction: > 50%
- Cache hit rate: > 80%
- Developer satisfaction: > 90%
- CI pipeline speed: 2x improvement
