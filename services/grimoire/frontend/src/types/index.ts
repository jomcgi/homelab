// --- Classification ---

export type Classification =
  | "ic_action"
  | "ic_dialogue"
  | "rules"
  | "dm_narration"
  | "dm_ruling"
  | "table_talk";

export interface ClassificationMeta {
  label: string;
  color: string;
  bg: string;
  icon: string;
}

// --- Feed ---

export interface RollData {
  formula: string;
  result: number;
  type: string;
}

export interface FeedEvent {
  id: string;
  who: string;
  time: string;
  source: "voice" | "typed" | "roll" | "system";
  cls?: Classification | "private";
  text?: string;
  roll?: RollData;
  conf?: number;
  rag?: boolean;
  private_to?: string;
}

// --- Characters ---

export interface Player {
  id: string;
  name: string;
  class: string;
  level: number;
  hp: number;
  maxHp: number;
  ac: number;
  init: number;
  conditions: string[];
  color: string;
}

export interface AbilityScore {
  name: string;
  value?: number;
  modifier: number;
}

// --- Monsters ---

export interface Monster {
  id?: string;
  name: string;
  hp: number;
  maxHp: number;
  ac: number;
  init: number;
  cr: string;
  conditions: string[];
}

// --- Initiative ---

export type InitiativeEntry =
  | (Player & { type: "player" })
  | (Monster & { type: "monster" });

// --- Encounters ---

export interface PlannedEncounter {
  name: string;
  monsters: string;
  diff: "Easy" | "Medium" | "Hard" | "Deadly";
  notes: string;
}

// --- Sessions ---

export interface SessionSummary {
  n: number;
  date: string;
  text: string;
}

// --- RAG ---

export interface RAGChunk {
  source: string;
  title: string;
  text: string;
  rel: number;
  auto?: boolean;
  pinned?: boolean;
}

// --- Lore ---

export interface LoreEntry {
  fact: string;
  src: string;
  isNew?: boolean;
}

// --- Inventory ---

export interface InventoryItem {
  name: string;
  detail: string;
  equipped: boolean;
}

// --- Quick Roll ---

export interface QuickRoll {
  label: string;
  formula: string;
  sub: string;
}

// --- Journal ---

export interface JournalEntry {
  n: number;
  date: string;
  text: string;
}

// --- World State ---

export interface WorldStateEntry {
  key: string;
  value: string;
}

// --- WebSocket Events ---

export type WSEvent =
  | { type: "audio_chunk"; data: ArrayBuffer }
  | { type: "voice_status"; speaker_id: string; speaking: boolean }
  | { type: "transcript"; event: FeedEvent }
  | { type: "feed_event"; event: FeedEvent }
  | { type: "roll_result"; roll: RollData; player?: string; character?: string }
  | { type: "encounter_update"; encounter: unknown }
  | { type: "dm_correction"; event_id: string; new_classification: string }
  | { type: "presence"; player_id: string; status: "online" | "offline" };
