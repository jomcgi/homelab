# Unified Frontend Build & Deployment Strategy

## Goals

1. **Unified asset bundling** - Single Bazel-based approach for all Vite/frontend builds
2. **Private serving with internal API access** - Frontend served via tunnel with proxy to cluster APIs
3. **rules_wrangler** - Bazel rules for pushing built assets to Cloudflare Pages

## Current State

| Project | Framework | Build System | Deployment | Notes |
|---------|-----------|--------------|------------|-------|
| **ships.jomcgi.dev** | React + Vite | Bazel (js_run_binary) | K8s container | Gold standard for K8s |
| **trips.jomcgi.dev** | React + Vite | npm only | Cloudflare Pages | Works fine as-is |
| **claude/frontend** | React + Vite + Express | filegroup only | K8s (runtime build) | Has native modules |
| **jomcgi.dev** | Astro | npm only | Cloudflare Pages | Different framework |
| **hikes.jomcgi.dev** | Static HTML | None | Cloudflare Pages | No build needed |

## Architecture Decision

### Two Serving Patterns

| Pattern | Use Case | Build | Serve | API Access |
|---------|----------|-------|-------|------------|
| **K8s + Proxy** | Private sites needing cluster APIs | Bazel Vite | Bun/Node proxy in pod | In-cluster routing |
| **CF Pages** | Public static sites | Bazel Vite | Cloudflare CDN | N/A or separate tunnel |

**The proxy pattern (ships-frontend) remains the right choice** for private sites that need to call internal APIs. It provides:
- Single tunnel endpoint (subdomain → pod)
- In-cluster API routing without auth complexity
- WebSocket support for real-time features

## Implementation Plan

### Phase 1: Unified Vite Build Macro

Create `tools/js/vite_build.bzl` to standardize frontend builds.

**File:** `tools/js/vite_build.bzl`
```starlark
"""Unified Vite build macro for React/frontend projects."""

load("@aspect_rules_js//js:defs.bzl", "js_library", "js_run_binary")
load("@aspect_rules_js//npm:defs.bzl", "npm_link_all_packages")

def vite_build(
    name,
    srcs,
    deps = [],
    out_dir = "dist",
    config_file = "vite.config.js",
    build_tool = "vite",  # "vite" or "astro"
    visibility = None):
    """Standard Vite/Astro build for frontend projects.

    Args:
      build_tool: "vite" for React/Vue apps, "astro" for Astro sites
                  (Astro uses Vite internally, same output structure)

    Creates:
      :node_modules - Linked npm packages
      :src - Source library
      :{name} - Build output
      :{name}_dist - Filegroup of built dist (for consumption)
    """
    npm_link_all_packages(name = "node_modules")

    # Get build tool binary
    if build_tool == "astro":
        tool_target = "@npm//websites/{pkg}:astro/package_json.bzl".format(
            pkg = native.package_name().split("/")[-1]
        )
        build_args = ["build"]
    else:
        tool_target = "@npm//websites/{pkg}:vite/package_json.bzl".format(
            pkg = native.package_name().split("/")[-1]
        )
        build_args = ["build"]

    js_library(
        name = "src",
        srcs = srcs + ([config_file] if config_file else []),
        deps = [":node_modules/" + d for d in deps],
    )

    js_run_binary(
        name = name,
        srcs = [":src"],
        args = build_args,
        chdir = native.package_name(),
        out_dirs = [out_dir],
        tool = tool_target,
    )

    native.filegroup(
        name = name + "_dist",
        srcs = [":" + name],
        visibility = visibility,
    )
```

### Phase 2: Create rules_wrangler

Create Bazel rules for Cloudflare Pages deployment, following the `tools/oci/` pattern.

**Directory:** `tools/wrangler/`

```
tools/wrangler/
├── BUILD
├── wrangler_pages.bzl      # Rule + macro definitions
└── wrangler_push.sh.tpl    # Push script template
```

