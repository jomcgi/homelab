import type {
  FeedEvent,
  Monster,
  RAGChunk,
  PlannedEncounter,
  SessionSummary,
  WorldStateEntry,
  LoreEntry,
  InventoryItem,
  QuickRoll,
  JournalEntry,
  AbilityScore,
} from "@/types";

export const MOCK_FEED: FeedEvent[] = [
  {
    id: "1",
    who: "DM",
    time: "19:42",
    source: "voice",
    cls: "dm_narration",
    text: "As you push through the undergrowth, the forest goes quiet. Too quiet. The birds have stopped. You can smell something musky \u2014 like wet feathers and blood.",
    conf: 0.96,
  },
  {
    id: "2",
    who: "Vex",
    time: "19:42",
    source: "voice",
    cls: "ic_action",
    text: "I stop and hold up a fist. Everybody freeze. I want to look around \u2014 Perception check.",
    conf: 0.94,
  },
  {
    id: "3",
    who: "Vex",
    time: "19:42",
    source: "roll",
    roll: { formula: "1d20+3", result: 18, type: "Perception" },
  },
  {
    id: "4",
    who: "DM",
    time: "19:42",
    source: "voice",
    cls: "dm_narration",
    text: "You spot movement in the canopy \u2014 a massive shape on a thick branch. Below, three small figures behind a fallen log. Goblins. And that shape... that's an owlbear.",
    conf: 0.97,
  },
  {
    id: "5",
    who: "Lyra",
    time: "19:43",
    source: "voice",
    cls: "rules",
    text: "Wait \u2014 can I cast Bless before combat? If Vex spotted them, are we surprised or do we get a round?",
    conf: 0.91,
    rag: true,
  },
  {
    id: "6",
    who: "DM",
    time: "19:43",
    source: "voice",
    cls: "dm_ruling",
    text: "Good question. Vex spotted them, so the party is not surprised. But we're rolling initiative \u2014 Lyra, you can Bless on your first turn if you beat them.",
    conf: 0.93,
  },
  {
    id: "7",
    who: "Kael",
    time: "19:43",
    source: "voice",
    cls: "table_talk",
    text: "Oh man, an owlbear? Those things hit like trucks.",
    conf: 0.88,
  },
  {
    id: "8",
    who: "Theron",
    time: "19:43",
    source: "voice",
    cls: "table_talk",
    text: "I've got healing word prepped, we'll be fine.",
    conf: 0.72,
  },
  {
    id: "9",
    who: "DM",
    time: "19:43",
    source: "voice",
    cls: "dm_narration",
    text: "Everyone roll initiative.",
    conf: 0.95,
  },
  {
    id: "10",
    who: "Vex",
    time: "19:43",
    source: "roll",
    roll: { formula: "1d20+4", result: 22, type: "Initiative" },
  },
  {
    id: "11",
    who: "Kael",
    time: "19:43",
    source: "roll",
    roll: { formula: "1d20+1", result: 17, type: "Initiative" },
  },
  {
    id: "12",
    who: "Vex",
    time: "19:44",
    source: "voice",
    cls: "ic_dialogue",
    text: "Alright \u2014 Kael, take the big one. Theron, keep us standing. Lyra, light them up. I'll handle the boss.",
    conf: 0.95,
  },
  {
    id: "13",
    who: "Vex",
    time: "19:44",
    source: "voice",
    cls: "ic_action",
    text: "I drop from my branch and drive my shortsword into the goblin boss.",
    conf: 0.97,
  },
  {
    id: "14",
    who: "Vex",
    time: "19:44",
    source: "roll",
    roll: { formula: "1d20+7", result: 24, type: "Attack \u2192 Goblin Boss" },
  },
  {
    id: "15",
    who: "Vex",
    time: "19:44",
    source: "roll",
    roll: { formula: "1d6+4+3d6", result: 19, type: "Sneak Attack Damage" },
  },
  {
    id: "16",
    who: "DM",
    time: "19:44",
    source: "voice",
    cls: "dm_narration",
    text: "Nineteen damage. The goblin boss staggers, blood pouring from his chest. He snarls something in Goblin.",
    conf: 0.98,
  },
  {
    id: "17",
    who: "DM",
    time: "19:44",
    source: "typed",
    cls: "private",
    text: "You understand Goblin \u2014 he's calling for reinforcements from the cave. Maybe two rounds.",
    private_to: "vex",
  },
  {
    id: "18",
    who: "Kael",
    time: "19:45",
    source: "voice",
    cls: "ic_action",
    text: "My turn. I charge the owlbear \u2014 two attacks with my longsword.",
    conf: 0.96,
  },
  {
    id: "19",
    who: "Kael",
    time: "19:45",
    source: "roll",
    roll: { formula: "1d20+7", result: 14, type: "Attack \u2192 Owlbear" },
  },
  {
    id: "20",
    who: "Kael",
    time: "19:45",
    source: "roll",
    roll: {
      formula: "1d20+7",
      result: 21,
      type: "Attack \u2192 Owlbear (2nd)",
    },
  },
  {
    id: "21",
    who: "Kael",
    time: "19:45",
    source: "roll",
    roll: { formula: "1d8+4", result: 11, type: "Longsword Damage" },
  },
  {
    id: "22",
    who: "DM",
    time: "19:45",
    source: "voice",
    cls: "dm_narration",
    text: "First swing goes wide. The second catches it across the flank \u2014 eleven damage. It screams, a horrible shrieking sound.",
    conf: 0.97,
  },
  {
    id: "23",
    who: "Lyra",
    time: "19:46",
    source: "voice",
    cls: "rules",
    text: "Does that shriek force a concentration check? I'm holding Bless.",
    conf: 0.89,
    rag: true,
  },
];

