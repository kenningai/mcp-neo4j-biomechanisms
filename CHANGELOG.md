# Changelog

All notable changes to this project are documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project adheres to [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-08-27

### Added

- **MIT license.** `LICENSE` at the project root, `license = "MIT"` and `license-files = ["LICENSE"]` in `pyproject.toml` (PEP 639), and a License section in `README.md`. Built distributions now carry `License-Expression: MIT` and ship the license file in `dist-info/licenses/`. The build backend floor was raised to `hatchling>=1.27`, the first version supporting the PEP 639 fields.
- `compose.yml` gains a second service exposing the upstream `mcp/neo4j-cypher` server on `:8004` against the same Neo4j instance, and sets `NEO4J_TELEMETRY: "false"` on both services.

### Changed

- `Dockerfile` and `compose.yml` version pins move to `0.3.0` alongside the package version; the compose image name follows the repository to the `kenningai` organisation.

## [0.2.0] — 2026-05-05

### Changed

- Upgraded FastMCP from `>=2.0` to `>=3.0,<4`. The streamable-http monkey-patch in `server.py` was removed — the underlying bug it worked around (FastMCP 2.13.0.2 only allowing GET on the streamable-http route) was fixed in 2.13.1 and the HTTP app structure is different in v3. `ToolResult` import path updated from `fastmcp.tools.tool` to `fastmcp.tools.base`.
- `read_cypher` now detects write intent by running `EXPLAIN` against the Neo4j planner and inspecting `summary.query_type`, replacing the previous regex over query text. Eliminates false positives from string literals, identifiers like `creation_date`, and Cypher comments. Costs one extra round-trip per read query, which is the upstream `mcp-neo4j-cypher` v0.6.0 behavior.
- The `http` transport name is accepted as an alias for `streamable-http`, matching upstream naming. `compose.yml` updated to use `http`.

### Fixed

- `gds_create_projection` previously injected `memory: '2GB'` into the Cypher projection configuration map. `memory` is not a valid config key for `gds.graph.project()`, so every call failed with the default arguments. The `memory_gb` parameter has been removed; GDS manages its own heap at the server level.
- `create_entities` no longer wipes `description` on existing nodes when the caller doesn't provide one. The cypher template previously did an unconditional `ON MATCH SET n.description = $description` with `""` as the fallback, silently destroying data on re-create. `description` now flows through the dynamic SET block, so MERGE-on-existing only updates fields the caller actually passed.

### Removed

- `memory_gb` parameter on `gds_create_projection`.
- The `patched_create_streamable_http_app` monkey-patch in `server.py` and its FastMCP-internal imports.

## [0.1.0]

Initial release. Eight node types (`NeuralStructure`, `EdgeConfiguration`, `ManifoldDimension`, `Patient`, `FalsificationCondition`, `TheoreticalPrinciple`, `EmpiricalEvidence`, `Study`), twelve relationship types with direction constraints and property enum validation, schema-bounded mutation tools, GDS analytics (PageRank, Betweenness, Louvain, WCC), fulltext search, and read-only Cypher access.
