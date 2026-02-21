package main

import (
	"context"
	"fmt"
	"net/http"

	"cloud.google.com/go/firestore"
)

func registerEncounterRoutes(mux *http.ServeMux, fs *firestore.Client) {
	mux.HandleFunc("POST /api/sessions/{sid}/encounters", createEncounter(fs))
	mux.HandleFunc("PATCH /api/encounters/{id}", updateEncounter(fs))
	mux.HandleFunc("POST /api/encounters/{id}/next-turn", nextTurn(fs))
	mux.HandleFunc("POST /api/encounters/{id}/end-round", endRound(fs))
	mux.HandleFunc("PATCH /api/encounters/{eid}/monsters/{mid}", updateMonster(fs))
}

// encounterRef finds an encounter document by ID using a collection group query.
// Encounters live under campaigns/{cid}/sessions/{sid}/encounters/{eid}.
func encounterRef(ctx context.Context, fs *firestore.Client, encounterID string) (*firestore.DocumentRef, *firestore.DocumentSnapshot, error) {
	iter := fs.CollectionGroup("encounters").Documents(ctx)
	defer iter.Stop()
	for {
		doc, err := iter.Next()
		if err != nil {
			break
		}
		if doc.Ref.ID == encounterID {
			return doc.Ref, doc, nil
		}
	}
	return nil, nil, fmt.Errorf("encounter not found")
}

func createEncounter(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sessionID := r.PathValue("sid")

		var body struct {
			Name            string `json:"name"`
			Terrain         string `json:"terrain"`
			CampaignID      string `json:"campaign_id"`
			InitiativeOrder []struct {
				ID         string `json:"id"`
				Name       string `json:"name"`
				Initiative int    `json:"initiative"`
			} `json:"initiative_order"`
			Monsters []struct {
				Name       string   `json:"name"`
				HP         int      `json:"hp"`
				MaxHP      int      `json:"max_hp"`
				AC         int      `json:"ac"`
				Initiative int      `json:"initiative"`
				CR         string   `json:"cr"`
				Conditions []string `json:"conditions"`
				SourceRef  string   `json:"source_ref"`
			} `json:"monsters"`
		}
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if body.Name == "" {
			httpError(w, http.StatusBadRequest, "name is required")
			return
		}
		if body.CampaignID == "" {
			httpError(w, http.StatusBadRequest, "campaign_id is required")
			return
		}

		encountersCol := fs.Collection("campaigns").Doc(body.CampaignID).
			Collection("sessions").Doc(sessionID).
			Collection("encounters")

		if err := verifyCampaignOwner(r.Context(), fs, body.CampaignID, userEmail(r)); err != nil {
			httpError(w, http.StatusForbidden, "forbidden")
			return
		}

		doc := encountersCol.NewDoc()
		data := map[string]any{
			"session_id":       sessionID,
			"name":             body.Name,
			"status":           "planned",
			"round":            0,
			"current_turn_id":  "",
			"initiative_order": body.InitiativeOrder,
			"terrain":          body.Terrain,
		}

		// Create encounter + monsters atomically using a batch write.
		batch := fs.Batch()
		batch.Set(doc, data)
		for _, m := range body.Monsters {
			conditions := m.Conditions
			if conditions == nil {
				conditions = []string{}
			}
			monsterDoc := doc.Collection("monsters").NewDoc()
			mData := map[string]any{
				"encounter_id": doc.ID,
				"name":         m.Name,
				"hp":           m.HP,
				"max_hp":       m.MaxHP,
				"ac":           m.AC,
				"initiative":   m.Initiative,
				"cr":           m.CR,
				"conditions":   conditions,
				"source_ref":   m.SourceRef,
			}
			batch.Set(monsterDoc, mData)
		}
		if _, err := batch.Commit(r.Context()); err != nil {
			internalError(w, err)
			return
		}

		data["id"] = doc.ID
		writeJSON(w, http.StatusCreated, data)
	}
}

func updateEncounter(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		ctx := r.Context()

		ref, _, err := encounterRef(ctx, fs, id)
		if err != nil {
			httpError(w, http.StatusNotFound, err.Error())
			return
		}

		var body map[string]any
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}

		allowedFields := map[string]bool{
			"name": true, "terrain": true, "initiative_order": true,
			"status": true, "round": true, "current_turn_id": true,
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

		// If transitioning status, use a transaction to enforce the state machine.
		if newStatus, ok := body["status"].(string); ok {
			err := fs.RunTransaction(ctx, func(ctx context.Context, tx *firestore.Transaction) error {
				doc, err := tx.Get(ref)
				if err != nil {
					return err
				}
				current, _ := doc.DataAt("status")
				currentStr, _ := current.(string)
				if !validEncounterTransition(currentStr, newStatus) {
					return fmt.Errorf("cannot transition encounter from %q to %q", currentStr, newStatus)
				}
				if newStatus == "active" {
					updates = append(updates, firestore.Update{Path: "round", Value: 1})
				}
				return tx.Update(ref, updates)
			})
			if err != nil {
				httpError(w, http.StatusConflict, err.Error())
				return
			}
		} else {
			if _, err := ref.Update(ctx, updates); err != nil {
				internalError(w, err)
				return
			}
		}

		doc, err := ref.Get(ctx)
		if err != nil {
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docToMap(doc))
	}
}

