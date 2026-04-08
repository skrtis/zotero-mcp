#!/usr/bin/env python3
"""
Zotero MCP Server for Poke
Gives Poke access to your Zotero research library via the Model Context Protocol.
"""

import os
import json
from typing import Optional
from functools import lru_cache

from fastmcp import FastMCP
from pyzotero import zotero
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("Zotero MCP Server")

# ---------------------------------------------------------------------------
# Client helpers
# ---------------------------------------------------------------------------

def _get_client() -> zotero.Zotero:
    library_id = os.environ.get("ZOTERO_LIBRARY_ID")
    api_key = os.environ.get("ZOTERO_API_KEY")
    library_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "user")
    use_local = os.environ.get("ZOTERO_LOCAL", "false").lower() == "true"

    if not library_id:
        raise ValueError("ZOTERO_LIBRARY_ID environment variable is required")
    if not api_key and not use_local:
        raise ValueError("ZOTERO_API_KEY environment variable is required for web API mode")

    return zotero.Zotero(library_id, library_type, api_key or "", local=use_local)


def _format_item(item: dict) -> str:
    """Convert a Zotero item to a readable markdown string."""
    data = item.get("data", {})
    lines = []

    title = data.get("title", "Untitled")
    lines.append(f"**{title}**")
    lines.append(f"- Key: `{data.get('key', '')}`")
    lines.append(f"- Type: {data.get('itemType', 'unknown')}")

    creators = data.get("creators", [])
    if creators:
        authors = []
        for c in creators:
            if "name" in c:
                authors.append(c["name"])
            else:
                name = " ".join(filter(None, [c.get("firstName", ""), c.get("lastName", "")]))
                if name:
                    authors.append(name)
        if authors:
            lines.append(f"- Authors: {', '.join(authors)}")

    if data.get("date"):
        lines.append(f"- Date: {data['date']}")
    if data.get("publicationTitle"):
        lines.append(f"- Publication: {data['publicationTitle']}")
    if data.get("journalAbbreviation"):
        lines.append(f"- Journal: {data['journalAbbreviation']}")
    if data.get("volume"):
        lines.append(f"- Volume: {data['volume']}")
    if data.get("issue"):
        lines.append(f"- Issue: {data['issue']}")
    if data.get("pages"):
        lines.append(f"- Pages: {data['pages']}")
    if data.get("DOI"):
        lines.append(f"- DOI: {data['DOI']}")
    if data.get("url"):
        lines.append(f"- URL: {data['url']}")
    if data.get("ISBN"):
        lines.append(f"- ISBN: {data['ISBN']}")
    if data.get("publisher"):
        lines.append(f"- Publisher: {data['publisher']}")

    tags = data.get("tags", [])
    if tags:
        tag_names = [t.get("tag", "") for t in tags if t.get("tag")]
        if tag_names:
            lines.append(f"- Tags: {', '.join(tag_names)}")

    if data.get("abstractNote"):
        abstract = data["abstractNote"]
        if len(abstract) > 500:
            abstract = abstract[:500] + "…"
        lines.append(f"- Abstract: {abstract}")

    return "\n".join(lines)


def _is_regular_item(item: dict) -> bool:
    """Return True for citable items — excludes attachments, notes, and annotations."""
    return item.get("data", {}).get("itemType") not in ("attachment", "note", "annotation")


def _format_items_list(items: list[dict]) -> str:
    if not items:
        return "No items found."
    parts = []
    for item in items:
        parts.append(_format_item(item))
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Search tools
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Search your Zotero library for items matching a query string. "
    "Returns titles, authors, dates, and keys for matched items."
))
def search_items(query: str, limit: int = 20) -> str:
    try:
        zot = _get_client()
        items = zot.items(q=query, limit=100)
        items = [i for i in items if _is_regular_item(i)][:min(limit, 100)]
        return _format_items_list(items)
    except Exception as e:
        return f"Error searching items: {e}"


