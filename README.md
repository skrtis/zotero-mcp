# Zotero MCP Server for Poke

An MCP server that gives [Poke](https://github.com/InteractionCo/mcp-server-template) access to your Zotero research library. Built with [FastMCP](https://github.com/jlowin/fastmcp) following the InteractionCo template.

## Tools

| Tool | Description |
|------|-------------|
| `search_items` | Search the library by keyword |
| `get_recent_items` | Get recently added items |
| `search_by_tag` | Filter items by tag |
| `get_tags` | List all tags in the library |
| `get_item_metadata` | Get full metadata for an item by key |
| `get_item_fulltext` | Extract full text from a paper (local mode) |
| `get_item_children` | List attachments and notes for an item |
| `get_item_notes` | Get note content for an item |
| `get_item_annotations` | Get PDF highlights and comments (local mode) |
| `get_collections` | List all collections |
| `get_collection_items` | Get items in a specific collection |
| `list_library` | One line per item (key, year, author, title, tags, collections) for the whole library or one collection |
| `create_note` | Create a new note, optionally attached to an item |
| `add_item_by_doi` | Add a paper to Zotero by DOI |
| `update_item_tags` | Add and/or remove tags on one or more items |
| `rename_tag` | Rename a tag on every item that has it (merges if the new tag exists) |
| `delete_tags` | Remove tags from every item in the library |
| `create_collection` | Create a collection or subcollection |
| `update_collection` | Rename a collection or move it under another one |
| `delete_collection` | Delete a collection (its items stay in the library) |
| `add_to_collection` | Add items to a collection |
| `remove_from_collection` | Remove items from a collection (they stay in the library) |
| `get_library_info` | Show connection status and library details |

The write tools need an API key with write access.

## Setup

**1. Copy the example env file and fill it in:**

```bash
cp .env.example .env
```

You need:
- **Library ID** — the number in your Zotero profile URL, or at [zotero.org/settings/keys](https://www.zotero.org/settings/keys)
- **API key** — create one at [zotero.org/settings/keys/new](https://www.zotero.org/settings/keys/new) with read (and optionally write) access

**2. Install dependencies:**

```bash
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**3. Run locally:**

```bash
.venv/bin/python src/server.py
```

The server starts at `http://localhost:8000/mcp`.

## Authentication

Every request must carry `Authorization: Bearer <MCP_AUTH_TOKEN>`; anything else gets a 401. The server refuses
to start without `MCP_AUTH_TOKEN` unless `MCP_ALLOW_NO_AUTH=true` is set (local testing only). Generate a token with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put it in `.env` locally and in the Render dashboard for the deployed server. Clients send it as a header, e.g. Claude Code:

```bash
claude mcp add --transport http zotero https://<your-render-url>/mcp --header "Authorization: Bearer <token>"
```

## Local Mode (full-text + annotations)

Set `ZOTERO_LOCAL=true` to connect directly to the Zotero app running on your machine. This enables:
- `get_item_fulltext` — extract text from PDFs
- `get_item_annotations` — read PDF highlights and comments

In Zotero: **Edit → Preferences → Advanced → Allow other applications to access Zotero**

## Connecting Poke

Add this to your Poke MCP configuration:

```json
{
  "mcpServers": {
    "zotero": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Or if deployed to Render, replace `localhost:8000` with your Render URL.

## Deploy to Render

Push this repo to GitHub, connect it to [Render](https://render.com), and set the environment variables (`ZOTERO_LIBRARY_ID`, `ZOTERO_API_KEY`, `MCP_AUTH_TOKEN`) in the Render dashboard. The `render.yaml` handles everything else.
