# Refactoring Plan: Annotation and CRD Strategy

This plan outlines the steps to refactor the Cloudflare operator to use a hybrid annotation/CRD model. The goal is to use annotations on `v1.Service` resources to trigger behavior and reference complex policy configurations defined in a dedicated `AccessPolicy` Custom Resource Definition (CRD).

This approach aligns with Kubernetes best practices by separating concerns, improving reusability, and providing a more robust, validated API for managing policies.

---

## 1. Create the `AccessPolicy` CRD

The first step is to define the `AccessPolicy` CRD. This resource will represent a reusable Cloudflare Access Policy.

**File:** `helm/cloudflare-operator/crds/accesspolicy.cloudflare.io.yaml`

**Definition:**
```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: accesspolicies.cloudflare.io
spec:
  group: cloudflare.io
  scope: Namespaced
  names:
    plural: accesspolicies
    singular: accesspolicy
    kind: AccessPolicy
    shortNames:
    - cfap
  versions:
  - name: v1
    served: true
    storage: true
    schema:
      openAPIV3Schema:
        type: object
        properties:
          spec:
            type: object
            required: ["decision", "include"]
            properties:
              decision:
                type: string
                enum: ["allow", "deny", "bypass"]
                description: "The action to take when a request matches the policy."
              include:
                type: array
                description: "Rules that must be met for the policy to apply."
                items:
                  type: object
                  properties:
                    emails:
                      type: array
                      items: { type: string, format: email }
                    emailDomains:
                      type: array
                      items: { type: string }
                    accessGroups:
                      type: array
                      items: { type: string }
                    # Future rule types can be added here
              # 'require' and 'exclude' can be added later for more complex policies
          status:
            type: object
            properties:
              policyId:
                type: string
                description: "The ID of the policy in Cloudflare."
              ready:
                type: boolean
                description: "True if the policy is successfully provisioned in Cloudflare."
              conditions:
                type: array
                items:
                  # Standard Kubernetes conditions structure
                  type: object
                  properties:
                    type: { type: string }
                    status: { type: string }
                    reason: { type: string }
                    message: { type: string }
                    lastTransitionTime: { type: string, format: date-time }
```

---

## 2. Implement the `AccessPolicyReconciler`

A new controller will be created to manage the lifecycle of `AccessPolicy` resources.

**File:** `internal/controller/accesspolicy_controller.go`

**Responsibilities:**
- **Watch `AccessPolicy` resources.**
- **Create/Update/Delete Policies in Cloudflare:** When an `AccessPolicy` CR is created, updated, or deleted, the reconciler will make the corresponding API calls to Cloudflare.
- **Update Status:** The reconciler will update the `status` subresource of the `AccessPolicy` CR with the Cloudflare Policy ID and the provisioning status (`ready`, `conditions`).
- **Finalizer:** Use a finalizer (`accesspolicy.cloudflare.io/cleanup`) to ensure the policy is deleted from Cloudflare before the CR is removed from the Kubernetes API.

---

## 3. Refactor the `ServiceReconciler`

The existing `ServiceReconciler` will be modified to consume the new `AccessPolicy` CRD instead of using ConfigMaps or hardcoded values.

**File:** `internal/controller/service_controller.go`

**Changes:**
- **Remove `resolvePolicyReference`:** This function will be deprecated.
- **Modify Reconciliation Logic:**
    1. When a `Service` is reconciled, check for the `cloudflare.io/access-policy` annotation.
    2. If the annotation exists, the reconciler will fetch the corresponding `AccessPolicy` CR from the cluster. It will need to know which namespace to look in (e.g., from an operator-level configuration or another annotation like `cloudflare.io/access-policy-namespace`).
    3. It will check the `status` of the `AccessPolicy` CR. If `status.ready` is `true`, it will retrieve the `status.policyId`.
    4. This `policyId` will then be used to create the Zero Trust Application.
    5. If the `AccessPolicy` is not found or not ready, the `ServiceReconciler` should requeue the request and potentially report a non-ready status on the `Service` via an event.
- **Cleanup Logic:** The `ServiceReconciler`'s finalizer will only be responsible for deleting the Cloudflare *Application*. It will no longer be responsible for deleting the *Policy*, as the policy's lifecycle is now managed independently by the `AccessPolicyReconciler`.

---

## 4. Update Operator Setup and RBAC

The main operator setup and permissions need to be updated.

**File:** `cmd/manager/main.go`
- **Register Scheme:** Add the new `accesspolicies.cloudflare.io/v1` scheme.
- **Setup New Controller:** Instantiate and start the new `AccessPolicyReconciler`.

**File:** `helm/cloudflare-operator/templates/rbac.yaml`
- **Add Permissions:** Update the `ClusterRole` to grant the operator permissions to `get`, `list`, `watch`, `create`, `update`, `patch`, and `delete` `accesspolicies` resources and their `status` subresources.

```yaml
# Add to ClusterRole rules
- apiGroups:
  - cloudflare.io
  resources:
  - accesspolicies
  verbs:
  - create
  - delete
  - get
  - list
  - patch
  - update
  - watch
- apiGroups:
  - cloudflare.io
  resources:
  - accesspolicies/status
  verbs:
  - get
  - patch
  - update
```

---

## 5. Testing Strategy

- **Unit Tests:** Write unit tests for the `AccessPolicyReconciler`'s core logic using a mocked Cloudflare client.
- **Integration Tests (`envtest`):**
    - Write a test that creates an `AccessPolicy` CR and verifies the controller updates its status correctly.
    - Write a test that creates a `Service` with an `access-policy` annotation and an `AccessPolicy` CR. Verify that the `ServiceReconciler` correctly links the two and creates the Cloudflare Application with the right Policy ID.