**File:** `tools/wrangler/wrangler_pages.bzl`
```starlark
"""Bazel rules for Cloudflare Pages deployment."""

def _wrangler_pages_push_impl(ctx):
    # Generate push script from template
    script = ctx.actions.declare_file(ctx.label.name + "_push.sh")
    ctx.actions.expand_template(
        template = ctx.file._template,
        output = script,
        substitutions = {
            "{{WRANGLER}}": ctx.executable._wrangler.short_path,
            "{{DIST_DIR}}": ctx.file.dist.short_path,
            "{{PROJECT_NAME}}": ctx.attr.project_name,
        },
        is_executable = True,
    )

    runfiles = ctx.runfiles(files = [ctx.file.dist, ctx.executable._wrangler])
    return [DefaultInfo(executable = script, runfiles = runfiles)]

wrangler_pages_push = rule(
    implementation = _wrangler_pages_push_impl,
    attrs = {
        "dist": attr.label(allow_single_file = True, mandatory = True),
        "project_name": attr.string(mandatory = True),
        "_wrangler": attr.label(
            default = "@npm//:wrangler",
            executable = True,
            cfg = "exec",
        ),
        "_template": attr.label(
            default = "//tools/wrangler:wrangler_push.sh.tpl",
            allow_single_file = True,
        ),
    },
    executable = True,
)

def wrangler_pages(name, dist, project_name, visibility = None):
    """High-level macro for Cloudflare Pages deployment.

    Creates:
      :{name}.push - Executable target to deploy to CF Pages
    """
    wrangler_pages_push(
        name = name + ".push",
        dist = dist,
        project_name = project_name,
        visibility = visibility,
    )
```

**File:** `tools/wrangler/wrangler_push.sh.tpl`
```bash
#!/usr/bin/env bash
set -euo pipefail

# Bazel runfiles handling
if [[ -n "${RUNFILES_DIR:-}" ]]; then
    RUNFILES="${RUNFILES_DIR}"
elif [[ -n "${BASH_SOURCE[0]:-}" ]]; then
    RUNFILES="${BASH_SOURCE[0]}.runfiles"
fi

WRANGLER="${RUNFILES}/{{WRANGLER}}"
DIST_DIR="${RUNFILES}/{{DIST_DIR}}"

# Deploy to Cloudflare Pages
# CLOUDFLARE_API_TOKEN must be set in environment
exec "${WRANGLER}" pages deploy "${DIST_DIR}" \
    --project-name="{{PROJECT_NAME}}" \
    --commit-dirty=true
```

### Phase 3: Frontend Server Template

Create a reusable Bun server template for K8s deployments.

**File:** `tools/js/frontend_server.ts.tpl`
```typescript
// Template for frontend servers with API proxying
const PORT = process.env.PORT || "3000";
const PUBLIC_DIR = process.env.PUBLIC_DIR || "./dist";
const API_UPSTREAM = process.env.API_UPSTREAM || "http://localhost:8000";

const server = Bun.serve({
  port: parseInt(PORT),
  async fetch(req) {
    const url = new URL(req.url);

    // API proxy
    if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/ws/")) {
      return proxyRequest(req, API_UPSTREAM);
    }

    // Static files
    const file = Bun.file(`${PUBLIC_DIR}${url.pathname}`);
    if (await file.exists()) {
      return new Response(file);
    }

    // SPA fallback
    return new Response(Bun.file(`${PUBLIC_DIR}/index.html`));
  },
});
```

### Phase 4: Migrate Existing Projects

**ships.jomcgi.dev** - Already uses Bazel, update to use shared macro:
```starlark
load("//tools/js:vite_build.bzl", "vite_build")

vite_build(
    name = "build",
    srcs = glob(["src/**/*", "public/**/*"]) + ["index.html", "package.json"],
    deps = ["react", "react-dom", "maplibre-gl", "@vitejs/plugin-react"],
    visibility = ["//services/ships-frontend:__pkg__"],
)
```

