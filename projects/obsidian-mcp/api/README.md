# Obsidian Knowledge MCP Server

An MCP (Model Context Protocol) server that enables Claude to search, discover, and retrieve relevant notes from a published Obsidian vault on GitHub.

## Features

- **Search notes** by text content, titles, and tags
- **Browse note titles** and metadata to aid in discovery  
- **Retrieve full note content** including wikilinks and structure
- **Basic wikilink traversal** (following links between content notes)
- **Filter out index pages** from traversal
- **Work with GitHub-published notes** (leveraging existing publishing workflow)

## Architecture

The server follows clean architecture principles:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ FastMCP Server  │    │ Obsidian        │    │ GitHub Client   │
│ (Tools)         │───▶│ Service         │───▶│ (Raw Files)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │ Note Parser +   │
                       │ Search Engine   │
                       └─────────────────┘
```

## Configuration

Set these environment variables:

- `OBSIDIAN_REPO_URL` - GitHub repository URL (required)
- `GITHUB_TOKEN` - Personal access token (optional for public repos)
- `OBSIDIAN_BRANCH` - Git branch to use (default: main)
- `OBSIDIAN_PATH_PREFIX` - Path within repo (default: root)

## Testing

### Basic Functionality Test

```bash
cd api
python3 test_basic.py
```

### Unit Tests

```bash
cd api
python3 -m pytest tests/
```

### Docker Test

```bash
docker build -t obsidian-mcp .
docker run --rm -e OBSIDIAN_REPO_URL=your/repo obsidian-mcp
```

## Usage

The server exposes these MCP tools:

1. **search_notes** - Search by content/title/tags
2. **get_note** - Retrieve full note content
3. **list_notes** - Browse all available notes
4. **follow_wikilink** - Traverse wikilinks between notes

## Implementation Notes

- Uses **FastMCP** for clean Pydantic-based tool definitions
- **No circular imports** - clean separation of concerns
- **BaseSettings** for robust configuration management
- **Simple search engine** prioritizing reliability over sophistication
- **Index page filtering** to focus on content notes