var validEncounterTransitions = map[string]map[string]bool{
	"planned": {"active": true},
	"active":  {"completed": true},
}

func validEncounterTransition(from, to string) bool {
	allowed, ok := validEncounterTransitions[from]
	return ok && allowed[to]
}

// nextTurn advances the current_turn_id to the next entry in initiative_order.
func nextTurn(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		ctx := r.Context()

		ref, _, err := encounterRef(ctx, fs, id)
		if err != nil {
			httpError(w, http.StatusNotFound, err.Error())
			return
		}

		err = fs.RunTransaction(ctx, func(ctx context.Context, tx *firestore.Transaction) error {
			doc, err := tx.Get(ref)
			if err != nil {
				return err
			}

			st, _ := doc.DataAt("status")
			if st != "active" {
				return fmt.Errorf("encounter is not active")
			}

			order, _ := doc.DataAt("initiative_order")
			orderSlice, ok := order.([]any)
			if !ok || len(orderSlice) == 0 {
				return fmt.Errorf("initiative_order is empty")
			}

			currentTurn, _ := doc.DataAt("current_turn_id")
			currentTurnStr, _ := currentTurn.(string)

			nextIdx := 0
			for i, entry := range orderSlice {
				if m, ok := entry.(map[string]any); ok {
					if entryID, _ := m["id"].(string); entryID == currentTurnStr {
						nextIdx = (i + 1) % len(orderSlice)
						break
					}
				}
			}

			var nextID string
			if m, ok := orderSlice[nextIdx].(map[string]any); ok {
				nextID, _ = m["id"].(string)
			}

			return tx.Update(ref, []firestore.Update{
				{Path: "current_turn_id", Value: nextID},
			})
		})
		if err != nil {
			httpError(w, http.StatusConflict, err.Error())
			return
		}

		updated, err := ref.Get(ctx)
		if err != nil {
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docToMap(updated))
	}
}

// endRound increments the round counter and sets the turn to the first combatant.
func endRound(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.PathValue("id")
		ctx := r.Context()

		ref, _, err := encounterRef(ctx, fs, id)
		if err != nil {
			httpError(w, http.StatusNotFound, err.Error())
			return
		}

		err = fs.RunTransaction(ctx, func(ctx context.Context, tx *firestore.Transaction) error {
			doc, err := tx.Get(ref)
			if err != nil {
				return err
			}

			st, _ := doc.DataAt("status")
			if st != "active" {
				return fmt.Errorf("encounter is not active")
			}

			round, _ := doc.DataAt("round")
			roundNum, _ := round.(int64)

			order, _ := doc.DataAt("initiative_order")
			orderSlice, _ := order.([]any)
			var firstID string
			if len(orderSlice) > 0 {
				if m, ok := orderSlice[0].(map[string]any); ok {
					firstID, _ = m["id"].(string)
				}
			}

			return tx.Update(ref, []firestore.Update{
				{Path: "round", Value: roundNum + 1},
				{Path: "current_turn_id", Value: firstID},
			})
		})
		if err != nil {
			httpError(w, http.StatusConflict, err.Error())
			return
		}

		updated, err := ref.Get(ctx)
		if err != nil {
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docToMap(updated))
	}
}

// updateMonster patches a monster within an encounter.
func updateMonster(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		eid := r.PathValue("eid")
		mid := r.PathValue("mid")
		ctx := r.Context()

		encRef, _, err := encounterRef(ctx, fs, eid)
		if err != nil {
			httpError(w, http.StatusNotFound, "encounter not found")
			return
		}

		var body map[string]any
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}

		allowedFields := map[string]bool{
			"hp": true, "conditions": true, "initiative": true, "name": true,
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

		monsterRef := encRef.Collection("monsters").Doc(mid)
		if _, err := monsterRef.Update(ctx, updates); err != nil {
			if isNotFound(err) {
				httpError(w, http.StatusNotFound, "monster not found")
				return
			}
			internalError(w, err)
			return
		}

		doc, err := monsterRef.Get(ctx)
		if err != nil {
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docToMap(doc))
	}
}