**trips.jomcgi.dev** - Add Bazel BUILD for CF Pages deployment:
```starlark
load("//tools/js:vite_build.bzl", "vite_build")
load("//tools/wrangler:wrangler_pages.bzl", "wrangler_pages")

vite_build(
    name = "build",
    srcs = glob(["src/**/*", "public/**/*"]) + ["index.html", "package.json"],
    deps = ["react", "react-dom", "maplibre-gl", "wouter", "lucide-react"],
)

wrangler_pages(
    name = "trips",
    dist = ":build_dist",
    project_name = "trips-jomcgi-dev",
)
```

Deploy with: `bazel run //websites/trips.jomcgi.dev:trips.push`

### Phase 5: Centralized Push Targets

**File:** `websites/BUILD`
```starlark
# Push all static sites to Cloudflare Pages
sh_binary(
    name = "push_all_pages",
    srcs = ["push_all_pages.sh"],
    data = [
        "//websites/trips.jomcgi.dev:trips.push",
        "//websites/jomcgi.dev:homepage.push",
        "//websites/hikes.jomcgi.dev:hikes.push",
    ],
)
```

## File Changes Summary

| File | Action | Purpose |
|------|--------|---------|
| `tools/js/vite_build.bzl` | Create | Shared Vite build macro |
| `tools/js/BUILD` | Create | Package for JS tools |
| `tools/wrangler/wrangler_pages.bzl` | Create | CF Pages push rule |
| `tools/wrangler/wrangler_push.sh.tpl` | Create | Push script template |
| `tools/wrangler/BUILD` | Create | Package for wrangler tools |
| `websites/ships.jomcgi.dev/BUILD` | Update | Use shared macro |
| `websites/trips.jomcgi.dev/BUILD` | Create | Add Bazel build + CF push |
| `websites/jomcgi.dev/BUILD` | Create | Add Astro build + CF push |
| `websites/hikes.jomcgi.dev/BUILD` | Create | Add CF push (no build needed) |
| `pnpm-workspace.yaml` | Update | Add trips.jomcgi.dev |
| `MODULE.bazel` | Update | Add wrangler npm dependency |

## Verification

1. **Build verification:**
   ```bash
   bazel build //websites/ships.jomcgi.dev:build
   bazel build //websites/trips.jomcgi.dev:build
   ```

2. **Push verification (dry-run):**
   ```bash
   # Test wrangler is available
   bazel run //websites/trips.jomcgi.dev:trips.push -- --help
   ```

3. **Full deployment test:**
   ```bash
   export CLOUDFLARE_API_TOKEN="..."
   bazel run //websites/trips.jomcgi.dev:trips.push
   ```

## Decisions

1. **Astro handling** → Use same `vite_build` macro (Astro uses Vite internally)
2. **Wrangler auth** → Environment variable (`CLOUDFLARE_API_TOKEN`)
3. **Claude frontend** → Investigate Bazel native module compilation

## Phase 6: Claude Frontend Native Modules (Investigation)

The claude/frontend has `better-sqlite3` which requires native compilation. To bring it into the unified build:

**Research needed:**
- `rules_nodejs` native module support via `node-gyp`
- Pre-built binaries from `@aspect_rules_js`
- Cross-compilation for multi-arch (x86_64 + aarch64)

**Potential approach:**
```starlark
# If aspect_rules_js supports native modules:
npm_link_all_packages(
    name = "node_modules",
    native_modules = ["better-sqlite3"],
)
```

**Fallback:** If native compilation proves too complex, keep claude/frontend on runtime builds but use the same `vite_build` macro for the frontend portion, with a separate server build step.

**Files to investigate:**
- `charts/claude/frontend/package.json` - Native dependencies
- `charts/claude/image/apko.yaml` - Build tools available (python, build-base)
- aspect_rules_js docs on native modules
