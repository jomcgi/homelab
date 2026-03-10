package main

import (
	"fmt"
	"math/rand/v2"
	"net/http"
	"regexp"
	"strconv"
	"strings"

	"cloud.google.com/go/firestore"
)

func registerDiceRoutes(mux *http.ServeMux, fs *firestore.Client) {
	mux.HandleFunc("POST /api/roll", rollDice(fs))
	mux.HandleFunc("GET /api/sessions/{sid}/rolls", listRolls(fs))
}

// rollDice parses a dice formula (e.g. "2d6+3", "1d20adv", "4d6kh3"),
// executes the roll, and persists it as a feed event.
func rollDice(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Formula    string `json:"formula"`
			Context    string `json:"context"`
			Private    bool   `json:"private"`
			SessionID  string `json:"session_id"`
			CampaignID string `json:"campaign_id"`
		}
		if err := readJSON(r, &body); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if body.Formula == "" {
			httpError(w, http.StatusBadRequest, "formula is required")
			return
		}

		result, detail, err := parseAndRoll(body.Formula)
		if err != nil {
			httpError(w, http.StatusBadRequest, "invalid formula: "+err.Error())
			return
		}

		roll := map[string]any{
			"formula": body.Formula,
			"result":  result,
			"detail":  detail,
			"type":    body.Context,
		}

		resp := map[string]any{
			"formula": body.Formula,
			"result":  result,
			"detail":  detail,
			"context": body.Context,
		}

		// Persist as a feed event if session is provided.
		if body.SessionID != "" && body.CampaignID != "" {
			email := userEmail(r)
			var privateTo any
			if body.Private {
				privateTo = email
			}
			feedDoc := fs.Collection("campaigns").Doc(body.CampaignID).
				Collection("sessions").Doc(body.SessionID).
				Collection("feed").NewDoc()
			feedData := map[string]any{
				"session_id":     body.SessionID,
				"speaker_id":     email,
				"source":         "roll",
				"classification": "ic_action",
				"confidence":     1.0,
				"text":           fmt.Sprintf("%s rolled %s: %d", body.Context, body.Formula, result),
				"roll":           roll,
				"private_to":     privateTo,
				"rag_triggered":  false,
				"created_at":     nowTimestamp(),
			}
			if _, err := feedDoc.Set(r.Context(), feedData); err != nil {
				internalError(w, err)
				return
			}
			resp["feed_event_id"] = feedDoc.ID
		}

		writeJSON(w, http.StatusOK, resp)
	}
}

func listRolls(fs *firestore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		sessionID := r.PathValue("sid")
		limit, _ := paginationParams(r)

		iter := fs.CollectionGroup("feed").
			Where("session_id", "==", sessionID).
			Where("source", "==", "roll").
			OrderBy("created_at", firestore.Desc).
			Limit(limit).
			Documents(r.Context())
		docs, err := collectDocs(iter)
		if err != nil {
			internalError(w, err)
			return
		}

		// Filter out private rolls not addressed to the requesting user.
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

// --- Dice parser ---
// Supports: NdS, NdS+M, NdS-M, NdSadv, NdSdis, NdSkhN (keep highest N)

var dicePattern = regexp.MustCompile(`^(\d+)d(\d+)(kh(\d+)|adv|dis)?([+-]\d+)?$`)

func parseAndRoll(formula string) (int, string, error) {
	formula = strings.TrimSpace(strings.ToLower(formula))
	m := dicePattern.FindStringSubmatch(formula)
	if m == nil {
		return 0, "", fmt.Errorf("unrecognized dice formula: %s", formula)
	}

	count, _ := strconv.Atoi(m[1])
	sides, _ := strconv.Atoi(m[2])
	modifier := m[3]    // "adv", "dis", or "khN"
	keepHighN := m[4]   // the N from "khN"
	modifierVal := m[5] // "+3" or "-2"

	if count < 1 || count > 100 || sides < 1 || sides > 1000 {
		return 0, "", fmt.Errorf("dice out of range")
	}

	rolls := make([]int, count)
	for i := range rolls {
		rolls[i] = rand.IntN(sides) + 1
	}

	var total int
	var detail string

	switch {
	case modifier == "adv" && count == 1:
		// Roll twice, take higher.
		second := rand.IntN(sides) + 1
		if second > rolls[0] {
			total = second
			detail = fmt.Sprintf("[%d, %d] -> %d", rolls[0], second, second)
		} else {
			total = rolls[0]
			detail = fmt.Sprintf("[%d, %d] -> %d", rolls[0], second, rolls[0])
		}
	case modifier == "dis" && count == 1:
		// Roll twice, take lower.
		second := rand.IntN(sides) + 1
		if second < rolls[0] {
			total = second
			detail = fmt.Sprintf("[%d, %d] -> %d", rolls[0], second, second)
		} else {
			total = rolls[0]
			detail = fmt.Sprintf("[%d, %d] -> %d", rolls[0], second, rolls[0])
		}
	case keepHighN != "":
		// Keep highest N dice.
		keepN, _ := strconv.Atoi(keepHighN)
		if keepN > count {
			keepN = count
		}
		sorted := sortDescCopy(rolls)
		for i := 0; i < keepN; i++ {
			total += sorted[i]
		}
		detail = fmt.Sprintf("%v kh%d -> %d", rolls, keepN, total)
	default:
		for _, v := range rolls {
			total += v
		}
		detail = fmt.Sprintf("%v -> %d", rolls, total)
	}

	// Apply flat modifier.
	if modifierVal != "" {
		mod, _ := strconv.Atoi(modifierVal)
		total += mod
		detail += fmt.Sprintf(" %s%d = %d", signStr(mod), abs(mod), total)
	}

	return total, detail, nil
}

func sortDescCopy(s []int) []int {
	c := make([]int, len(s))
	copy(c, s)
	for i := range c {
		for j := i + 1; j < len(c); j++ {
			if c[j] > c[i] {
				c[i], c[j] = c[j], c[i]
			}
		}
	}
	return c
}

func signStr(n int) string {
	if n >= 0 {
		return "+"
	}
	return "-"
}

func abs(n int) int {
	if n < 0 {
		return -n
	}
	return n
}
