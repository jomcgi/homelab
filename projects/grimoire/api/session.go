package main

import (
	"context"
	"fmt"
	"net/http"

	"cloud.google.com/go/firestore"
)

func registerSessionRoutes(mux *http.ServeMux, fs *firestore.Client) {
	mux.HandleFunc("GET /api/campaigns/{id}/sessions", listSessions(fs))
	mux.HandleFunc("POST /api/campaigns/{id}/sessions", createSession(fs))
	mux.HandleFunc("PATCH /api/campaigns/{cid}/sessions/{sid}", updateSession(fs))
	mux.HandleFunc("POST /api/campaigns/{cid}/sessions/{sid}/start", transitionSession(fs, "active"))
	mux.HandleFunc("POST /api/campaigns/{cid}/sessions/{sid}/pause", transitionSession(fs, "paused"))
	mux.HandleFunc("POST /api/campaigns/{cid}/sessions/{sid}/resume", transitionSession(fs, "active"))
	mux.HandleFunc("POST /api/campaigns/{cid}/sessions/{sid}/end", transitionSession(fs, "completed"))
}

func listSessions(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		campaignID := r.PathValue("id")
		limit, _ := paginationParams(r)
		iter := fs.Collection("campaigns").Doc(campaignID).
			Collection("sessions").
			OrderBy("session_number", firestore.Desc).
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

func createSession(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		campaignID := r.PathValue("id")

		if err := verifyCampaignOwner(r.Context(), fs, campaignID, userEmail(r)); err != nil {
			httpError(w, http.StatusForbidden, "forbidden")
			return
		}

		num, err := nextSessionNumber(r, fs, campaignID)
		if err != nil {
			internalError(w, err)
			return
		}

		doc := fs.Collection("campaigns").Doc(campaignID).Collection("sessions").NewDoc()
		data := map[string]any{
			"campaign_id":    campaignID,
			"session_number": num,
			"status":         "planning",
			"started_at":     nil,
			"ended_at":       nil,
		}
		if _, err := doc.Set(r.Context(), data); err != nil {
			internalError(w, err)
			return
		}
		data["id"] = doc.ID
		writeJSON(w, http.StatusCreated, data)
	}
}

func updateSession(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		cid := r.PathValue("cid")
		sid := r.PathValue("sid")

		if err := verifyCampaignOwner(r.Context(), fs, cid, userEmail(r)); err != nil {
			httpError(w, http.StatusForbidden, "forbidden")
			return
		}

		var body map[string]any
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}

		var updates []firestore.Update
		for _, field := range []string{"session_number"} {
			if v, ok := body[field]; ok {
				updates = append(updates, firestore.Update{Path: field, Value: v})
			}
		}
		if len(updates) == 0 {
			httpError(w, http.StatusBadRequest, "no valid fields to update")
			return
		}

		ref := fs.Collection("campaigns").Doc(cid).Collection("sessions").Doc(sid)
		if _, err := ref.Update(r.Context(), updates); err != nil {
			if isNotFound(err) {
				httpError(w, http.StatusNotFound, "session not found")
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

// Valid session state transitions.
//
//	planning -> active -> paused -> active -> completed
//	                   -> completed
var validTransitions = map[string]map[string]bool{
	"planning": {"active": true},
	"active":   {"paused": true, "completed": true},
	"paused":   {"active": true, "completed": true},
}

// transitionSession moves a session to the target status, enforcing the state
// machine and the invariant that at most one session per campaign can be
// active or paused at a time. Uses a Firestore transaction for consistency.
func transitionSession(fs *firestore.Client, target string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		cid := r.PathValue("cid")
		sid := r.PathValue("sid")
		ctx := r.Context()

		if err := verifyCampaignOwner(ctx, fs, cid, userEmail(r)); err != nil {
			httpError(w, http.StatusForbidden, "forbidden")
			return
		}

		sessionsCol := fs.Collection("campaigns").Doc(cid).Collection("sessions")
		ref := sessionsCol.Doc(sid)

		err := fs.RunTransaction(ctx, func(ctx context.Context, tx *firestore.Transaction) error {
			doc, err := tx.Get(ref)
			if err != nil {
				if isNotFound(err) {
					return fmt.Errorf("session not found")
				}
				return err
			}

			current, _ := doc.DataAt("status")
			currentStr, _ := current.(string)

			allowed, ok := validTransitions[currentStr]
			if !ok || !allowed[target] {
				return fmt.Errorf("cannot transition from %q to %q", currentStr, target)
			}

			// Enforce at most one active/paused session per campaign.
			if target == "active" || target == "paused" {
				others := sessionsCol.Where("status", "in", []string{"active", "paused"})
				otherDocs, err := tx.Documents(others).GetAll()
				if err != nil {
					return err
				}
				for _, other := range otherDocs {
					if other.Ref.ID != sid {
						return fmt.Errorf("campaign already has an active/paused session: %s", other.Ref.ID)
					}
				}
			}

			updates := []firestore.Update{
				{Path: "status", Value: target},
			}
			if target == "active" && currentStr == "planning" {
				updates = append(updates, firestore.Update{Path: "started_at", Value: nowTimestamp()})
			}
			if target == "completed" {
				updates = append(updates, firestore.Update{Path: "ended_at", Value: nowTimestamp()})
			}

			return tx.Update(ref, updates)
		})
		if err != nil {
			code := http.StatusConflict
			if err.Error() == "session not found" {
				code = http.StatusNotFound
			}
			httpError(w, code, err.Error())
			return
		}

		doc, err := ref.Get(ctx)
		if err != nil {
			internalError(w, err)
			return
		}
		writeJSON(w, http.StatusOK, docToMap(doc))
	}
}