@mcp.tool(description=(
    "Get the most recently added items from your Zotero library."
))
def get_recent_items(limit: int = 10) -> str:
    try:
        zot = _get_client()
        items = zot.items(limit=100, sort="dateAdded", direction="desc")
        items = [i for i in items if _is_regular_item(i)][:min(limit, 50)]
        return _format_items_list(items)
    except Exception as e:
        return f"Error fetching recent items: {e}"


@mcp.tool(description=(
    "Search Zotero items by tag. Returns all items that have the specified tag."
))
def search_by_tag(tag: str, limit: int = 20) -> str:
    try:
        zot = _get_client()
        items = zot.items(tag=tag, limit=100)
        items = [i for i in items if _is_regular_item(i)][:min(limit, 100)]
        return _format_items_list(items)
    except Exception as e:
        return f"Error searching by tag '{tag}': {e}"


@mcp.tool(description=(
    "List all tags in your Zotero library alphabetically."
))
def get_tags() -> str:
    try:
        zot = _get_client()
        tags = zot.tags()
        if not tags:
            return "No tags found in your library."
        tag_list = []
        for t in tags:
            if isinstance(t, dict):
                name = t.get("tag", "")
            else:
                name = str(t)
            if name:
                tag_list.append(name)
        tag_list = sorted(tag_list)
        return "Tags in your library:\n" + "\n".join(f"- {t}" for t in tag_list)
    except Exception as e:
        return f"Error fetching tags: {e}"


# ---------------------------------------------------------------------------
# Item retrieval tools
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Get detailed metadata for a specific Zotero item by its key "
    "(the short alphanumeric ID like 'ABC12345')."
))
def get_item_metadata(item_key: str) -> str:
    try:
        zot = _get_client()
        item = zot.item(item_key)
        return _format_item(item)
    except Exception as e:
        return f"Error fetching item '{item_key}': {e}"


@mcp.tool(description=(
    "Get the full text content of a Zotero item's attachment. "
    "Only works in local mode (ZOTERO_LOCAL=true). "
    "Returns the extracted text from the PDF or other attachment."
))
def get_item_fulltext(item_key: str) -> str:
    use_local = os.environ.get("ZOTERO_LOCAL", "false").lower() == "true"
    if not use_local:
        return (
            "Full text extraction requires local Zotero mode. "
            "Set ZOTERO_LOCAL=true and run the server locally alongside Zotero."
        )
    try:
        zot = _get_client()
        fulltext = zot.fulltext_item(item_key)
        if not fulltext or not fulltext.get("content"):
            return f"No full text available for item '{item_key}'."
        content = fulltext["content"]
        if len(content) > 8000:
            content = content[:8000] + "\n\n[Truncated — full text is longer]"
        return content
    except Exception as e:
        return f"Error fetching full text for '{item_key}': {e}"


