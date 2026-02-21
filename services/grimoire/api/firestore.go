package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"cloud.google.com/go/firestore"
	"google.golang.org/api/iterator"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func newFirestoreClient(ctx context.Context, projectID, database string) (*firestore.Client, error) {
	return firestore.NewClientWithDatabase(ctx, projectID, database)
}

// --- JSON helpers ---

func writeJSON(w http.ResponseWriter, code int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	json.NewEncoder(w).Encode(v)
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 1<<20)) // 1 MB limit
	if err != nil {
		return fmt.Errorf("reading body: %w", err)
	}
	return json.Unmarshal(body, v)
}

func httpError(w http.ResponseWriter, code int, msg string) {
	writeJSON(w, code, map[string]string{"error": msg})
}

// --- Firestore helpers ---

// docToMap converts a Firestore DocumentSnapshot to a map, injecting the doc ID.
func docToMap(doc *firestore.DocumentSnapshot) map[string]any {
	data := doc.Data()
	data["id"] = doc.Ref.ID
	return data
}

// collectDocs iterates a Firestore query and returns all documents as maps.
func collectDocs(iter *firestore.DocumentIterator) ([]map[string]any, error) {
	defer iter.Stop()
	var results []map[string]any
	for {
		doc, err := iter.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return nil, err
		}
		results = append(results, docToMap(doc))
	}
	if results == nil {
		results = []map[string]any{}
	}
	return results, nil
}

// isNotFound returns true if the error is a Firestore not-found error.
func isNotFound(err error) bool {
	return status.Code(err) == codes.NotFound
}

// nowTimestamp returns the current time as a Firestore-compatible value.
func nowTimestamp() time.Time {
	return time.Now().UTC()
}