export const MOCK_MONSTERS: Monster[] = [
  {
    name: "Owlbear",
    hp: 42,
    maxHp: 59,
    ac: 13,
    init: 8,
    cr: "3",
    conditions: [],
  },
  {
    name: "Goblin Boss",
    hp: 11,
    maxHp: 21,
    ac: 17,
    init: 14,
    cr: "1",
    conditions: ["Prone"],
  },
  {
    name: "Goblin \u00D73",
    hp: 7,
    maxHp: 7,
    ac: 15,
    init: 6,
    cr: "\u00BC",
    conditions: [],
  },
];

export const MOCK_RAG: RAGChunk[] = [
  {
    source: "PHB p.203",
    title: "Concentration",
    text: "Taking damage \u2192 Con save. DC = 10 or half damage, whichever is higher. Owlbear shriek is flavor, not damage \u2014 no save needed.",
    rel: 0.95,
    auto: true,
  },
  {
    source: "MM p.249",
    title: "Owlbear",
    text: "Multiattack: beak + claws. Keen Sight/Smell: adv on Perception. No shriek ability in stat block.",
    rel: 0.94,
    pinned: true,
  },
  {
    source: "MM p.166",
    title: "Goblin Boss \u2014 Redirect Attack",
    text: "Reaction: swap with goblin within 5ft when targeted. Chosen goblin becomes target.",
    rel: 0.91,
  },
  {
    source: "PHB p.96",
    title: "Sneak Attack (5th)",
    text: "3d6 extra, once/turn. Advantage or ally within 5ft. Finesse or ranged weapon.",
    rel: 0.87,
  },
];

export const MOCK_ENCOUNTERS: PlannedEncounter[] = [
  {
    name: "Cragmaw Cave \u2014 Entry",
    monsters: "4\u00D7 Goblin, 2\u00D7 Wolf",
    diff: "Medium",
    notes: "Stealth DC 12 to avoid lookout. Wolves chained.",
  },
  {
    name: "Cragmaw Cave \u2014 Bridge",
    monsters: "1\u00D7 Goblin Boss, 3\u00D7 Goblin",
    diff: "Hard",
    notes: "Boss can trigger flood. Dex DC 13 or swept away.",
  },
  {
    name: "Cragmaw Cave \u2014 Klarg",
    monsters: "1\u00D7 Bugbear, 1\u00D7 Wolf, 2\u00D7 Goblin",
    diff: "Deadly",
    notes: "Klarg negotiates below half HP. Has stolen goods.",
  },
];

