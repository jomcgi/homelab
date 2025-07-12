IMG ?= cloudflare-operator:latest
VERSION ?= 0.1.0

.PHONY: help
help: ## Display this help.
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

.PHONY: test
test: ## Run tests
	go test ./... -coverprofile cover.out

.PHONY: build
build: ## Build manager binary
	go build -o bin/manager cmd/manager/main.go

.PHONY: run
run: ## Run a controller from your host
	go run cmd/manager/main.go

.PHONY: docker-build
docker-build: ## Build docker image with the manager
	docker build -t ${IMG} .

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