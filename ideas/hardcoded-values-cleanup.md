# Hardcoded Values Cleanup

Move hardcoded values from templates to `values.yaml` for better configurability and maintainability.

## Priority: Medium

These changes improve chart reusability and follow Helm best practices, but are not blocking issues.

## Charts with Hardcoded Values

### api-gateway

| Location         | Current Value               | Recommended                            |
| ---------------- | --------------------------- | -------------------------------------- |
| `values.yaml:20` | `tag: "latest"` for kubectl | Pin to specific version (e.g., `1.31`) |

### claude

| Location             | Current Value            | Recommended                                                   |
| -------------------- | ------------------------ | ------------------------------------------------------------- |
| `deployment.yaml:39` | `bitnami/kubectl:latest` | Add `leaderElection.image` to values.yaml with pinned version |
| `deployment.yaml:74` | `nginx:1.27-alpine`      | Add `nginx.image` to values.yaml                              |

### cloudflare-tunnel

| Location              | Current Value          | Recommended                          |
| --------------------- | ---------------------- | ------------------------------------ |
| `envoy-configmap:117` | Istio proxyv2 `1.20.0` | Add `envoy.image.tag` to values.yaml |
| `configmap:15`        | `no-autoupdate: true`  | Make configurable                    |

### gh-arc-runners

| Location                            | Current Value                       | Recommended                                  |
| ----------------------------------- | ----------------------------------- | -------------------------------------------- |
| `Chart.yaml:13`, `values.yaml:6,47` | `https://github.com/jomcgi/homelab` | Add `github.configUrl` as configurable value |

### marine

| Location                      | Current Value                                            | Recommended                                         |
| ----------------------------- | -------------------------------------------------------- | --------------------------------------------------- |
| `frontend-deployment.yaml:56` | `PUBLIC_DIR: /app/public/websites/ships.jomcgi.dev/dist` | Add `frontend.publicDir` to values.yaml             |
| `values.yaml:128`             | `cors.origins: "http://localhost:3000"`                  | Document as dev-only or parameterize for production |

### stargazer

| Location                     | Current Value                        | Recommended                                  |
| ---------------------------- | ------------------------------------ | -------------------------------------------- |
| `deployment-api.yaml:38`     | `nginxinc/nginx-unprivileged:alpine` | Add `api.nginx.image` to values.yaml         |
| `configmap-nginx.yaml`       | `Access-Control-Allow-Origin: *`     | Add `api.cors.allowedOrigins` to values.yaml |
| `configmap-nginx.yaml:37,54` | Hardcoded data paths                 | Add `api.dataPaths` to values.yaml           |

### trips

| Location                      | Current Value           | Recommended                                 |
| ----------------------------- | ----------------------- | ------------------------------------------- |
| `api-deployment.yaml:81`      | CORS origins hardcoded  | Add `api.config.corsOrigins` to values.yaml |
| `values.yaml:62`              | `tag: "latest"` for API | Use specific version tags                   |
| `nginx-deployment.yaml:10`    | `replicas: 1` hardcoded | Add `nginx.replicas` to values.yaml         |
| `imgproxy-deployment.yaml:10` | `replicas: 2` hardcoded | Add `imgproxy.replicas` to values.yaml      |

## Implementation Notes

1. When adding new values, include sensible defaults that match current behavior
2. Add comments explaining what each value controls
3. Consider grouping related values under component prefixes (e.g., `nginx.image`, `nginx.replicas`)
4. For CORS origins, consider using environment-specific overlays rather than chart defaults
