# Makefile
.PHONY: setup-gcp

setup-gcp: setup-gcp-project setup-gcp-firestore setup-gcp-storage setup-gcp-run setup-gcp-api-keys

setup-gcp-project:
	gcloud projects create grimoire-prod --name="Grimoire" || true
	gcloud config set project grimoire-prod
	gcloud services enable \
		firestore.googleapis.com \
		run.googleapis.com \
		storage.googleapis.com \
		aiplatform.googleapis.com \
		generativelanguage.googleapis.com

setup-gcp-firestore:
	gcloud firestore databases create \
		--database=grimoire \
		--location=us-west1 \
		--type=firestore-native

setup-gcp-storage:
	gcloud storage buckets create gs://grimoire-sourcebooks \
		--location=us-west1 \
		--uniform-bucket-level-access

setup-gcp-run:
	@echo "Cloud Run services deploy with their containers — see deploy-api target"

setup-gcp-api-keys:
	@echo "Create a Gemini API key at https://aistudio.google.com/apikey"
	@echo "Then run: make set-gemini-key KEY=<your-key>"

set-gemini-key:
	kubectl create secret generic gemini-api-key \
		--from-literal=key=$(KEY) \
		--namespace=grimoire \
		--dry-run=client -o yaml | kubeseal | kubectl apply -f -