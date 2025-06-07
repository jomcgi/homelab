## Kubernetes Integration Testing

This project uses a GitHub Actions workflow (`.github/workflows/integration-test.yaml`) to perform integration tests on the Kubernetes configuration and deployments.

### Overview

The workflow aims to validate that the Kubernetes resources can be deployed successfully in the correct order and that the deployed services are healthy. It uses [Minikube](https://minikube.sigs.k8s.io/docs/) to create a local Kubernetes cluster within the CI environment and [Skaffold](https://skaffold.dev/) to manage the deployments.

### Workflow Steps

1.  **Setup Minikube**: A Minikube cluster is started using the Docker driver.
2.  **Install Skaffold**: The Skaffold CLI is installed.
3.  **Deploy CRDs**: Custom Resource Definitions from `cluster/crd/skaffold.yaml` are deployed first.
4.  **Deploy Services**: Each service from `cluster/services/` is deployed sequentially using its respective `skaffold.yaml` file.
5.  **Health & Configuration Checks**: A script (`scripts/integration-test-checks.sh`) is run to:
    *   Verify that all relevant Pods are `Running` or `Succeeded`.
    *   Check that Deployments and StatefulSets have their desired number of ready replicas.
    *   (Placeholders exist for future checks like service accessibility and specific ConfigMap/Secret validation).

### Triggering the Workflow

The workflow is automatically triggered on:
- Pull requests targeting the `main` branch.

### Interpreting Results

- If the workflow passes, it indicates that all defined Kubernetes resources were deployed successfully and passed the basic health checks.
- If the workflow fails, check the logs for the failed step. This could be due to:
    - Errors during Minikube setup.
    - Errors during Skaffold deployment (e.g., image build failures, resource apply failures).
    - Failures in the health and configuration checks script (e.g., Pods not ready, Deployments not scaling correctly).

### Local Execution (Conceptual)

While this workflow is designed for CI, the general steps can be reproduced locally if you have Minikube and Skaffold installed:
1. Start Minikube: `minikube start`
2. Deploy CRDs: `skaffold run -f cluster/crd/skaffold.yaml`
3. Deploy Services: `skaffold run -f cluster/services/your-service/skaffold.yaml` (repeat for each service)
4. Run checks: `scripts/integration-test-checks.sh` (ensure your `kubectl` context is pointing to Minikube)
