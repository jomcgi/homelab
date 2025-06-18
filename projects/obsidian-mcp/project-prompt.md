  ### Project Prompt: Obsidian Knowledge MCP Server

  **1. Core Value Proposition:**
  *   **Problem:** Personal knowledge stored in Obsidian notes is inaccessible during LLM conversations, limiting the AI's ability to provide
   contextually-aware responses based on existing insights.
  *   **Solution:** An MCP server that enables Claude to search, discover, and retrieve relevant notes from a published Obsidian vault to
  enhance conversations with personal knowledge context.
  *   **Value:** Transforms isolated LLM chats into knowledge-enhanced conversations that can critique designs, synthesize concepts, and
  generate insights based on accumulated personal knowledge.

  **2. Intended Use Case:**
  *   **Primary User:** Knowledge worker with curated Obsidian notes who wants to leverage their existing insights during LLM conversations.
  *   **Scenario:** User is discussing leadership principles with Claude. MCP server searches notes, finds related content (leadership,
  management, team dynamics), user selects relevant notes, and Claude provides responses informed by the user's existing thoughts and
  frameworks on these topics.

  **3. MVP Scope & Key Features:**
  *   Search notes by text content, titles, and tags
  *   Browse note titles and metadata to aid in discovery
  *   Retrieve full note content including wikilinks and structure
  *   Basic wikilink traversal (following links between content notes)
  *   Filter out index pages (top-level summary pages) from traversal
  *   Work with GitHub-published notes (leveraging existing publishing workflow)
  *   **Explicitly de-scoped for MVP:** Content summaries, advanced graph analysis, automatic relevance scoring, vault editing capabilities

  **4. Technical Constraints & Considerations:**
  *   **Stack:** Python MCP server, integrates with GitHub-published markdown files
  *   **Key Design Principle:** "Simplicity over sophistication" - focus on reliable text search and retrieval rather than complex AI-powered
   relevance
  *   **Scope:** Personal use only, optimized for single user's vault structure

  **5. Acceptance Criteria & Testing Plan:**
  *   **Behavior 1:** User searches for notes containing "leadership"
      *   **Test:** Verify relevant notes are returned with titles, tags, and brief metadata
  *   **Behavior 2:** User requests full content of a specific note
      *   **Test:** Verify complete markdown content is returned including wikilinks and formatting
  *   **Behavior 3:** User traverses wikilinks from a content note
      *   **Test:** Verify linked notes are accessible while index pages are filtered out
  *   **Behavior 4:** User searches for notes with specific tags
      *   **Test:** Verify notes with matching tags are identified and retrievable

  **6. Call to Action: Implementation Strategy**
  *   **Your Task:** Implement the MCP server described in this brief.
  *   **Process:**
      1.  **Plan First:** Propose a high-level technical plan including file structure, key components, data flow, and GitHub integration
  approach. **No implementation code yet.**
      2.  **Await Approval:** Present the plan for review and feedback.
      3.  **Execute Step-by-Step:** Implement MVP features incrementally, focusing on search → retrieval → traversal workflow.