@mcp.tool(description=(
    "Get the child items (attachments and notes) for a Zotero item by its key."
))
def get_item_children(item_key: str) -> str:
    try:
        zot = _get_client()
        children = zot.children(item_key)
        if not children:
            return f"No children found for item '{item_key}'."

        lines = [f"Children of `{item_key}`:\n"]
        for child in children:
            data = child.get("data", {})
            item_type = data.get("itemType", "unknown")
            title = data.get("title") or data.get("filename") or data.get("note", "")[:80] or "Untitled"
            key = data.get("key", "")
            lines.append(f"- [{item_type}] **{title}** (key: `{key}`)")
            if data.get("contentType"):
                lines.append(f"  Content type: {data['contentType']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching children for '{item_key}': {e}"


@mcp.tool(description=(
    "Get the notes attached to a Zotero item. Returns note content in plain text."
))
def get_item_notes(item_key: str) -> str:
    try:
        zot = _get_client()
        children = zot.children(item_key)
        notes = [c for c in children if c.get("data", {}).get("itemType") == "note"]
        if not notes:
            return f"No notes found for item '{item_key}'."

        parts = []
        for note in notes:
            data = note.get("data", {})
            key = data.get("key", "")
            content = data.get("note", "")
            # Strip basic HTML tags
            import re
            content = re.sub(r"<[^>]+>", " ", content).strip()
            content = re.sub(r"\s+", " ", content)
            parts.append(f"Note `{key}`:\n{content}")
        return "\n\n---\n\n".join(parts)
    except Exception as e:
        return f"Error fetching notes for '{item_key}': {e}"


@mcp.tool(description=(
    "Get annotations (highlights and comments) from a Zotero item's PDF attachment. "
    "Only works in local mode (ZOTERO_LOCAL=true)."
))
def get_item_annotations(item_key: str) -> str:
    use_local = os.environ.get("ZOTERO_LOCAL", "false").lower() == "true"
    if not use_local:
        return (
            "Annotation extraction requires local Zotero mode. "
            "Set ZOTERO_LOCAL=true and run the server locally alongside Zotero."
        )
    try:
        zot = _get_client()
        children = zot.children(item_key)

        # Find PDF attachment keys
        pdf_keys = [
            c["data"]["key"] for c in children
            if c.get("data", {}).get("contentType") == "application/pdf"
        ]
        if not pdf_keys:
            return f"No PDF attachments found for item '{item_key}'."

        all_annotations = []
        for pdf_key in pdf_keys:
            annotations = zot.children(pdf_key)
            for ann in annotations:
                data = ann.get("data", {})
                if data.get("itemType") != "annotation":
                    continue
                ann_type = data.get("annotationType", "unknown")
                text = data.get("annotationText", "")
                comment = data.get("annotationComment", "")
                color = data.get("annotationColor", "")
                page = data.get("annotationPageLabel", "")

                parts = [f"[{ann_type}]"]
                if page:
                    parts.append(f"p.{page}")
                if color:
                    parts.append(f"({color})")
                line = " ".join(parts)
                if text:
                    line += f"\n  > {text}"
                if comment:
                    line += f"\n  Comment: {comment}"
                all_annotations.append(line)

        if not all_annotations:
            return f"No annotations found for item '{item_key}'."
        return f"Annotations for `{item_key}`:\n\n" + "\n\n".join(all_annotations)
    except Exception as e:
        return f"Error fetching annotations for '{item_key}': {e}"


# ---------------------------------------------------------------------------
# Collection tools
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "List all collections in your Zotero library, showing their names and keys."
))
def get_collections() -> str:
    try:
        zot = _get_client()
        collections = zot.collections()
        if not collections:
            return "No collections found in your library."

        # Build a map for parent lookup
        col_map = {c["data"]["key"]: c["data"] for c in collections}
        lines = ["Collections in your library:\n"]

        def get_path(col_key: str) -> str:
            parts = []
            current = col_map.get(col_key)
            while current:
                parts.insert(0, current.get("name", ""))
                parent_key = current.get("parentCollection")
                current = col_map.get(parent_key) if parent_key else None
            return " / ".join(parts)

        sorted_cols = sorted(collections, key=lambda c: get_path(c["data"]["key"]))
        for col in sorted_cols:
            data = col["data"]
            path = get_path(data["key"])
            count = data.get("numItems", "?")
            lines.append(f"- **{path}** (key: `{data['key']}`, items: {count})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching collections: {e}"


@mcp.tool(description=(
    "Get items in a specific Zotero collection by its key. "
    "Use get_collections() first to find collection keys."
))
def get_collection_items(collection_key: str, limit: int = 20) -> str:
    try:
        zot = _get_client()
        items = zot.collection_items(collection_key, limit=100)
        items = [i for i in items if _is_regular_item(i)][:min(limit, 100)]
        return _format_items_list(items)
    except Exception as e:
        return f"Error fetching items for collection '{collection_key}': {e}"


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Create a new note in Zotero, optionally attached to an existing item. "
    "If item_key is provided the note becomes a child of that item. "
    "Tags should be a comma-separated string, e.g. 'reading notes, important'."
))
def create_note(
    content: str,
    item_key: Optional[str] = None,
    tags: Optional[str] = None,
) -> str:
    try:
        zot = _get_client()
        tag_list = []
        if tags:
            tag_list = [{"tag": t.strip()} for t in tags.split(",") if t.strip()]

        note_data = {
            "itemType": "note",
            "note": content,
            "tags": tag_list,
        }
        if item_key:
            note_data["parentItem"] = item_key

        result = zot.create_items([note_data])
        if result and result.get("successful"):
            created_key = list(result["successful"].values())[0].get("data", {}).get("key", "")
            return f"Note created successfully (key: `{created_key}`)."
        return f"Note creation returned: {json.dumps(result)}"
    except Exception as e:
        return f"Error creating note: {e}"


