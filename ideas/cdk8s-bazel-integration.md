# Integrate CDK8S Dependencies with Bazel

## Problem

The `cdk8s/` directory contains Python code that uses:
- `imports/k8s` - Generated Kubernetes type bindings from `cdk8s import`
- `lib/` - Shared constructs

These are not pip packages, so Gazelle fails to resolve them:
```
gazelle: ERROR: failed to validate dependencies for target "//cdk8s/cloudflare-operator-test":
"imports.k8s" is an invalid dependency
```

Currently ignored via `# gazelle:exclude cdk8s` in the root BUILD file.

## Solution Options

### Option 1: Create proper py_library targets

Create BUILD files for the local modules:

```starlark
# cdk8s/lib/BUILD
py_library(
    name = "lib",
    srcs = ["__init__.py"],
    visibility = ["//cdk8s:__subpackages__"],
)

# cdk8s/cloudflare-operator-test/imports/k8s/BUILD
py_library(
    name = "k8s",
    srcs = glob(["*.py"]),
    deps = ["@pip//jsii", "@pip//typeguard", ...],  # cdk8s runtime deps
    visibility = ["//cdk8s:__subpackages__"],
)
```

Then add gazelle resolve directives:
```starlark
# gazelle:resolve py imports.k8s //cdk8s/cloudflare-operator-test/imports/k8s
# gazelle:resolve py lib //cdk8s/lib
```

### Option 2: Run cdk8s synth as a Bazel genrule

Generate the imports at build time rather than checking them in:

```starlark
genrule(
    name = "cdk8s_imports",
    srcs = ["cdk8s.yaml"],
    outs = ["imports/k8s/__init__.py"],
    cmd = "cdk8s import -l python -o $(@D)/imports",
)
```

## Considerations

- The `imports/k8s/__init__.py` is 2.7MB of generated code
- jsii runtime has complex dependencies
- cdk8s is experimental in this repo (see `ideas/cdk8s-migration.md`)

## Recommendation

Since cdk8s is experimental and not used in production, defer proper Bazel integration until cdk8s is promoted to a primary workflow.
