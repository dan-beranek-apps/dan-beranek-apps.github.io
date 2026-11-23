#!/usr/bin/env python3
"""Generate the Apps-domain ARD manifest and canonical AI Catalog pointer.

The richer Apps-specific ARD remains generated from its local reviewed source.
The AI Catalog endpoint delegates to the single canonical DIO/ODI catalog on
the Reference Model domain instead of maintaining a second artifact inventory.
Both generated files are committed for static GitHub Pages hosting.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "discovery/catalog-source.json"
ARD_OUTPUT = ROOT / ".well-known/ard.json"
AI_CATALOG_OUTPUT = ROOT / ".well-known/ai-catalog.json"

ARD_CONTEXT = "https://agenticresourcediscovery.org/context/v1"
AI_CATALOG_SPEC_VERSION = "0.9"
CANONICAL_AI_CATALOG_URL = "https://vocab.danielberanek.cz/.well-known/ai-catalog.json"
MEDIA_TYPE = re.compile(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$")


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path.relative_to(ROOT)}: {exc}") from exc


def dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def require_https(value: str, label: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be an absolute HTTPS URL: {value!r}")


def validate_source(source: dict) -> None:
    if not isinstance(source, dict) or source.get("source_version") != "0.1.0":
        raise ValueError("Unexpected discovery source; review the source schema deliberately.")

    host = source.get("host")
    if not isinstance(host, dict) or not isinstance(host.get("displayName"), str) or not host["displayName"].strip():
        raise ValueError("The catalog host requires a non-empty displayName.")
    if host.get("identifier") != "apps.danielberanek.cz":
        raise ValueError("The catalog host identifier must remain apps.danielberanek.cz.")
    require_https(host.get("documentationUrl", ""), "host.documentationUrl")

    entries = source.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("The canonical source must contain at least one entry.")

    identifiers: set[str] = set()
    for index, entry in enumerate(entries):
        label = f"entries[{index}]"
        if not isinstance(entry, dict):
            raise ValueError(f"{label} must be an object.")
        for field in ("identifier", "displayName", "type", "description", "tags", "representativeQueries"):
            if field not in entry:
                raise ValueError(f"{label} is missing {field}.")
        identifier = entry["identifier"]
        if not isinstance(identifier, str) or not identifier.startswith("urn:air:apps.danielberanek.cz:"):
            raise ValueError(f"{label}.identifier must use the Apps-domain URN namespace.")
        if identifier in identifiers:
            raise ValueError(f"Duplicate discovery identifier: {identifier}")
        identifiers.add(identifier)
        if not isinstance(entry["type"], str) or not MEDIA_TYPE.fullmatch(entry["type"]):
            raise ValueError(f"{label}.type must be a media type.")
        if ("url" in entry) == ("data" in entry):
            raise ValueError(f"{label} must contain exactly one of url or data.")
        if "url" in entry:
            require_https(entry["url"], f"{label}.url")
        queries = entry["representativeQueries"]
        if not isinstance(queries, list) or not 2 <= len(queries) <= 5:
            raise ValueError(f"{label}.representativeQueries must contain 2–5 examples.")
        if any(not isinstance(query, str) or not query.strip() for query in queries):
            raise ValueError(f"{label}.representativeQueries contains an empty value.")
        if not isinstance(entry["tags"], list) or any(not isinstance(tag, str) or not tag.strip() for tag in entry["tags"]):
            raise ValueError(f"{label}.tags must contain non-empty strings.")
        if "version" in entry and (not isinstance(entry["version"], str) or not entry["version"].strip()):
            raise ValueError(f"{label}.version must be a non-empty string when present.")


def project_ard(source: dict) -> dict:
    entries = []
    for entry in source["entries"]:
        projected = {
            "@context": ARD_CONTEXT,
            "identifier": entry["identifier"],
            "displayName": entry["displayName"],
            "type": entry["type"],
        }
        if "url" in entry:
            projected["url"] = entry["url"]
        else:
            projected["data"] = entry["data"]
        projected["description"] = entry["description"]
        if entry.get("version"):
            projected["version"] = entry["version"]
        projected["tags"] = entry["tags"]
        if entry.get("capabilities"):
            projected["capabilities"] = entry["capabilities"]
        projected["representativeQueries"] = entry["representativeQueries"]
        entries.append(projected)
    return {"entries": entries}


def project_ai_catalog(source: dict) -> dict:
    return {
        "specVersion": AI_CATALOG_SPEC_VERSION,
        "host": source["host"],
        "entries": [
            {
                "identifier": "urn:air:apps.danielberanek.cz:catalog:canonical",
                "displayName": "Canonical DIO/ODI AI Catalog",
                "type": "application/ai-catalog+json",
                "url": CANONICAL_AI_CATALOG_URL,
                "description": (
                    "Canonical catalog for the public DIO/ODI research resources, "
                    "machine-readable reference data, MCP service and Agentic "
                    "Entity Resolution Guardrail Planner."
                ),
            }
        ],
    }


def validate_ai_catalog(catalog: dict) -> None:
    if not isinstance(catalog, dict) or catalog.get("specVersion") != AI_CATALOG_SPEC_VERSION:
        raise ValueError("AI Catalog must identify the v0.9 release-candidate contract.")
    host = catalog.get("host")
    if not isinstance(host, dict) or not isinstance(host.get("displayName"), str) or not host["displayName"].strip():
        raise ValueError("AI Catalog requires host.displayName.")
    entries = catalog.get("entries")
    if not isinstance(entries, list):
        raise ValueError("AI Catalog requires an entries array.")
    if len(entries) != 1:
        raise ValueError("Apps AI Catalog must remain a single-entry pointer to the canonical catalogue.")
    pointer = entries[0]
    if pointer.get("type") != "application/ai-catalog+json" or pointer.get("url") != CANONICAL_AI_CATALOG_URL:
        raise ValueError("Apps AI Catalog must delegate to the canonical Reference Model catalogue.")
    for index, entry in enumerate(entries):
        label = f"AI Catalog entries[{index}]"
        for field in ("identifier", "type"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"{label} requires {field}.")
        if ("url" in entry) == ("data" in entry):
            raise ValueError(f"{label} must contain exactly one of url or data.")
        if "url" in entry:
            require_https(entry["url"], f"{label}.url")
        if not MEDIA_TYPE.fullmatch(entry["type"]):
            raise ValueError(f"{label}.type must be a media type.")


def expected_outputs() -> dict[Path, str]:
    source = read_json(SOURCE)
    validate_source(source)
    ard = project_ard(source)
    ai_catalog = project_ai_catalog(source)
    validate_ai_catalog(ai_catalog)
    return {
        ARD_OUTPUT: dump_json(ard),
        AI_CATALOG_OUTPUT: dump_json(ai_catalog),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write generated public manifests")
    mode.add_argument("--check", action="store_true", help="verify committed manifests are reproducible")
    args = parser.parse_args()

    try:
        outputs = expected_outputs()
        if args.write:
            for path, content in outputs.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
                print(f"WROTE {path.relative_to(ROOT)}")
        else:
            stale = [
                str(path.relative_to(ROOT))
                for path, content in outputs.items()
                if not path.is_file() or path.read_text(encoding="utf-8") != content
            ]
            if stale:
                raise ValueError("Generated manifests are stale or missing: " + ", ".join(stale))
            print("Apps ARD manifest and canonical AI Catalog pointer are reproducible and valid.")
    except Exception as exc:
        print(f"Agent discovery generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