@mcp.tool(description=(
    "Add a Zotero item by DOI. Fetches metadata automatically from CrossRef. "
    "Example: add_item_by_doi('10.1038/nature12373')"
))
def add_item_by_doi(doi: str) -> str:
    try:
        import requests
        zot = _get_client()

        # Use Zotero's translation server or CrossRef
        doi = doi.strip().lstrip("https://doi.org/").lstrip("http://doi.org/")

        # Fetch metadata from CrossRef
        url = f"https://api.crossref.org/works/{doi}"
        resp = requests.get(url, headers={"User-Agent": "ZoteroMCP/1.0 (mailto:user@example.com)"}, timeout=10)
        if resp.status_code != 200:
            return f"Could not fetch metadata for DOI '{doi}' (HTTP {resp.status_code})."

        work = resp.json().get("message", {})
        item_type = "journalArticle"
        if work.get("type") == "book":
            item_type = "book"
        elif work.get("type") == "book-chapter":
            item_type = "bookSection"

        creators = []
        for author in work.get("author", []):
            creators.append({
                "creatorType": "author",
                "firstName": author.get("given", ""),
                "lastName": author.get("family", ""),
            })

        title_list = work.get("title", [""])
        title = title_list[0] if title_list else ""

        date_parts = work.get("published", {}).get("date-parts", [[]])[0]
        date = "-".join(str(p) for p in date_parts) if date_parts else ""

        container = work.get("container-title", [""])
        journal = container[0] if container else ""

        new_item = {
            "itemType": item_type,
            "title": title,
            "creators": creators,
            "date": date,
            "DOI": doi,
            "url": f"https://doi.org/{doi}",
            "publicationTitle": journal,
            "volume": work.get("volume", ""),
            "issue": work.get("issue", ""),
            "pages": work.get("page", ""),
            "tags": [],
        }

        result = zot.create_items([new_item])
        if result and result.get("successful"):
            created_key = list(result["successful"].values())[0].get("data", {}).get("key", "")
            return f"Item added successfully (key: `{created_key}`):\n\n{_format_item(list(result['successful'].values())[0])}"
        return f"Item creation returned: {json.dumps(result)}"
    except Exception as e:
        return f"Error adding item by DOI '{doi}': {e}"


# ---------------------------------------------------------------------------
# Library info
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Get information about your connected Zotero library, including the library ID, "
    "type, and connection mode (local or web API)."
))
def get_library_info() -> str:
    library_id = os.environ.get("ZOTERO_LIBRARY_ID", "not set")
    library_type = os.environ.get("ZOTERO_LIBRARY_TYPE", "user")
    use_local = os.environ.get("ZOTERO_LOCAL", "false").lower() == "true"
    mode = "local (Zotero app on this machine)" if use_local else "web API (api.zotero.org)"

    try:
        zot = _get_client()
        items = zot.items(limit=1)
        connected = True
    except Exception as e:
        connected = False
        error = str(e)

    lines = [
        "**Zotero Library Info**",
        f"- Library ID: `{library_id}`",
        f"- Library type: {library_type}",
        f"- Connection mode: {mode}",
        f"- Connected: {'✓ Yes' if connected else f'✗ No — {error}'}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    print(f"Starting Zotero MCP server on {host}:{port}")
    print(f"  Library ID:   {os.environ.get('ZOTERO_LIBRARY_ID', 'not set')}")
    print(f"  Library type: {os.environ.get('ZOTERO_LIBRARY_TYPE', 'user')}")
    print(f"  Local mode:   {os.environ.get('ZOTERO_LOCAL', 'false')}")

    mcp.run(
        transport="http",
        host=host,
        port=port,
        stateless_http=True,
    )
