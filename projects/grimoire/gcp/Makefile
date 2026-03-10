PROJECT_ID    := h0melab
REGION        := us-west1
FIRESTORE_DB  := grimoire
GCS_BUCKET    := h0melab-grimoire-sourcebooks
API_IMAGE     := gcr.io/$(PROJECT_ID)/grimoire-api
INGEST_IMAGE  := gcr.io/$(PROJECT_ID)/grimoire-ingest

# ──────────────────────────────────────────────
# Bootstrap — run once
# ──────────────────────────────────────────────

.PHONY: setup
setup: setup-project setup-apis setup-firestore setup-storage setup-artifact-registry
	@echo ""
	@echo "GCP infrastructure ready."
	@echo "Next steps:"
	@echo "  1. Create Gemini API key: https://aistudio.google.com/apikey"
	@echo "  2. Store Gemini API key in 1Password (vault: Homelab, item: grimoire-gemini-api-key)"
	@echo "  3. Deploy API: make deploy-api"
	@echo "  4. Ingest a sourcebook: make ingest PDF=gs://$(GCS_BUCKET)/phb.pdf"

setup-project:
	gcloud config set project $(PROJECT_ID)

setup-apis:
	gcloud services enable \
		firestore.googleapis.com \
		run.googleapis.com \
		storage.googleapis.com \
		artifactregistry.googleapis.com \
		generativelanguage.googleapis.com \
		aiplatform.googleapis.com

setup-firestore:
	gcloud firestore databases create \
		--database=$(FIRESTORE_DB) \
		--location=$(REGION) \
		--type=firestore-native 2>/dev/null || true
	@echo "Firestore database '$(FIRESTORE_DB)' ready in $(REGION)"
	@echo "Create vector index manually in console or via gcloud alpha:"
	@echo "   Collection: sourcebook_chunks"
	@echo "   Field: embedding, Dimensions: 768, Distance: COSINE"

setup-storage:
	gcloud storage buckets create gs://$(GCS_BUCKET) \
		--location=$(REGION) \
		--uniform-bucket-level-access 2>/dev/null || true
	@echo "Cloud Storage bucket '$(GCS_BUCKET)' ready"

setup-artifact-registry:
	gcloud artifacts repositories create grimoire \
		--repository-format=docker \
		--location=$(REGION) 2>/dev/null || true
	@echo "Artifact Registry 'grimoire' ready"

# ──────────────────────────────────────────────
# Deploy — push containers + update Cloud Run
# ──────────────────────────────────────────────

build-api:
	docker build -t $(API_IMAGE):latest apps/api/
	docker push $(API_IMAGE):latest

build-ingest:
	docker build -t $(INGEST_IMAGE):latest apps/ingest/
	docker push $(INGEST_IMAGE):latest

deploy-api: build-api
	gcloud run deploy grimoire-api \
		--image=$(API_IMAGE):latest \
		--region=$(REGION) \
		--platform=managed \
		--allow-unauthenticated \
		--set-env-vars="GCP_PROJECT_ID=$(PROJECT_ID),FIRESTORE_DATABASE=$(FIRESTORE_DB),CF_ACCESS_TEAM=your-team.cloudflareaccess.com" \
		--set-secrets="GOOGLE_API_KEY=google-api-key:latest" \
		--min-instances=0 \
		--max-instances=2 \
		--memory=256Mi \
		--cpu=1 \
		--concurrency=80
	@echo "API deployed to Cloud Run"
	@echo "   Note: Cloud Run uses GOOGLE_API_KEY for Gemini Flash (RAG) + embeddings"
	@echo "   The homelab WS Gateway uses a separate secret synced from 1Password"

# ──────────────────────────────────────────────
# Ingest — process a sourcebook PDF
# ──────────────────────────────────────────────

upload-pdf:
	@test -n "$(FILE)" || (echo "Usage: make upload-pdf FILE=./phb.pdf" && exit 1)
	gcloud storage cp $(FILE) gs://$(GCS_BUCKET)/

ingest:
	@test -n "$(PDF)" || (echo "Usage: make ingest PDF=gs://$(GCS_BUCKET)/phb.pdf" && exit 1)
	gcloud run jobs execute grimoire-ingest \
		--region=$(REGION) \
		--set-env-vars="PDF_URI=$(PDF),GCP_PROJECT_ID=$(PROJECT_ID),FIRESTORE_DATABASE=$(FIRESTORE_DB)" \
		--wait

# ──────────────────────────────────────────────
# Teardown — remove everything
# ──────────────────────────────────────────────

teardown:
	@echo "This will delete all Grimoire GCP resources. Ctrl+C to cancel."
	@sleep 5
	gcloud run services delete grimoire-api --region=$(REGION) --quiet || true
	gcloud run jobs delete grimoire-ingest --region=$(REGION) --quiet || true
	gcloud storage rm -r gs://$(GCS_BUCKET) || true
	gcloud firestore databases delete --database=$(FIRESTORE_DB) --quiet || true
	gcloud artifacts repositories delete grimoire --location=$(REGION) --quiet || true
	@echo "GCP resources deleted. Project $(PROJECT_ID) still exists."
