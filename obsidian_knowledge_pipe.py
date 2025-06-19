"""
title: Obsidian Knowledge Base
author: homelab
author_url: https://github.com/jomcgi/homelab
funding_url: https://github.com/jomcgi/homelab
version: 0.1
"""

import httpx
import re
from pydantic import BaseModel, Field
from typing import Optional


class Pipe:
    class Valves(BaseModel):
        obsidian_api_url: str = Field(
            default="http://obsidian-mcp.obsidian-mcp.svc.cluster.local:8000",
            description="Base URL for the Obsidian Knowledge API"
        )
        search_limit: int = Field(
            default=5,
            description="Default maximum number of search results to return"
        )
        timeout: int = Field(
            default=30,
            description="Request timeout in seconds"
        )
        model_name: str = Field(
            default="Obsidian Knowledge Base",
            description="Display name for the model"
        )

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        return [
            {
                "id": "obsidian-knowledge",
                "name": self.valves.model_name,
            }
        ]

    async def pipe(self, body: dict, __user__: Optional[dict] = None) -> str:
        try:
            # Get the user's message
            messages = body.get("messages", [])
            if not messages:
                return "Please provide a message to search the knowledge base."
            
            user_message = messages[-1].get("content", "").strip()
            
            # Detect what the user wants to do based on their message
            if self._is_search_request(user_message):
                return await self._handle_search(user_message)
            elif self._is_list_request(user_message):
                return await self._handle_list()
            elif self._is_get_note_request(user_message):
                return await self._handle_get_note(user_message)
            else:
                # Default to search
                return await self._handle_search(user_message)
                
        except Exception as e:
            return f"Error processing request: {str(e)}"

    def _is_search_request(self, message: str) -> bool:
        search_keywords = ["search", "find", "look for", "about", "on", "regarding"]
        return any(keyword in message.lower() for keyword in search_keywords)

    def _is_list_request(self, message: str) -> bool:
        list_keywords = ["list", "show all", "all notes", "what notes"]
        return any(keyword in message.lower() for keyword in list_keywords)

    def _is_get_note_request(self, message: str) -> bool:
        get_keywords = ["get note", "show note", "full content", "read note"]
        return any(keyword in message.lower() for keyword in get_keywords)

    async def _handle_search(self, query: str) -> str:
        try:
            # Clean the query - remove common prefixes
            clean_query = re.sub(r'^(search for|find|look for|about|on|regarding)\s+', '', query.lower()).strip()
            
            search_payload = {
                "query": clean_query,
                "limit": self.valves.search_limit
            }

            async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
                response = await client.post(
                    f"{self.valves.obsidian_api_url}/api/search",
                    json=search_payload,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                results = response.json()

            if not results:
                return f"No notes found matching '{clean_query}'. Try different keywords or ask me to list all notes."

            # Format results
            formatted_results = [f"Found {len(results)} notes matching '{clean_query}':\n"]
            
            for i, result in enumerate(results, 1):
                note = result["note"]
                score = result["relevance_score"]
                matched_content = result["matched_content"]
                
                formatted_result = f"""
## {i}. {note['title']} (Score: {score:.1f})

**Path:** `{note['path']}`
**Tags:** {', '.join(note['tags']) if note['tags'] else 'None'}

**Relevant Content:**
{matched_content[:400]}{'...' if len(matched_content) > 400 else ''}

---"""
                formatted_results.append(formatted_result)

            return "\n".join(formatted_results)

        except httpx.HTTPError as e:
            return f"Error searching notes: HTTP error occurred"
        except Exception as e:
            return f"Error searching notes: {str(e)}"

    async def _handle_list(self) -> str:
        try:
            async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
                response = await client.get(f"{self.valves.obsidian_api_url}/api/notes")
                response.raise_for_status()
                notes = response.json()

            if not notes:
                return "No notes found in the knowledge base."

            # Group notes by directory
            grouped_notes = {}
            for note in notes:
                # Extract directory from path
                path_parts = note['path'].split('/')
                if len(path_parts) > 1:
                    directory = '/'.join(path_parts[:-1])
                else:
                    directory = "Root"
                
                if directory not in grouped_notes:
                    grouped_notes[directory] = []
                grouped_notes[directory].append(note)

            # Format grouped output
            formatted_output = [f"📚 **Knowledge Base Overview** ({len(notes)} total notes)\n"]
            
            for directory, dir_notes in sorted(grouped_notes.items()):
                formatted_output.append(f"\n### 📁 {directory} ({len(dir_notes)} notes)")
                for note in sorted(dir_notes, key=lambda x: x['title'])[:10]:  # Limit per directory
                    tags_str = f" `{', '.join(note['tags'][:3])}`" if note['tags'] else ""
                    formatted_output.append(f"- **{note['title']}**{tags_str}")
                
                if len(dir_notes) > 10:
                    formatted_output.append(f"  ... and {len(dir_notes) - 10} more notes")

            formatted_output.append(f"\n💡 **Tip:** Ask me to 'search for [topic]' to find specific notes!")
            
            return "\n".join(formatted_output)

        except Exception as e:
            return f"Error listing notes: {str(e)}"

    async def _handle_get_note(self, message: str) -> str:
        try:
            # Try to extract note path from message
            # This is a simple implementation - could be improved with better parsing
            words = message.split()
            potential_paths = [word for word in words if '/' in word or word.endswith('.md')]
            
            if not potential_paths:
                return "Please specify a note path, e.g., 'get note src/site/notes/Notes/Software Design.md'"
            
            note_path = potential_paths[0]
            
            async with httpx.AsyncClient(timeout=self.valves.timeout) as client:
                response = await client.get(f"{self.valves.obsidian_api_url}/api/notes/{note_path}")
                response.raise_for_status()
                note = response.json()

            # Format full note
            formatted_note = f"""# {note['title']}

**Path:** `{note['path']}`
**Tags:** {', '.join(note['tags']) if note['tags'] else 'None'}
**Wikilinks:** {len(note['wikilinks'])} links
**Last Modified:** {note['last_modified'] or 'Unknown'}

---

{note['content']}"""

            return formatted_note

        except httpx.HTTPError as e:
            if hasattr(e, 'response') and e.response.status_code == 404:
                return f"Note not found. Use 'list notes' to see available notes."
            return f"Error retrieving note: {str(e)}"
        except Exception as e:
            return f"Error retrieving note: {str(e)}"