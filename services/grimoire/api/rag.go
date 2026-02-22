package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"

	"cloud.google.com/go/firestore"
	"google.golang.org/api/iterator"
)

// --- Request / Response types ---

// RAGRequest is the body of POST /api/rag/query.
type RAGRequest struct {
	Query       string   `json:"query"`
	ContentType string   `json:"content_type"`
	Books       []string `json:"books"`
	Edition     string   `json:"edition"`
	CampaignID  string   `json:"campaign_id"`
}

// RAGResponse is returned from the RAG query endpoint.
type RAGResponse struct {
	Query           string           `json:"query"`
	Answer          string           `json:"answer"`
	Citations       []Citation       `json:"citations"`
	CampaignContext []CampaignContext `json:"campaign_context,omitempty"`
}

// Citation references a sourcebook chunk used in the answer.
type Citation struct {
	SourceBook  string  `json:"source_book"`
	Page        int     `json:"page"`
	Section     string  `json:"section"`
	ContentType string  `json:"content_type"`
	Relevance   float64 `json:"relevance,omitempty"`
	Text        string  `json:"text"`
}

// CampaignContext is a campaign entity included as extra context.
type CampaignContext struct {
	Type    string `json:"type"`
	Name    string `json:"name"`
	Summary string `json:"summary"`
}

// --- Route registration ---

func registerRAGRoutes(mux *http.ServeMux, fs *firestore.Client, gemini *GeminiClient) {
	mux.HandleFunc("POST /api/rag/query", handleRAGQuery(fs, gemini))
}

// --- System prompt ---

const ragSystemPrompt = `You are a D&D 5e rules assistant. Answer the question using ONLY the provided context.
Cite source book and page for every claim: (PHB p.96), (MM p.23).
If the context doesn't contain enough information, say so.
Be concise and precise.
Respond in JSON: {"answer": "...", "citations": [{"source_book": "PHB", "page": 96, "section": "...", "relevance": 0.94}]}`

// --- Handler ---

func handleRAGQuery(fs *firestore.Client, gemini *GeminiClient) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		var req RAGRequest
		if err := readJSON(r, &req); err != nil {
			httpError(w, http.StatusBadRequest, err.Error())
			return
		}
		if req.Query == "" {
			httpError(w, http.StatusBadRequest, "query is required")
			return
		}

		email := userEmail(r)

		// 1. Embed the query.
		embedding, err := gemini.Embed(ctx, req.Query)
		if err != nil {
			log.Printf("rag: embed error: %v", err)
			internalError(w, err)
			return
		}

		// 2. Vector search sourcebook_chunks.
		vq := fs.Collection("sourcebook_chunks").
			FindNearest("embedding", embedding, 5, firestore.DistanceMeasureCosine, nil)

		iter := vq.Documents(ctx)
		defer iter.Stop()

		// Determine if the user is the DM of the given campaign (for spoiler filtering).
		var isDM bool
		if req.CampaignID != "" {
			isDM = checkIsDM(ctx, fs, req.CampaignID, email)
		}

		var chunks []map[string]any
		for {
			doc, err := iter.Next()
			if err == iterator.Done {
				break
			}
			if err != nil {
				log.Printf("rag: vector search error: %v", err)
				internalError(w, err)
				return
			}
			data := docToMap(doc)

			// Post-filter: skip dm_only / spoiler chunks unless user is DM.
			if !isDM {
				audience, _ := data["audience"].(string)
				if audience == "dm_only" || audience == "spoiler" {
					continue
				}
			}

			// Post-filter by content_type if provided.
			if req.ContentType != "" {
				ct, _ := data["content_type"].(string)
				if ct != req.ContentType {
					continue
				}
			}

			// Post-filter by books if provided.
			if len(req.Books) > 0 {
				sb, _ := data["source_book"].(string)
				if !stringInSlice(sb, req.Books) {
					continue
				}
			}

			// Post-filter by edition if provided.
			if req.Edition != "" {
				ed, _ := data["edition"].(string)
				if ed != req.Edition {
					continue
				}
			}

			chunks = append(chunks, data)
		}

		// 3. Optionally gather campaign context for DM users.
		var campaignCtx []CampaignContext
		if req.CampaignID != "" && isDM {
			campaignCtx = gatherCampaignContext(ctx, fs, req.CampaignID, req.Query)
		}

		// 4. If no results, return a helpful message.
		if len(chunks) == 0 && len(campaignCtx) == 0 {
			writeJSON(w, http.StatusOK, RAGResponse{
				Query:     req.Query,
				Answer:    "No relevant information found in the available sourcebooks or campaign data.",
				Citations: []Citation{},
			})
			return
		}

		// 5. Assemble context string.
		contextStr := assembleContext(chunks, campaignCtx)

		// 6. Generate answer.
		userPrompt := fmt.Sprintf("Context:\n%s\n\nQuestion: %s", contextStr, req.Query)
		answer, err := gemini.Generate(ctx, ragSystemPrompt, userPrompt)
		if err != nil {
			log.Printf("rag: generate error: %v", err)
			internalError(w, err)
			return
		}

		// 7. Try to parse Gemini's structured JSON response.
		resp := RAGResponse{
			Query:           req.Query,
			CampaignContext: campaignCtx,
		}
		resp.Citations = buildCitationsFromChunks(chunks)

		var parsed struct {
			Answer    string `json:"answer"`
			Citations []struct {
				SourceBook string  `json:"source_book"`
				Page       int     `json:"page"`
				Section    string  `json:"section"`
				Relevance  float64 `json:"relevance"`
			} `json:"citations"`
		}

		// Strip markdown code fences if present.
		cleaned := stripCodeFences(answer)
		if err := json.Unmarshal([]byte(cleaned), &parsed); err == nil {
			resp.Answer = parsed.Answer
			if len(parsed.Citations) > 0 {
				resp.Citations = make([]Citation, len(parsed.Citations))
				for i, c := range parsed.Citations {
					resp.Citations[i] = Citation{
						SourceBook: c.SourceBook,
						Page:       c.Page,
						Section:    c.Section,
						Relevance:  c.Relevance,
					}
				}
			}
		} else {
			// Fallback: use raw text.
			resp.Answer = answer
		}

		writeJSON(w, http.StatusOK, resp)
	}
}

