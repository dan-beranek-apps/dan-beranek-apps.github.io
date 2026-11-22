#!/usr/bin/env python3
"""Validate the Apps homepage graph against its local page semantics and pinned identity registry."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"
LOCK = json.loads((ROOT / "metadata/entity-registry.lock.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / LOCK["snapshot_path"]).read_text(encoding="utf-8"))

PERSON_ID = "https://danielberanek.cz/#person"
PROFILE_URL = "https://danielberanek.cz/od-pultu-az-k-seo-a-copy-s-ostrymi-hroty-profesni-bio/"
WEBSITE_ID = "https://apps.danielberanek.cz/#website"
PAGE_ID = "https://apps.danielberanek.cz/#webpage"
ITEM_LIST_ID = "https://apps.danielberanek.cz/#applications"
PLANNER_PAGE_ID = "https://apps.danielberanek.cz/agentic-entity-resolution-guardrail-planner/#webpage"
MCP_PAGE_ID = "https://mcp.danielberanek.cz/#webpage"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def entity(key: str) -> dict:
    matches = [
        item for item in REGISTRY.get("entities", [])
        if item.get("key") == key and item.get("status") == "active"
    ]
    require(len(matches) == 1, "Entity Registry must contain one active " + key + " record.")
    return matches[0]


require(REGISTRY.get("status") == "canonical-approved", "Entity Registry snapshot is not approved.")
require(REGISTRY.get("registry_version") == LOCK.get("registry_version"), "Entity Registry lock/version mismatch.")
require(LOCK.get("registry_repository") == "dan-beranek/dio-odi-entity-registry", "Unexpected Entity Registry repository.")
require(len(LOCK.get("registry_commit", "")) == 40, "Entity Registry must be pinned to an immutable commit SHA.")

person_entity = entity("person-daniel-beranek")
planner_entity = entity("software-agentic-er-guardrail-planner")
mcp_entity = entity("service-dio-odi-mcp-api")

html = HTML.read_text(encoding="utf-8")
import re
match = re.search(r'<script type="application/ld\+json">([\s\S]*?)</script>', html)
require(match is not None, "Missing homepage JSON-LD.")
data = json.loads(match.group(1))
require(data.get("@context") == "https://schema.org", "Unexpected JSON-LD context.")
graph = data.get("@graph")
require(isinstance(graph, list), "Expected an @graph array.")
nodes = {node.get("@id"): node for node in graph if isinstance(node, dict) and node.get("@id")}
require(len(nodes) == len(graph), "Every graph node must have a unique, non-empty @id.")

person_id = person_entity["@id"]
planner_id = planner_entity["@id"]
mcp_api_id = mcp_entity["@id"]
required_ids = {person_id, WEBSITE_ID, PAGE_ID, ITEM_LIST_ID, planner_id, mcp_api_id}
missing = required_ids - set(nodes)
require(not missing, "Missing graph nodes: " + ", ".join(sorted(missing)))

person = nodes[person_id]
require(person.get("@type") == "Person", "Expected the canonical Person node.")
require(person.get("name") == person_entity["name"], "Person.name differs from the Entity Registry.")
require(person.get("url") == person_entity["url"] == PROFILE_URL, "Person.url must match the canonical professional biography.")
require(person.get("sameAs") == person_entity.get("sameAs", []), "Person.sameAs differs from the Entity Registry.")

planner = nodes[planner_id]
require(planner.get("@type") == "SoftwareApplication", "Planner identity must remain a SoftwareApplication.")
require(planner.get("name") == planner_entity["name"], "Planner name differs from the Entity Registry.")
require(planner.get("url") == planner_entity["url"], "Planner URL differs from the Entity Registry.")

mcp_api = nodes[mcp_api_id]
require(mcp_api.get("@type") == "WebAPI", "MCP endpoint identity must remain a WebAPI.")
require(mcp_api.get("name") == mcp_entity["name"], "MCP API name differs from the Entity Registry.")
require(mcp_api.get("url") == mcp_entity["url"], "MCP API endpoint differs from the Entity Registry.")

page = nodes[PAGE_ID]
require(page.get("@type") == "CollectionPage" and page.get("isPartOf", {}).get("@id") == WEBSITE_ID,
        "Apps homepage must be a CollectionPage within the Apps WebSite.")
require(page.get("mainEntity", {}).get("@id") == ITEM_LIST_ID,
        "Apps CollectionPage must identify its ItemList as mainEntity.")

items = nodes[ITEM_LIST_ID].get("itemListElement", [])
item_ids = [item.get("item", {}).get("@id") for item in items]
require(item_ids == [planner_id, mcp_api_id],
        "Apps ItemList must point to the canonical Planner and MCP entities.")
require(planner.get("mainEntityOfPage", {}).get("@id") == PLANNER_PAGE_ID,
        "Planner software must point to its canonical product page.")
require(mcp_api.get("mainEntityOfPage", {}).get("@id") == MCP_PAGE_ID,
        "MCP WebAPI must point to its canonical service page.")
require(planner.get("creator", {}).get("@id") == person_id and mcp_api.get("provider", {}).get("@id") == person_id,
        "Project creator/provider relationships must reference the canonical Person.")

for node in graph:
    require(node.get("@type") != "LocalBusiness", "LocalBusiness must not leak into the Apps graph.")
    require(not any(key in node for key in ("address", "geo", "openingHours", "areaServed", "makesOffer")),
            "Local business details must not leak into the Apps subdomain graph.")

print(
    "Apps homepage JSON-LD is valid against Entity Registry "
    f"v{REGISTRY['registry_version']}: Person, Planner SoftwareApplication, MCP WebAPI, "
    "CollectionPage and ItemList."
)
