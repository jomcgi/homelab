package main

import (
	"net/http"

	"cloud.google.com/go/firestore"
)

func registerCharacterRoutes(mux *http.ServeMux, fs *firestore.Client) {
	mux.HandleFunc("GET /api/campaigns/{id}/characters", listCharacters(fs))
	mux.HandleFunc("POST /api/campaigns/{id}/characters", createCharacter(fs))
	mux.HandleFunc("GET /api/characters/{id}", getCharacter(fs))
	mux.HandleFunc("PATCH /api/characters/{id}", updateCharacter(fs))
	mux.HandleFunc("GET /api/characters/{id}/lore", listLore(fs))
	mux.HandleFunc("POST /api/characters/{id}/lore", createLore(fs))
}

func listCharacters(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		campaignID := r.PathValue("id")
		limit, _ := paginationParams(r)
		iter := fs.Collection("campaigns").Doc(campaignID).
			Collection("characters").
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

func createCharacter(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		campaignID := r.PathValue("id")

		var body struct {
			Name       string         `json:"name"`
			Race       string         `json:"race"`
			Class      string         `json:"class"`
			Level      int            `json:"level"`
			HP         int            `json:"hp"`
			MaxHP      int            `json:"max_hp"`
			AC         int            `json:"ac"`
			Abilities  map[string]int `json:"abilities"`
			Conditions []string       `json:"conditions"`
			SpellSlots []int          `json:"spell_slots"`
			Color      string         `json:"color"`
		}
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if body.Name == "" {
			httpError(w, http.StatusBadRequest, "name is required")
			return
		}
		if body.Level == 0 {
			body.Level = 1
		}
		if body.Conditions == nil {
			body.Conditions = []string{}
		}
		if body.SpellSlots == nil {
			body.SpellSlots = []int{}
		}

		doc := fs.Collection("campaigns").Doc(campaignID).Collection("characters").NewDoc()
		data := map[string]any{
			"campaign_id": campaignID,
			"user_id":     userEmail(r),
			"name":        body.Name,
			"race":        body.Race,
			"class":       body.Class,
			"level":       body.Level,
			"hp":          body.HP,
			"max_hp":      body.MaxHP,
			"ac":          body.AC,
			"abilities":   body.Abilities,
			"conditions":  body.Conditions,
			"spell_slots": body.SpellSlots,
			"color":       body.Color,
		}
		if _, err := doc.Set(r.Context(), data); err != nil {
			internalError(w, err)
			return
		}
		data["id"] = doc.ID
		writeJSON(w, http.StatusCreated, data)
	}
}

// getCharacter looks up a character by ID. Since characters are stored in
// subcollections under campaigns, we use a collection group query.
func getCharacter(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		iter := fs.CollectionGroup("characters").Where("__name__", "==",
			fs.Collection("campaigns").Doc("_").Collection("characters").Doc(id).Path,
		).Documents(r.Context())
		// Collection group query by document ID is tricky. Instead, the client
		// should include the campaign_id, or we search all campaigns.
		// For simplicity, iterate the collection group and match by doc ID.
		iter.Stop()

		// Simpler approach: iterate all campaign character subcollections.
		// In practice, the frontend knows the campaign ID and uses the
		// /campaigns/:id/characters endpoint. This top-level endpoint is
		// a convenience that scans using a collection group query.
		groupIter := fs.CollectionGroup("characters").Documents(r.Context())
		defer groupIter.Stop()
		for {
			doc, err := groupIter.Next()
			if err != nil {
				break
			}
			if doc.Ref.ID == id {
				writeJSON(w, http.StatusOK, docToMap(doc))
				return
			}
		}
		httpError(w, http.StatusNotFound, "character not found")
	}
}

func updateCharacter(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		var body map[string]any
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}

		allowedFields := map[string]bool{
			"name": true, "race": true, "class": true, "level": true,
			"hp": true, "max_hp": true, "ac": true, "abilities": true,
			"conditions": true, "spell_slots": true, "color": true,
		}

		var updates []firestore.Update
		for field, val := range body {
			if allowedFields[field] {
				updates = append(updates, firestore.Update{Path: field, Value: val})
			}
		}
		if len(updates) == 0 {
			httpError(w, http.StatusBadRequest, "no valid fields to update")
			return
		}

		// Find the character via collection group and update it.
		groupIter := fs.CollectionGroup("characters").Documents(r.Context())
		defer groupIter.Stop()
		for {
			doc, err := groupIter.Next()
			if err != nil {
				break
			}
			if doc.Ref.ID == id {
				if _, err := doc.Ref.Update(r.Context(), updates); err != nil {
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
		httpError(w, http.StatusNotFound, "character not found")
	}
}

func listLore(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		charID := r.PathValue("id")

		// Find the character's parent path via collection group.
		groupIter := fs.CollectionGroup("characters").Documents(r.Context())
		defer groupIter.Stop()
		for {
			doc, err := groupIter.Next()
			if err != nil {
				break
			}
			if doc.Ref.ID == charID {
				iter := doc.Ref.Collection("lore").
					OrderBy("revealed_at", firestore.Desc).
					Documents(r.Context())
				lore, err := collectDocs(iter)
				if err != nil {
					internalError(w, err)
					return
				}
				writeJSON(w, http.StatusOK, lore)
				return
			}
		}
		httpError(w, http.StatusNotFound, "character not found")
	}
}

func createLore(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		charID := r.PathValue("id")

		var body struct {
			Fact   string `json:"fact"`
			Source string `json:"source"`
		}
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if body.Fact == "" {
			httpError(w, http.StatusBadRequest, "fact is required")
			return
		}

		// Find character to get campaign_id.
		groupIter := fs.CollectionGroup("characters").Documents(r.Context())
		defer groupIter.Stop()
		for {
			doc, err := groupIter.Next()
			if err != nil {
				break
			}
			if doc.Ref.ID == charID {
				campaignID, _ := doc.DataAt("campaign_id")

				loreDoc := doc.Ref.Collection("lore").NewDoc()
				data := map[string]any{
					"character_id": charID,
					"campaign_id":  campaignID,
					"fact":         body.Fact,
					"source":       body.Source,
					"is_new":       true,
					"revealed_at":  nowTimestamp(),
				}
				if _, err := loreDoc.Set(r.Context(), data); err != nil {
					internalError(w, err)
					return
				}
				data["id"] = loreDoc.ID
				writeJSON(w, http.StatusCreated, data)
				return
			}
		}
		httpError(w, http.StatusNotFound, "character not found")
	}
}
