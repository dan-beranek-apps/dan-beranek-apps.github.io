# Daniel Beránek Apps

A static directory of public applications and interfaces by Daniel Beránek.

## Agent discovery

The reviewed source of truth is `discovery/catalog-source.json`. The generated manifests are published at:

- ARD v0.91: `/.well-known/ard.json`
- Common AI Catalog v0.9: `/.well-known/ai-catalog.json`

Regenerate both files after changing the source:

```bash
python scripts/generate_agent_discovery.py --write
python scripts/generate_agent_discovery.py --check
```

The same deterministic generator is run in GitHub Actions to reject stale or invalid projections. The root `.nojekyll` marker ensures GitHub Pages publishes the hidden `.well-known` directory as static content.
