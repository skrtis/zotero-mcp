#!/usr/bin/env python3
"""
Zotero MCP Server for Poke
Gives Poke access to your Zotero research library via the Model Context Protocol.
"""

import os
import sys
import hmac
import json
from typing import Optional
from functools import lru_cache

from fastmcp import FastMCP
from pyzotero import zotero
from dotenv import load_dotenv
from starlette.middleware import Middleware
from starlette.responses import JSONResponse

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


def _split(value: Optional[str]) -> list[str]:
    """Split a comma-separated argument into a list of non-empty, stripped strings."""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _tag_names(item: dict) -> list[str]:
    return [t.get("tag", "") for t in item.get("data", {}).get("tags", []) if t.get("tag")]


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
        items = zot.items(q=query, limit=min(limit, 100))
        items = [i for i in items if _is_regular_item(i)]
        return _format_items_list(items)
    except Exception as e:
        return f"Error searching items: {e}"


@mcp.tool(description=(
    "Get the most recently added items from your Zotero library."
))
def get_recent_items(limit: int = 10) -> str:
    try:
        zot = _get_client()
        items = zot.items(limit=min(limit, 50), sort="dateAdded", direction="desc")
        items = [i for i in items if _is_regular_item(i)]
        return _format_items_list(items)
    except Exception as e:
        return f"Error fetching recent items: {e}"


@mcp.tool(description=(
    "Search Zotero items by tag. Returns all items that have the specified tag."
))
def search_by_tag(tag: str, limit: int = 20) -> str:
    try:
        zot = _get_client()
        items = zot.items(tag=tag, limit=min(limit, 100))
        items = [i for i in items if _is_regular_item(i)]
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
    "Pass the attachment key (not the parent item key). "
    "Returns the extracted text from the PDF or other attachment."
))
def get_item_fulltext(item_key: str) -> str:
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


def _format_annotation(ann: dict) -> str:
    """Format a single annotation dict into a readable string."""
    data = ann.get("data", {})
    ann_type = data.get("annotationType", "unknown")
    text = data.get("annotationText", "")
    comment = data.get("annotationComment", "")
    color = data.get("annotationColor", "")
    page = data.get("annotationPageLabel", "")
    key = data.get("key", "")

    parts = [f"[{ann_type}]"]
    if page:
        parts.append(f"p.{page}")
    if color:
        parts.append(f"({color})")
    if key:
        parts.append(f"key:{key}")
    line = " ".join(parts)
    if text:
        line += f"\n  > {text}"
    if comment:
        line += f"\n  Comment: {comment}"
    return line


@mcp.tool(description=(
    "Get annotations (highlights and comments) from a Zotero item's PDF attachment. "
    "Works with both the web API and local mode. "
    "Pass either a parent item key or a PDF attachment key."
))
def get_item_annotations(item_key: str) -> str:
    try:
        zot = _get_client()
        item = zot.item(item_key)
        item_type = item.get("data", {}).get("itemType", "")

        if item_type == "attachment":
            # item_key is already a PDF attachment — query its children directly
            pdf_keys = [item_key]
        else:
            # item_key is a parent item — find its PDF attachments
            children = zot.children(item_key)
            pdf_keys = [
                c["data"]["key"] for c in children
                if c.get("data", {}).get("contentType") == "application/pdf"
                or c.get("data", {}).get("itemType") == "attachment"
            ]
            if not pdf_keys:
                return f"No PDF attachments found for item '{item_key}'."

        all_annotations = []
        for pdf_key in pdf_keys:
            annotations = zot.children(pdf_key)
            for ann in annotations:
                if ann.get("data", {}).get("itemType") != "annotation":
                    continue
                all_annotations.append(_format_annotation(ann))

        if not all_annotations:
            return f"No annotations found for item '{item_key}'."
        return f"Annotations for `{item_key}`:\n\n" + "\n\n".join(all_annotations)
    except Exception as e:
        return f"Error fetching annotations for '{item_key}': {e}"


@mcp.tool(description=(
    "Get a single annotation by its key. Useful when you already have the annotation key "
    "from get_item_children or get_item_annotations. Returns the highlight text and comment."
))
def get_annotation(annotation_key: str) -> str:
    try:
        zot = _get_client()
        ann = zot.item(annotation_key)
        data = ann.get("data", {})
        if data.get("itemType") != "annotation":
            return f"Item '{annotation_key}' is not an annotation (type: {data.get('itemType')})."
        return _format_annotation(ann)
    except Exception as e:
        return f"Error fetching annotation '{annotation_key}': {e}"


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
            count = col.get("meta", {}).get("numItems", "?")
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
        items = zot.collection_items(collection_key, limit=min(limit, 100))
        items = [i for i in items if _is_regular_item(i)]
        return _format_items_list(items)
    except Exception as e:
        return f"Error fetching items for collection '{collection_key}': {e}"


