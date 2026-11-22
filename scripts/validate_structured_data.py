#!/usr/bin/env python3
"""Validate the Apps homepage's JSON-LD identity and application graph."""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"
PERSON_ID = "https://danielberanek.cz/#person"
PROFILE_ID = "https://danielberanek.cz/od-pultu-az-k-seo-a-copy-s-ostrymi-hroty-profesni-bio/#profilepage"
WEBSITE_ID = "https://apps.danielberanek.cz/#website"
PAGE_ID = "https://apps.danielberanek.cz/#webpage"
PLANNER_ID = "https://apps.danielberanek.cz/agentic-entity-resolution-guardrail-planner/#software"
PLANNER_PAGE_ID = "https://apps.danielberanek.cz/agentic-entity-resolution-guardrail-planner/#webpage"
MCP_API_ID = "https://mcp.danielberanek.cz/#webapi"
MCP_PAGE_ID = "https://mcp.danielberanek.cz/#webpage"

html = HTML.read_text(encoding="utf-8")
match = re.search(r'<script type="application/ld\+json">([\s\S]*?)</script>', html)
if not match:
    raise SystemExit("Missing homepage JSON-LD.")
data = json.loads(match.group(1))
if data.get("@context") != "https://schema.org":
    raise SystemExit("Unexpected JSON-LD context.")
graph = data.get("@graph")
if not isinstance(graph, list):
    raise SystemExit("Expected an @graph array.")
nodes = {node.get("@id"): node for node in graph if isinstance(node, dict) and node.get("@id")}
if len(nodes) != len(graph):
    raise SystemExit("Every graph node must have a unique, non-empty @id.")
required = {PERSON_ID, WEBSITE_ID, PAGE_ID, "https://apps.danielberanek.cz/#applications", PLANNER_ID, MCP_API_ID}
missing = required - set(nodes)
if missing:
    raise SystemExit("Missing graph nodes: " + ", ".join(sorted(missing)))
person = nodes[PERSON_ID]
if person.get("@type") != "Person" or person.get("mainEntityOfPage", {}).get("@id") != PROFILE_ID:
    raise SystemExit("Person must resolve to the canonical WordPress ProfilePage.")
if person.get("url") != PROFILE_ID.rsplit("#", 1)[0] + "/":
    raise SystemExit("Person.url must be the canonical professional biography URL.")
page = nodes[PAGE_ID]
if page.get("@type") != "CollectionPage" or page.get("isPartOf", {}).get("@id") != WEBSITE_ID:
    raise SystemExit("Apps homepage must be a CollectionPage within the Apps WebSite.")
if page.get("mainEntity", {}).get("@id") != "https://apps.danielberanek.cz/#applications":
    raise SystemExit("Apps CollectionPage must identify its ItemList as mainEntity.")
items = nodes["https://apps.danielberanek.cz/#applications"].get("itemListElement", [])
item_ids = [item.get("item", {}).get("@id") for item in items]
if item_ids != [PLANNER_ID, MCP_API_ID]:
    raise SystemExit("Apps ItemList must point to the canonical Planner and MCP entities.")
if nodes[PLANNER_ID].get("mainEntityOfPage", {}).get("@id") != PLANNER_PAGE_ID:
    raise SystemExit("Planner software must point to its canonical product page.")
if nodes[MCP_API_ID].get("mainEntityOfPage", {}).get("@id") != MCP_PAGE_ID:
    raise SystemExit("MCP WebAPI must point to its canonical service page.")
if nodes[PLANNER_ID].get("creator", {}).get("@id") != PERSON_ID or nodes[MCP_API_ID].get("provider", {}).get("@id") != PERSON_ID:
    raise SystemExit("Project creator/provider relationships must reference the canonical Person.")
for node in graph:
    if node.get("@type") == "LocalBusiness" or any(key in node for key in ("address", "geo", "openingHours", "areaServed", "makesOffer")):
        raise SystemExit("Local business details must not leak into the Apps subdomain graph.")
print("Apps homepage JSON-LD graph is valid: canonical Person, CollectionPage, ItemList, Planner and MCP WebAPI.")
