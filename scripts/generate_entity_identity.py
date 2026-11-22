#!/usr/bin/env python3
"""Project shared Apps identities from the immutable DIO/ODI Entity Registry snapshot."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "metadata" / "entity-registry.lock.json"
INDEX_PATH = ROOT / "index.html"
EXPECTED_KEYS = (
    "person-daniel-beranek",
    "software-agentic-er-guardrail-planner",
    "service-dio-odi-mcp-api",
)
ITEM_LIST_ID = "https://apps.danielberanek.cz/#applications"


def fail(message: str) -> None:
    raise SystemExit("ENTITY IDENTITY PROJECTION FAILED: " + message)


def load_registry() -> tuple[dict, dict]:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("registry_repository") != "dan-beranek/dio-odi-entity-registry":
        fail("unexpected Entity Registry repository")
    commit = lock.get("registry_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        fail("registry_commit must be a full immutable commit SHA")

    snapshot_path = ROOT / lock["snapshot_path"]
    snapshot_bytes = snapshot_path.read_bytes()
    registry = json.loads(snapshot_bytes)
    if registry.get("status") != "canonical-approved":
        fail("Entity Registry snapshot is not canonical-approved")
    if registry.get("registry_version") != lock.get("registry_version"):
        fail("Entity Registry snapshot version differs from its lock")

    source_url = (
        f"https://raw.githubusercontent.com/{lock['registry_repository']}/"
        f"{commit}/{lock['source_path']}"
    )
    request = Request(source_url, headers={"User-Agent": "Apps-Entity-Identity-Projection/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            upstream_bytes = response.read()
    except Exception as exc:
        fail(f"cannot retrieve immutable Entity Registry source: {exc}")
    if upstream_bytes != snapshot_bytes:
        fail("vendored Entity Registry snapshot differs from the immutable upstream commit")

    by_key = {entity["key"]: entity for entity in registry.get("entities", [])}
    for key in EXPECTED_KEYS:
        entity = by_key.get(key)
        if not entity or entity.get("status") != "active":
            fail(f"missing active required identity: {key}")
    return lock, by_key


def replace_jsonld(html: str, registry: dict[str, dict]) -> str:
    pattern = re.compile(r'(<script type="application/ld\+json">)([\s\S]*?)(</script>)')
    matches = list(pattern.finditer(html))
    if len(matches) != 1:
        fail(f"expected exactly one homepage JSON-LD block; found {len(matches)}")

    document = json.loads(matches[0].group(2))
    if document.get("@context") != "https://schema.org" or not isinstance(document.get("@graph"), list):
        fail("homepage JSON-LD must use Schema.org @graph")
    graph = document["@graph"]
    nodes = {node.get("@id"): node for node in graph if isinstance(node, dict) and node.get("@id")}
    if len(nodes) != len(graph):
        fail("homepage JSON-LD graph must have unique @id values")

    def project_node(key: str) -> str:
        entity = registry[key]
        entity_id = entity["@id"]
        node = nodes.get(entity_id)
        if node is None:
            fail(f"homepage graph is missing Entity Registry node {key}: {entity_id}")
        types = [value.rsplit("/", 1)[-1] for value in entity["@type"]]
        node["@type"] = types[0] if len(types) == 1 else types
        node["name"] = entity["name"]
        node["url"] = entity["url"]
        if "sameAs" in entity:
            node["sameAs"] = entity["sameAs"]
        return entity_id

    person_id = project_node("person-daniel-beranek")
    planner_id = project_node("software-agentic-er-guardrail-planner")
    api_id = project_node("service-dio-odi-mcp-api")

    if nodes[planner_id].get("creator", {}).get("@id") != person_id:
        fail("Planner creator relation must point to the canonical Person")
    if nodes[api_id].get("provider", {}).get("@id") != person_id:
        fail("MCP WebAPI provider relation must point to the canonical Person")

    item_list = nodes.get(ITEM_LIST_ID)
    if not item_list:
        fail("Apps ItemList is missing")
    list_items = item_list.get("itemListElement", [])
    if len(list_items) != 2:
        fail("Apps ItemList must retain exactly two entries")
    expected_ids = [planner_id, api_id]
    for index, expected_id in enumerate(expected_ids):
        item = list_items[index].get("item", {})
        item["@id"] = expected_id
        list_items[index]["item"] = item
    nodes[ITEM_LIST_ID] = item_list

    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    return html[:matches[0].start(2)] + rendered + html[matches[0].end(2):]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Update index.html from the pinned registry.")
    mode.add_argument("--check", action="store_true", help="Fail if index.html differs from the registry projection.")
    args = parser.parse_args()

    try:
        lock, registry = load_registry()
        original = INDEX_PATH.read_text(encoding="utf-8")
        expected = replace_jsonld(original, registry)
        if args.write:
            INDEX_PATH.write_text(expected, encoding="utf-8")
            print("Generated Apps JSON-LD from Entity Registry v" + lock["registry_version"])
            return 0
        if original != expected:
            print("Apps JSON-LD is stale. Run: python scripts/generate_entity_identity.py --write", file=sys.stderr)
            return 1
        print(
            "Apps Entity Registry projection is reproducible: "
            f"v{lock['registry_version']} at {lock['registry_commit']}."
        )
        return 0
    except Exception as exc:
        print(f"ENTITY IDENTITY PROJECTION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