@mcp.tool(description=(
    "List every item in the library (or in one collection) as one compact line each: "
    "key | year | first author | title | tags | collections. No limit — pages through everything. "
    "Use this to get an overview before reorganising tags or collections."
))
def list_library(collection_key: Optional[str] = None) -> str:
    try:
        zot = _get_client()
        query = zot.collection_items(collection_key) if collection_key else zot.items()
        items = [i for i in zot.everything(query) if _is_regular_item(i)]
        if not items:
            return "No items found."
        col_names = {c["data"]["key"]: c["data"].get("name", "") for c in zot.everything(zot.collections())}

        lines = [f"{len(items)} items (key | year | first author | title | tags | collections):"]
        for item in sorted(items, key=lambda i: i.get("data", {}).get("title", "").lower()):
            data = item.get("data", {})
            creators = data.get("creators", [])
            first = ""
            if creators:
                c = creators[0]
                first = c.get("name") or c.get("lastName", "")
                if len(creators) > 1:
                    first += " et al."
            year = (item.get("meta", {}).get("parsedDate") or data.get("date", ""))[:4]
            cols = ", ".join(col_names.get(k, k) for k in data.get("collections", []))
            lines.append(
                f"{data.get('key', '')} | {year} | {first} | {data.get('title', 'Untitled')} | "
                f"{', '.join(_tag_names(item)) or '-'} | {cols or '-'}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing library: {e}"


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
# Tag editing tools
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Add and/or remove tags on one or more items. item_keys, add and remove are "
    "comma-separated strings, e.g. item_keys='ABC12345, DEF67890', add='gLM, to read', "
    "remove='old tag'. Tags already present are not duplicated."
))
def update_item_tags(item_keys: str, add: Optional[str] = None, remove: Optional[str] = None) -> str:
    try:
        keys, to_add, to_remove = _split(item_keys), _split(add), set(_split(remove))
        if not keys:
            return "No item keys given."
        if not to_add and not to_remove:
            return "Nothing to do: give tags to add and/or remove."
        zot = _get_client()
        lines = []
        for key in keys:
            try:
                item = zot.item(key)
                before = _tag_names(item)
                tags = [t for t in item["data"].get("tags", []) if t.get("tag") not in to_remove]
                present = {t.get("tag") for t in tags}
                tags += [{"tag": t} for t in to_add if t not in present]
                after = [t["tag"] for t in tags]
                if after == before:
                    lines.append(f"- `{key}`: unchanged")
                    continue
                item["data"]["tags"] = tags
                zot.update_item(item)
                lines.append(f"- `{key}`: {', '.join(after) or '(no tags)'}")
            except Exception as e:
                lines.append(f"- `{key}`: error — {e}")
        return "Tags updated:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error updating tags: {e}"


@mcp.tool(description=(
    "Rename a tag on every item that carries it. If an item already has the new tag, "
    "the two are merged (no duplicate)."
))
def rename_tag(old_tag: str, new_tag: str) -> str:
    try:
        old_tag, new_tag = old_tag.strip(), new_tag.strip()
        if not old_tag or not new_tag or old_tag == new_tag:
            return "Give two different, non-empty tag names."
        zot = _get_client()
        items = zot.everything(zot.items(tag=old_tag))
        changed, errors = 0, []
        for item in items:
            try:
                tags = [t for t in item["data"].get("tags", []) if t.get("tag") != old_tag]
                if new_tag not in {t.get("tag") for t in tags}:
                    tags.append({"tag": new_tag})
                item["data"]["tags"] = tags
                zot.update_item(item)
                changed += 1
            except Exception as e:
                errors.append(f"`{item.get('key', '?')}`: {e}")
        msg = f"Renamed '{old_tag}' → '{new_tag}' on {changed} of {len(items)} items."
        return msg + ("\nErrors:\n" + "\n".join(errors) if errors else "")
    except Exception as e:
        return f"Error renaming tag '{old_tag}': {e}"


@mcp.tool(description=(
    "Delete tags from the whole library: each tag is removed from every item that has it. "
    "The items themselves are not deleted. tags is a comma-separated string (up to 50)."
))
def delete_tags(tags: str) -> str:
    try:
        names = _split(tags)
        if not names:
            return "No tags given."
        zot = _get_client()
        zot.delete_tags(*names)
        return f"Deleted {len(names)} tag(s) from the library: {', '.join(names)}"
    except Exception as e:
        return f"Error deleting tags: {e}"


# ---------------------------------------------------------------------------
# Collection editing tools
# ---------------------------------------------------------------------------