export const MOCK_SESSIONS: SessionSummary[] = [
  {
    n: 3,
    date: "Feb 9",
    text: "Ambushed on Triboar Trail. Captured goblin \u2192 Cragmaw hideout. Gundren taken to 'the castle.'",
  },
  {
    n: 2,
    date: "Feb 2",
    text: "Arrived Phandalin. Met Sildar Hallwinter. Investigated Redbrand thugs at Stonehill Inn.",
  },
];

export const MOCK_WORLD_STATE: WorldStateEntry[] = [
  { key: "Location", value: "Triboar Trail \u2192 Cragmaw Hideout" },
  { key: "Quest", value: "Find Gundren Rockseeker, locate Wave Echo Cave" },
  {
    key: "Threats",
    value: "Cragmaw Goblins, Black Spider (unknown), Redbrand Ruffians",
  },
  {
    key: "Open Threads",
    value: "Redbrand hideout under Tresendar Manor. Old Owl Well miners.",
  },
];

export const MOCK_LORE: LoreEntry[] = [
  {
    fact: "Goblin boss called for cave reinforcements in Goblin.",
    src: "Overheard, Session 4",
    isNew: true,
  },
  {
    fact: "Cragmaw goblins act under orders from 'the Black Spider.'",
    src: "Goblin prisoner",
  },
  {
    fact: "Gundren taken to 'the castle' \u2014 location unknown.",
    src: "Session 3",
  },
];

export const MOCK_QUICK_ROLLS: QuickRoll[] = [
  { label: "Shortsword", formula: "1d20+7", sub: "Attack" },
  { label: "Damage", formula: "1d6+4", sub: "Piercing" },
  { label: "Sneak Attack", formula: "3d6", sub: "Extra" },
  { label: "Stealth", formula: "1d20+10", sub: "Expertise" },
  { label: "Perception", formula: "1d20+3", sub: "Passive 13" },
];

export const MOCK_VEX_STATS: AbilityScore[] = [
  { name: "STR", modifier: 0 },
  { name: "DEX", modifier: 4 },
  { name: "CON", modifier: 1 },
  { name: "INT", modifier: 2 },
  { name: "WIS", modifier: 0 },
  { name: "CHA", modifier: 2 },
];

export const MOCK_VEX_FULL_STATS: AbilityScore[] = [
  { name: "STR", value: 10, modifier: 0 },
  { name: "DEX", value: 18, modifier: 4 },
  { name: "CON", value: 12, modifier: 1 },
  { name: "INT", value: 14, modifier: 2 },
  { name: "WIS", value: 10, modifier: 0 },
  { name: "CHA", value: 14, modifier: 2 },
];

export const MOCK_INVENTORY: InventoryItem[] = [
  {
    name: "Shortsword",
    detail: "1d6 piercing, finesse, light",
    equipped: true,
  },
  { name: "Shortbow", detail: "1d6 piercing, range 80/320", equipped: true },
  { name: "Leather Armor", detail: "AC 11 + Dex modifier", equipped: true },
  { name: "Thieves' Tools", detail: "Proficient", equipped: false },
];

export const MOCK_JOURNAL: JournalEntry[] = [
  {
    n: 3,
    date: "Feb 9",
    text: "Ambushed by goblins. Spotted the ambush \u2014 24 Perception. Took two out from the trees. Captured one: Cragmaw Cave, 'the Black Spider,' Gundren taken to a castle.",
  },
  {
    n: 2,
    date: "Feb 2",
    text: "Phandalin. Pickpocketed Redbrand leader's note \u2014 'Glasstaff' at Tresendar Manor.",
  },
];

export const MOCK_FULL_LORE: LoreEntry[] = [
  {
    fact: "Gundren Rockseeker hired the party for Phandalin escort.",
    src: "Session 1",
  },
  { fact: "Cragmaw goblins serve 'the Black Spider.'", src: "Session 3" },
  {
    fact: "Gundren taken to 'the castle' \u2014 unknown location.",
    src: "Goblin prisoner",
  },
  {
    fact: "'Glasstaff' leads Redbrands from Tresendar Manor.",
    src: "Pickpocketed note",
  },
];
