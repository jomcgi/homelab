package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
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
	data, err := json.Marshal(v)
	if err != nil {
		slog.Error("json marshal error", "error", err)
		http.Error(w, "internal server error", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	w.Write(data)
}

func internalError(w http.ResponseWriter, err error) {
	slog.Error("internal error", "error", err)
	httpError(w, http.StatusInternalServerError, "internal server error")
}

// verifyCampaignOwner checks that the authenticated user is the DM of the campaign.
func verifyCampaignOwner(ctx context.Context, fs *firestore.Client, campaignID, email string) error {
	doc, err := fs.Collection("campaigns").Doc(campaignID).Get(ctx)
	if err != nil {
		return fmt.Errorf("campaign not found")
	}
	dm, _ := doc.DataAt("dm_user_id")
	if dm != email {
		return fmt.Errorf("forbidden")
	}
	return nil
}

// paginationParams extracts limit and cursor from query parameters.
func paginationParams(r *http.Request) (int, string) {
	limit := 50
	if l := r.URL.Query().Get("limit"); l != "" {
		if n, err := strconv.Atoi(l); err == nil && n > 0 && n <= 200 {
			limit = n
		}
	}
	cursor := r.URL.Query().Get("cursor")
	return limit, cursor
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
