IMG ?= cloudflare-operator:latest
VERSION ?= 0.1.0

.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.PHONY: test
test: ## Run tests
	@echo "Running go tests..."
	@go test -short -parallel 4 ./...

.PHONY: test-coverage
test-coverage: ## Run tests with coverage
	go test ./... -coverprofile cover.out

.PHONY: test-ci
test-ci: ## Run tests optimized for CI (build verification only since no tests exist)
	@echo "Running CI tests (fast mode)..."
	@go test -short -parallel 4 ./...

.PHONY: verify-build
verify-build: ## Verify all packages build successfully
	@echo "Verifying all packages build..."
	@go build ./...

.PHONY: build
build: ## Build manager binary
	go build -o bin/manager cmd/manager/main.go

.PHONY: run
run: ## Run a controller from your host
	go run cmd/manager/main.go

.PHONY: docker-build
docker-build: ## Build docker image with the manager
	docker build -t ${IMG} .

.PHONY: minikube-build
minikube-build: ## Build docker image for minikube
	eval $$(minikube docker-env) && docker build -t ${IMG} .

.PHONY: minikube-deploy
minikube-deploy: minikube-build ## Build and restart operator in minikube
	kubectl rollout restart deployment cloudflare-operator

.PHONY: debug-deploy
debug-deploy: ## Build with timestamp tag, load to minikube, and deploy for debugging
	$(eval DEBUG_TAG := debug-$(shell date +%s))
	@echo "Building debug version: $(DEBUG_TAG)"
	docker build -t cloudflare-operator:$(DEBUG_TAG) .
	minikube image load cloudflare-operator:$(DEBUG_TAG)
	kubectl set image deployment/cloudflare-operator manager=cloudflare-operator:$(DEBUG_TAG) -n cloudflare
	kubectl rollout status deployment/cloudflare-operator -n cloudflare --timeout=60s
	@echo "✅ Deployed debug version: $(DEBUG_TAG)"

.PHONY: docker-push
docker-push: ## Push docker image with the manager
	docker push ${IMG}

.PHONY: install
install: ## Install CRDs into the K8s cluster specified in ~/.kube/config
	kubectl apply -f config/crd/

.PHONY: uninstall
uninstall: ## Uninstall CRDs from the K8s cluster specified in ~/.kube/config
	kubectl delete -f config/crd/

.PHONY: deploy
deploy: ## Deploy controller to the K8s cluster specified in ~/.kube/config
	helm upgrade --install cloudflare-operator ./helm/cloudflare-operator

.PHONY: undeploy
undeploy: ## Undeploy controller from the K8s cluster specified in ~/.kube/config
	helm uninstall cloudflare-operator

.PHONY: helm-package
helm-package: ## Package the Helm chart
	helm package ./helm/cloudflare-operator

.PHONY: lint
lint: ## Run golangci-lint
	golangci-lint run

.PHONY: fmt
fmt: ## Run go fmt against code
	go fmt ./...

.PHONY: vet
vet: ## Run go vet against code
	go vet ./...

.PHONY: test-setup
test-setup: ## Complete test setup: wipe minikube, build image, load to minikube, deploy with secrets
	@echo "🔄 Starting complete test setup..."
	@echo "1/6 Wiping minikube cluster..."
	minikube delete || true
	@echo "2/6 Starting fresh minikube cluster..."
	minikube start
	@echo "3/6 Building operator image..."
	make build
	make docker-build
	@echo "4/6 Loading image to minikube..."
	minikube image load cloudflare-operator:latest
	@echo "5/6 Creating namespace and secrets..."
	kubectl create namespace cloudflare
	@echo "Deploying secret for operator"; \
	kubectl create secret generic cloudflare-creds \
		--from-literal=api-token=$$(cat /home/jomcgi/homelab/cloudflare-creds.json | jq -r '.token') \
		--from-literal=account-id=$$(cat /home/jomcgi/homelab/cloudflare-creds.json | jq -r '.account_id') \
		-n cloudflare;
	@echo "6/6 Deploying operator..."
	helm install cloudflare-operator ./helm/cloudflare-operator --namespace cloudflare
	@echo "✅ Test setup complete! Operator deployed and running."
	@echo "📋 Next steps:"
	@echo "  - Check status: kubectl get pods -n cloudflare"
	@echo "  - View logs: kubectl logs -n cloudflare -l app.kubernetes.io/name=cloudflare-operator"
	@echo "  - Test removal: make test-cleanup"

.PHONY: test-cleanup
test-cleanup: ## Test operator removal and cleanup
	@echo "🧹 Testing operator removal..."
	helm uninstall cloudflare-operator -n cloudflare
	@echo "📋 Checking cleanup results..."
	kubectl get all,secrets -n cloudflare
	@echo "✅ Cleanup test complete!"