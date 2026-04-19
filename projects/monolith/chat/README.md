# Discord Bot

AI-powered Discord bot with embeddings, vision, web search, and channel summarisation.

## Overview

Responds to messages using on-cluster LLM inference, with context from the knowledge graph. Supports history backfill, channel summarisation, and multimodal inputs (images via vision).

| Module         | Description                                                         |
| -------------- | ------------------------------------------------------------------- |
| **bot**        | Core Discord bot with message handling and response generation      |
| **agent**      | LLM agent with tool execution (web search, knowledge graph, vision) |
| **backfill**   | Historical message import and re-processing                         |
| **summarizer** | Channel summarisation with scheduled digests                        |
| **explorer**   | Conversation exploration and search                                 |
| **vision**     | Image analysis via multimodal LLM                                   |
| **web_search** | Web search tool integration via SearXNG                             |
| **changelog**  | Changelog fetching and presentation                                 |
| **store**      | Message persistence with embedding storage                          |
