# mcp-neo4j-biomechanisms

A schema-bounded MCP server for empirical neuroscience knowledge graphs in Neo4j.

The graph maps what peer-reviewed empirical neuroscience has measured about the biological substrate of consciousness — neural structures, circuits, manifold dimensions, lesion patients, falsification conditions, theoretical principles, evidence, studies. Every mutation goes through a tool that validates type, properties, and direction against a registry; there is no raw write-Cypher path. GDS analytics (PageRank, Betweenness, Louvain, WCC) are first-class, because the structure of the connected evidence reveals patterns no individual paper does.

## Install

```bash
uv sync --dev
```

Requires Python ≥3.10, Neo4j ≥5.26 with the APOC and GDS plugins enabled, and a fulltext-capable database.

## Run

```bash
# stdio (default; for Claude Desktop and similar)
uv run mcp-neo4j-biomechanisms --db-url bolt://localhost:7687

# streamable HTTP
uv run mcp-neo4j-biomechanisms \
  --transport http --server-host 0.0.0.0 --server-port 8000 --server-path /mcp/
```

All flags have environment-variable equivalents. CLI > env > default.

| Flag                  | Env var                            | Default                  |
| --------------------- | ---------------------------------- | ------------------------ |
| `--db-url`            | `NEO4J_URL` / `NEO4J_URI`          | `bolt://localhost:7687`  |
| `--username`          | `NEO4J_USERNAME`                   | `neo4j`                  |
| `--password`          | `NEO4J_PASSWORD`                   | `password`               |
| `--database`          | `NEO4J_DATABASE`                   | `neo4j`                  |
| `--transport`         | `NEO4J_TRANSPORT`                  | `stdio`                  |
| `--namespace`         | `NEO4J_NAMESPACE`                  | (none)                   |
| `--server-host`       | `NEO4J_MCP_SERVER_HOST`            | `127.0.0.1`              |
| `--server-port`       | `NEO4J_MCP_SERVER_PORT`            | `8000`                   |
| `--server-path`       | `NEO4J_MCP_SERVER_PATH`            | `/mcp/`                  |
| `--allow-origins`     | `NEO4J_MCP_SERVER_ALLOW_ORIGINS`   | (empty — secure default) |
| `--allowed-hosts`     | `NEO4J_MCP_SERVER_ALLOWED_HOSTS`   | `localhost,127.0.0.1`    |
| `--read-timeout`      | `NEO4J_READ_TIMEOUT`               | `30`                     |

Transports: `stdio`, `http` (alias: `streamable-http`), `sse`.

### Docker

```bash
docker compose up
```

The provided `compose.yml` runs the server in `http` mode on `:8002` and connects to a Neo4j on the host (`bolt://host.docker.internal:7687`). Set `NEO4J_BIOMECHANISMS_PASSWORD` in the environment.

## Tools

| Tool                    | Purpose                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `create_entities`       | Create nodes; type + properties validated against `NODE_SCHEMAS`.        |
| `delete_entities`       | `DETACH DELETE` by exact name; returns relationship count before delete. |
| `create_relations`      | Create relationships; direction + properties validated.                  |
| `delete_relations`      | Delete by `(source, target, type)`.                                      |
| `search`                | Fulltext search across all node types on `name` and `description`.       |
| `find_by_name`          | Exact-name lookup with relationships between found nodes.                |
| `list_node_types`       | Introspect schemas for every node type.                                  |
| `list_relation_types`   | Introspect direction constraints, properties, and enum values.           |
| `get_schema`            | Live `apoc.meta.schema` introspection of the database.                   |
| `read_cypher`           | Read-only Cypher; write intent rejected via `EXPLAIN` query-type check.  |
| `gds_create_projection` | Project subgraph into the GDS catalog (filterable by node + rel types).  |
| `gds_drop_projection`   | Drop a projection. Always run after analysis.                            |
| `gds_pagerank`          | Centrality — what is structurally most central?                          |
| `gds_betweenness`       | Bridges — which nodes integrate otherwise separate regions?              |
| `gds_louvain`           | Communities — how does the evidence naturally cluster?                   |
| `gds_wcc`               | Weakly connected components — are there disconnected islands?            |

A `--namespace foo` flag prefixes every tool with `foo-`, useful when running multiple servers in one MCP client.

## Ontology

**8 node types.** `NeuralStructure`, `EdgeConfiguration`, `ManifoldDimension`, `Patient`, `FalsificationCondition`, `TheoreticalPrinciple`, `EmpiricalEvidence`, `Study`.

**12 relationship types**, in four categories with enforced direction:

- *Structural* — `CONNECTS_TO`, `PARTICIPATES_IN` (`NeuralStructure→EdgeConfiguration`), `GENERATES` (`EdgeConfiguration→ManifoldDimension`), `DECOMPOSES_INTO`, `COMPOSES_INTO`
- *Evidential* — `DEMONSTRATES` (`Patient→{ManifoldDimension,EdgeConfiguration}` with `effect` enum), `SUPPORTS`, `CHALLENGES`
- *Theoretical* — `EXPLAINS` (`TheoreticalPrinciple→…`), `WOULD_FALSIFY` (with `severity` enum)
- *Provenance* — `STUDIED_IN` (`Patient→Study`), `REPORTED_IN` (`EmpiricalEvidence→Study`)

Property enums are enforced server-side: `effect ∈ {collapse, preservation, severing, rerouting, gain_change}`, `severity ∈ {falsify, invalidate, constrain, weaken}`, `layer ∈ {data, envisioning, affective}`. Every node carries an auto-set `t_created`; empirical claims carry `t_valid` for when the finding was true in the world (independent of when the graph learned it).

Use `list_node_types` and `list_relation_types` for the live, complete schema — those tools introspect the registry, so there is no separate documentation to drift.

## GDS workflow

```text
gds_create_projection {"name": "bio_full"}
gds_pagerank          {"projection": "bio_full"}
gds_betweenness       {"projection": "bio_full"}
gds_louvain           {"projection": "bio_full"}
gds_drop_projection   {"name": "bio_full"}
```

Projections survive across tool calls within a session; always drop them when done. Use `node_types` / `rel_types` filters on `gds_create_projection` for focused analyses (e.g. only `NeuralStructure` + `EdgeConfiguration` for circuit-level topology).

## Development

```bash
uv run pytest                # 55 unit tests, no Neo4j required
uv run pyright src           # type check
```

Validation logic lives in `biomechanisms.py` and is fully tested without a database. The async driver only enters at the `Neo4jBiomechanisms` class boundary.

## Operating the graph

`HOWTO.xml` is an LLM-facing operations manual for the entity *using* these tools — what node-type goes where, when to draw which edge, when to add a `TheoreticalPrinciple` versus extend an `EmpiricalEvidence`, why GDS is constitutive rather than decorative. Read it before populating the graph.

## License

MIT — see [LICENSE](LICENSE).