@mcp.tool(description=(
    "Create a collection. Pass parent_key to make it a subcollection of an existing collection."
))
def create_collection(name: str, parent_key: Optional[str] = None) -> str:
    try:
        zot = _get_client()
        payload = {"name": name.strip()}
        if parent_key:
            payload["parentCollection"] = parent_key.strip()
        result = zot.create_collections([payload])
        if result and result.get("successful"):
            created = list(result["successful"].values())[0]
            key = created.get("key") or created.get("data", {}).get("key", "")
            return f"Collection '{name}' created (key: `{key}`)."
        return f"Collection creation returned: {json.dumps(result)}"
    except Exception as e:
        return f"Error creating collection '{name}': {e}"


@mcp.tool(description=(
    "Rename and/or move a collection. new_name renames it; new_parent_key moves it under "
    "another collection, or pass new_parent_key='top' to move it to the top level."
))
def update_collection(
    collection_key: str,
    new_name: Optional[str] = None,
    new_parent_key: Optional[str] = None,
) -> str:
    try:
        if not new_name and not new_parent_key:
            return "Nothing to do: give new_name and/or new_parent_key."
        zot = _get_client()
        col = zot.collection(collection_key)
        if new_name:
            col["data"]["name"] = new_name.strip()
        if new_parent_key:
            parent = new_parent_key.strip()
            col["data"]["parentCollection"] = False if parent.lower() == "top" else parent
        zot.update_collection(col)
        return f"Collection `{collection_key}` updated: name '{col['data']['name']}', parent {col['data'].get('parentCollection') or 'top level'}."
    except Exception as e:
        return f"Error updating collection '{collection_key}': {e}"


@mcp.tool(description=(
    "Delete a collection. Its items stay in the library (and in any other collections); "
    "only the collection is removed. Subcollections are deleted with it."
))
def delete_collection(collection_key: str) -> str:
    try:
        zot = _get_client()
        col = zot.collection(collection_key)
        zot.delete_collection(col)
        return f"Collection '{col['data'].get('name', collection_key)}' (`{collection_key}`) deleted."
    except Exception as e:
        return f"Error deleting collection '{collection_key}': {e}"


def _change_membership(collection_key: str, item_keys: str, adding: bool) -> str:
    keys = _split(item_keys)
    if not keys:
        return "No item keys given."
    zot = _get_client()
    lines = []
    for key in keys:
        try:
            item = zot.item(key)
            current = item["data"].get("collections", [])
            if adding and collection_key in current:
                lines.append(f"- `{key}`: already in collection")
            elif not adding and collection_key not in current:
                lines.append(f"- `{key}`: not in collection")
            elif adding:
                zot.addto_collection(collection_key, item)
                lines.append(f"- `{key}`: added")
            else:
                zot.deletefrom_collection(collection_key, item)
                lines.append(f"- `{key}`: removed")
        except Exception as e:
            lines.append(f"- `{key}`: error — {e}")
    return f"Collection `{collection_key}`:\n" + "\n".join(lines)


@mcp.tool(description=(
    "Add one or more items to a collection. item_keys is a comma-separated string. "
    "Items keep their other collections."
))
def add_to_collection(collection_key: str, item_keys: str) -> str:
    try:
        return _change_membership(collection_key, item_keys, adding=True)
    except Exception as e:
        return f"Error adding to collection '{collection_key}': {e}"


@mcp.tool(description=(
    "Remove one or more items from a collection. The items stay in the library and in any "
    "other collections. item_keys is a comma-separated string."
))
def remove_from_collection(collection_key: str, item_keys: str) -> str:
    try:
        return _change_membership(collection_key, item_keys, adding=False)
    except Exception as e:
        return f"Error removing from collection '{collection_key}': {e}"


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

class BearerAuthMiddleware:
    """Reject any HTTP request whose Authorization header is not 'Bearer <MCP_AUTH_TOKEN>'."""

    def __init__(self, app, token: str):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            supplied = dict(scope.get("headers", [])).get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                response = JSONResponse({"error": "unauthorized"}, status_code=401)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"

    token = os.environ.get("MCP_AUTH_TOKEN", "")
    allow_no_auth = os.environ.get("MCP_ALLOW_NO_AUTH", "false").lower() == "true"
    if not token and not allow_no_auth:
        sys.exit(
            "MCP_AUTH_TOKEN is not set. Set it to a long random string, or set "
            "MCP_ALLOW_NO_AUTH=true to run without authentication (local testing only)."
        )

    print(f"Starting Zotero MCP server on {host}:{port}")
    print(f"  Library ID:   {os.environ.get('ZOTERO_LIBRARY_ID', 'not set')}")
    print(f"  Library type: {os.environ.get('ZOTERO_LIBRARY_TYPE', 'user')}")
    print(f"  Local mode:   {os.environ.get('ZOTERO_LOCAL', 'false')}")
    print(f"  Auth:         {'bearer token required' if token else 'NONE (MCP_ALLOW_NO_AUTH=true)'}")

    mcp.run(
        transport="http",
        host=host,
        port=port,
        stateless_http=True,
        middleware=[Middleware(BearerAuthMiddleware, token=token)] if token else [],
    )
