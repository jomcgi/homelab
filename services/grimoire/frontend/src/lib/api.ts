import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import type { Classification, FeedEvent, Player, RollData } from "@/types";

const API_BASE = "/api";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

// --- Feed ---

export function useFeed(sessionId: string) {
  return useQuery({
    queryKey: ["feed", sessionId],
    queryFn: () => fetchJSON<FeedEvent[]>(`/sessions/${sessionId}/feed`),
    enabled: !!sessionId,
    refetchInterval: false,
  });
}

// --- Characters ---

export function useCharacters(campaignId: string) {
  return useQuery({
    queryKey: ["characters", campaignId],
    queryFn: () => fetchJSON<Player[]>(`/campaigns/${campaignId}/characters`),
    enabled: !!campaignId,
  });
}

// --- Dice ---

export function useRoll() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: {
      formula: string;
      context?: string;
      private?: boolean;
    }) => postJSON<RollData>("/roll", params),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feed"] });
    },
  });
}

// --- Feed Post ---

export function usePostFeedEvent(sessionId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (event: Partial<FeedEvent>) =>
      postJSON<FeedEvent>(`/sessions/${sessionId}/feed`, event),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feed", sessionId] });
    },
  });
}

// --- RAG ---

export function useRAGQuery() {
  return useMutation({
    mutationFn: (params: {
      query: string;
      content_type?: string;
      books?: string[];
    }) => postJSON("/rag/query", params),
  });
}

// --- Reclassify ---

export function useReclassify() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: {
      eventId: string;
      newClass: Classification;
    }) => {
      const res = await fetch(
        `${API_BASE}/feed/${encodeURIComponent(params.eventId)}/reclassify`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ new_classification: params.newClass }),
        },
      );
      if (!res.ok) throw new Error(`Request failed (${res.status})`);
      return res.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["feed"] });
    },
  });
}
