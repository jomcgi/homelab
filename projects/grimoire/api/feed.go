package main

import (
	"net/http"

	"cloud.google.com/go/firestore"
)

func registerFeedRoutes(mux *http.ServeMux, fs *firestore.Client) {
	mux.HandleFunc("GET /api/sessions/{sid}/feed", listFeed(fs))
	mux.HandleFunc("POST /api/sessions/{sid}/feed", createFeedEvent(fs))
	mux.HandleFunc("PATCH /api/feed/{id}/reclassify", reclassifyFeedEvent(fs))
}

func listFeed(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sessionID := r.PathValue("sid")
		limit, _ := paginationParams(r)

		query := fs.CollectionGroup("feed").
			Where("session_id", "==", sessionID).
			OrderBy("created_at", firestore.Asc).
			Limit(limit)

		// Optional filters from query params.
		if classification := r.URL.Query().Get("classification"); classification != "" {
			query = query.Where("classification", "==", classification)
		}
		if speaker := r.URL.Query().Get("speaker"); speaker != "" {
			query = query.Where("speaker_id", "==", speaker)
		}

		iter := query.Documents(r.Context())
		docs, err := collectDocs(iter)
		if err != nil {
			internalError(w, err)
			return
		}

		// Filter out private events not addressed to the requesting user.
		email := userEmail(r)
		filtered := make([]map[string]any, 0, len(docs))
		for _, doc := range docs {
			privateTo, _ := doc["private_to"].(string)
			speakerID, _ := doc["speaker_id"].(string)
			if privateTo == "" || privateTo == email || speakerID == email {
				filtered = append(filtered, doc)
			}
		}

		writeJSON(w, http.StatusOK, filtered)
	}
}

func createFeedEvent(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sessionID := r.PathValue("sid")

		var body struct {
			Text           string  `json:"text"`
			Source         string  `json:"source"`
			Classification string  `json:"classification"`
			Confidence     float64 `json:"confidence"`
			PrivateTo      string  `json:"private_to"`
			CampaignID     string  `json:"campaign_id"`
		}
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if body.Text == "" {
			httpError(w, http.StatusBadRequest, "text is required")
			return
		}
		if body.CampaignID == "" {
			httpError(w, http.StatusBadRequest, "campaign_id is required")
			return
		}
		if body.Source == "" {
			body.Source = "typed"
		}
		if body.Confidence == 0 {
			body.Confidence = 1.0
		}

		var privateTo any
		if body.PrivateTo != "" {
			privateTo = body.PrivateTo
		}

		doc := fs.Collection("campaigns").Doc(body.CampaignID).
			Collection("sessions").Doc(sessionID).
			Collection("feed").NewDoc()
		data := map[string]any{
			"session_id":     sessionID,
			"speaker_id":     userEmail(r),
			"source":         body.Source,
			"classification": body.Classification,
			"confidence":     body.Confidence,
			"text":           body.Text,
			"roll":           nil,
			"private_to":     privateTo,
			"rag_triggered":  false,
			"created_at":     nowTimestamp(),
		}
		if _, err := doc.Set(r.Context(), data); err != nil {
			internalError(w, err)
			return
		}
		data["id"] = doc.ID
		writeJSON(w, http.StatusCreated, data)
	}
}

func reclassifyFeedEvent(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")

		var body struct {
			NewClassification string `json:"new_classification"`
		}
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}

		validClassifications := map[string]bool{
			"ic_action": true, "ic_dialogue": true, "rules_question": true,
			"dm_narration": true, "dm_ruling": true, "table_talk": true,
		}
		if !validClassifications[body.NewClassification] {
			httpError(w, http.StatusBadRequest, "invalid classification: "+body.NewClassification)
			return
		}

		// Find the feed event via collection group query.
		iter := fs.CollectionGroup("feed").Documents(r.Context())
		defer iter.Stop()
		for {
			doc, err := iter.Next()
			if err != nil {
				break
			}
			if doc.Ref.ID == id {
				if _, err := doc.Ref.Update(r.Context(), []firestore.Update{
					{Path: "classification", Value: body.NewClassification},
					{Path: "confidence", Value: 1.0},
				}); err != nil {
					internalError(w, err)
					return
				}
				updated, err := doc.Ref.Get(r.Context())
				if err != nil {
					internalError(w, err)
					return
				}
				writeJSON(w, http.StatusOK, docToMap(updated))
				return
			}
		}
		httpError(w, http.StatusNotFound, "feed event not found")
	}
}
