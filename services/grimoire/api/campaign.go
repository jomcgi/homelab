package main

import (
	"net/http"

	"cloud.google.com/go/firestore"
	"google.golang.org/api/iterator"
)

func registerCampaignRoutes(mux *http.ServeMux, fs *firestore.Client) {
	mux.HandleFunc("GET /api/campaigns", listCampaigns(fs))
	mux.HandleFunc("POST /api/campaigns", createCampaign(fs))
	mux.HandleFunc("GET /api/campaigns/{id}", getCampaign(fs))
	mux.HandleFunc("PATCH /api/campaigns/{id}", updateCampaign(fs))
}

func listCampaigns(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		limit, _ := paginationParams(r)
		email := userEmail(r)
		iter := fs.Collection("campaigns").
			Where("dm_user_id", "==", email).
			OrderBy("created_at", firestore.Desc).
			Limit(limit).
			Documents(r.Context())
		docs, err := collectDocs(iter)
		if err != nil {
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docs)
	}
}

func createCampaign(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Name   string         `json:"name"`
			System string         `json:"system"`
			World  map[string]any `json:"world_state"`
		}
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if body.Name == "" {
			httpError(w, http.StatusBadRequest, "name is required")
			return
		}
		if body.System == "" {
			body.System = "dnd5e"
		}
		if body.World == nil {
			body.World = map[string]any{}
		}

		doc := fs.Collection("campaigns").NewDoc()
		data := map[string]any{
			"name":        body.Name,
			"system":      body.System,
			"dm_user_id":  userEmail(r),
			"world_state": body.World,
			"created_at":  nowTimestamp(),
		}
		if _, err := doc.Set(r.Context(), data); err != nil {
			internalError(w, err)
			return
		}
		data["id"] = doc.ID
		writeJSON(w, http.StatusCreated, data)
	}
}

func getCampaign(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		doc, err := fs.Collection("campaigns").Doc(id).Get(r.Context())
		if err != nil {
			if isNotFound(err) {
				httpError(w, http.StatusNotFound, "campaign not found")
				return
			}
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docToMap(doc))
	}
}

func updateCampaign(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")

		if err := verifyCampaignOwner(r.Context(), fs, id, userEmail(r)); err != nil {
			httpError(w, http.StatusForbidden, "forbidden")
			return
		}

		var body map[string]any
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}

		// Only allow updating specific fields.
		var updates []firestore.Update
		for _, field := range []string{"name", "system", "world_state"} {
			if v, ok := body[field]; ok {
				updates = append(updates, firestore.Update{Path: field, Value: v})
			}
		}
		if len(updates) == 0 {
			httpError(w, http.StatusBadRequest, "no valid fields to update")
			return
		}

		ref := fs.Collection("campaigns").Doc(id)
		if _, err := ref.Update(r.Context(), updates); err != nil {
			if isNotFound(err) {
				httpError(w, http.StatusNotFound, "campaign not found")
				return
			}
			internalError(w, err)
			return
		}

		doc, err := ref.Get(r.Context())
		if err != nil {
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docToMap(doc))
	}
}

// nextSessionNumber counts existing sessions and returns the next number.
func nextSessionNumber(r *http.Request, fs *firestore.Client, campaignID string) (int, error) {
	iter := fs.Collection("campaigns").Doc(campaignID).Collection("sessions").Documents(r.Context())
	defer iter.Stop()
	count := 0
	for {
		_, err := iter.Next()
		if err == iterator.Done {
			break
		}
		if err != nil {
			return 0, err
		}
		count++
	}
	return count + 1, nil
}
