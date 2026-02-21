import { create } from "zustand";
import type { Classification, FeedEvent, Player } from "@/types";

// Placeholder data matching example-ui.jsx for visual fidelity
const MOCK_PLAYERS: Player[] = [
  {
    id: "kael",
    name: "Kael",
    class: "Fighter",
    level: 5,
    hp: 45,
    maxHp: 52,
    ac: 18,
    init: 17,
    conditions: ["Blessed"],
    color: "#dc2626",
  },
  {
    id: "lyra",
    name: "Lyra",
    class: "Wizard",
    level: 5,
    hp: 28,
    maxHp: 28,
    ac: 13,
    init: 15,
    conditions: [],
    color: "#2563eb",
  },
  {
    id: "theron",
    name: "Theron",
    class: "Cleric",
    level: 5,
    hp: 38,
    maxHp: 41,
    ac: 16,
    init: 12,
    conditions: [],
    color: "#16a34a",
  },
  {
    id: "vex",
    name: "Vex",
    class: "Rogue",
    level: 5,
    hp: 19,
    maxHp: 33,
    ac: 15,
    init: 22,
    conditions: ["Poisoned"],
    color: "#d97706",
  },
];

interface GrimoireState {
  // Role & navigation
  role: "dm" | "player";
  setRole: (role: "dm" | "player") => void;

  // Active player (for player view)
  currentPlayerId: string;
  setCurrentPlayerId: (id: string) => void;

  // Session
  sessionId: string;
  campaignId: string;

  // Filters
  activeFilters: Classification[];
  toggleFilter: (cls: Classification) => void;

  // Feed
  feed: FeedEvent[];
  addFeedEvent: (event: FeedEvent) => void;
  setFeed: (events: FeedEvent[]) => void;

  // Players
  players: Player[];
  setPlayers: (players: Player[]) => void;

  // Voice
  connected: boolean;
  setConnected: (c: boolean) => void;
  speakingIds: string[];
  setSpeaking: (id: string, speaking: boolean) => void;
}

export const useStore = create<GrimoireState>((set) => ({
  role: "dm",
  setRole: (role) => set({ role }),

  currentPlayerId: "vex",
  setCurrentPlayerId: (id) => set({ currentPlayerId: id }),

  sessionId: "session-1",
  campaignId: "campaign-1",

  activeFilters: [
    "ic_action",
    "ic_dialogue",
    "rules",
    "dm_narration",
    "dm_ruling",
    "table_talk",
  ],
  toggleFilter: (cls) =>
    set((s) => ({
      activeFilters: s.activeFilters.includes(cls)
        ? s.activeFilters.filter((f) => f !== cls)
        : [...s.activeFilters, cls],
    })),

  feed: [],
  addFeedEvent: (event) =>
    set((s) => {
      const feed = [...s.feed, event];
      return { feed: feed.length > 500 ? feed.slice(-500) : feed };
    }),
  setFeed: (events) => set({ feed: events }),

  players: MOCK_PLAYERS,
  setPlayers: (players) => set({ players }),

  connected: false,
  setConnected: (c) => set({ connected: c }),
  speakingIds: [],
  setSpeaking: (id, speaking) =>
    set((s) => ({
      speakingIds: speaking
        ? [...s.speakingIds.filter((x) => x !== id), id]
        : s.speakingIds.filter((x) => x !== id),
    })),
}));