// --- Helpers ---

// checkIsDM returns true if email is the dm_user_id of the given campaign.
func checkIsDM(ctx context.Context, fs *firestore.Client, campaignID, email string) bool {
	doc, err := fs.Collection("campaigns").Doc(campaignID).Get(ctx)
	if err != nil {
		return false
	}
	dm, _ := doc.DataAt("dm_user_id")
	return dm == email
}

// gatherCampaignContext searches NPCs, locations, and factions subcollections
// for keyword matches against the query.
func gatherCampaignContext(ctx context.Context, fs *firestore.Client, campaignID, query string) []CampaignContext {
	var results []CampaignContext
	campaignRef := fs.Collection("campaigns").Doc(campaignID)
	keywords := strings.Fields(strings.ToLower(query))

	for _, sub := range []string{"npcs", "locations", "factions"} {
		iter := campaignRef.Collection(sub).Documents(ctx)
		docs, err := collectDocs(iter)
		if err != nil {
			continue
		}
		for _, data := range docs {
			name, _ := data["name"].(string)
			desc, _ := data["description"].(string)
			combined := strings.ToLower(name + " " + desc)

			for _, kw := range keywords {
				if len(kw) >= 3 && strings.Contains(combined, kw) {
					summary, _ := data["summary"].(string)
					if summary == "" {
						summary = truncate(desc, 200)
					}
					results = append(results, CampaignContext{
						Type:    sub,
						Name:    name,
						Summary: summary,
					})
					break
				}
			}
		}
	}
	return results
}

// assembleContext builds a prompt context string from chunks and campaign entities.
func assembleContext(chunks []map[string]any, campaignCtx []CampaignContext) string {
	var b strings.Builder

	for i, chunk := range chunks {
		sb, _ := chunk["source_book"].(string)
		page, _ := chunk["page"].(int64)
		section, _ := chunk["section"].(string)
		text, _ := chunk["text"].(string)
		fmt.Fprintf(&b, "[Source %d] %s p.%d — %s\n%s\n\n", i+1, sb, page, section, text)
	}

	if len(campaignCtx) > 0 {
		b.WriteString("Campaign context:\n")
		for _, c := range campaignCtx {
			fmt.Fprintf(&b, "- %s (%s): %s\n", c.Name, c.Type, c.Summary)
		}
	}

	return b.String()
}

// buildCitationsFromChunks creates a fallback citation list from the retrieved chunks.
func buildCitationsFromChunks(chunks []map[string]any) []Citation {
	citations := make([]Citation, 0, len(chunks))
	for _, chunk := range chunks {
		sb, _ := chunk["source_book"].(string)
		page, _ := chunk["page"].(int64)
		section, _ := chunk["section"].(string)
		ct, _ := chunk["content_type"].(string)
		text, _ := chunk["text"].(string)
		citations = append(citations, Citation{
			SourceBook:  sb,
			Page:        int(page),
			Section:     section,
			ContentType: ct,
			Text:        truncate(text, 200),
		})
	}
	return citations
}

// stringInSlice returns true if s is in the slice.
func stringInSlice(s string, slice []string) bool {
	for _, v := range slice {
		if v == s {
			return true
		}
	}
	return false
}

// truncate returns s truncated to maxLen with an ellipsis if needed.
func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}

// stripCodeFences removes markdown code fences (```json ... ```) from a string.
func stripCodeFences(s string) string {
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, "```") {
		// Remove opening fence (possibly with language tag).
		if idx := strings.Index(s, "\n"); idx != -1 {
			s = s[idx+1:]
		}
		// Remove closing fence.
		if idx := strings.LastIndex(s, "```"); idx != -1 {
			s = s[:idx]
		}
	}
	return strings.TrimSpace(s)
}
