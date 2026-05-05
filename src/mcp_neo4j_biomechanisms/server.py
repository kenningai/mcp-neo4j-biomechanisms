import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Literal

from neo4j import AsyncGraphDatabase, Query, RoutingControl
from pydantic import Field
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from fastmcp.server import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.base import ToolResult
from mcp.types import TextContent, ToolAnnotations
from neo4j.exceptions import Neo4jError

from .biomechanisms import (
    Neo4jBiomechanisms,
    NodeType,
    RelationType,
    NODE_SCHEMAS,
    RELATION_SCHEMAS,
    EFFECT_VALUES,
    SEVERITY_VALUES,
    LAYER_VALUES,
)
from .utils import format_namespace, _is_write_query, _value_sanitize

logger = logging.getLogger("mcp_neo4j_biomechanisms")
logger.setLevel(logging.INFO)


# -- Tool Helpers -------------------------------------------------------------

@asynccontextmanager
async def _tool_errors(operation: str):
    """Standard error handling for all MCP tools."""
    logger.info(f"MCP tool: {operation}")
    try:
        yield
    except ValueError as e:
        raise ToolError(str(e))
    except Neo4jError as e:
        logger.error(f"Neo4j error in {operation}: {e}")
        raise ToolError(f"Neo4j error in {operation}: {e}")
    except Exception as e:
        logger.error(f"Error in {operation}: {e}")
        raise ToolError(f"Error in {operation}: {e}")


def _json_result(data, structured=None) -> ToolResult:
    """Wrap JSON-serializable data in a ToolResult."""
    text = json.dumps(data, indent=2, default=str)
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=structured if structured is not None else {"result": json.loads(text)},
    )


def _text_result(text: str, structured=None) -> ToolResult:
    """Wrap a text string in a ToolResult."""
    return ToolResult(
        content=[TextContent(type="text", text=text)],
        structured_content=structured if structured is not None else {"result": text},
    )


# -- Server Factory -----------------------------------------------------------

def create_mcp_server(
    bio: Neo4jBiomechanisms,
    namespace: str = "",
    read_timeout: int = 30,
) -> FastMCP:
    """Create an MCP server instance for the biomechanisms knowledge graph."""

    ns = format_namespace(namespace)
    mcp: FastMCP = FastMCP("mcp-neo4j-biomechanisms")

    # -- Entity Tools ---------------------------------------------------------

    @mcp.tool(
        name=ns + "create_entities",
        annotations=ToolAnnotations(
            title="Create Entities", readOnlyHint=False,
            destructiveHint=False, idempotentHint=True, openWorldHint=True,
        ),
    )
    async def create_entities(
        entities: list[dict[str, Any]] = Field(
            ...,
            description=(
                "List of entities to create. Each must have 'type' (one of: "
                "NeuralStructure, EdgeConfiguration, ManifoldDimension, Patient, "
                "FalsificationCondition, TheoreticalPrinciple, EmpiricalEvidence, Study) "
                "plus required properties for that type. Common required: name, description. "
                "Study requires: name, year, t_valid. Patient requires: name, condition. "
                "EmpiricalEvidence requires: name, description, t_valid. "
                "ManifoldDimension requires: name, description, layer (data/envisioning/affective). "
                "Use list_node_types to see all schemas."
            ),
        ),
    ) -> ToolResult:
        """Create nodes in the biomechanisms knowledge graph.

        Validates type enum, required properties per type, and property constraints.
        No 'type' property stored on nodes — the Neo4j label IS the type.
        t_created is auto-set. Idempotent via MERGE on name.

        Example:
        {
            "entities": [
                {"type": "NeuralStructure", "name": "Hippocampus",
                 "description": "Critical for episodic memory formation",
                 "laterality": "bilateral"},
                {"type": "Patient", "name": "Patient SM",
                 "condition": "Bilateral amygdala calcification (Urbach-Wiethe)"}
            ]
        }
        """
        async with _tool_errors("create_entities"):
            result = await bio.create_entities(entities)
            return _json_result(result)

    @mcp.tool(
        name=ns + "delete_entities",
        annotations=ToolAnnotations(
            title="Delete Entities", readOnlyHint=False,
            destructiveHint=True, idempotentHint=False, openWorldHint=True,
        ),
    )
    async def delete_entities(
        names: list[str] = Field(
            ...,
            description="Exact names of entities to delete. DETACH DELETE — removes node and all relationships.",
        ),
    ) -> ToolResult:
        """Delete nodes by exact name. Destructive and irreversible.

        Returns what was deleted (name, type, description, relationship count)
        before deletion occurs, so the operation is auditable.

        Example: {"names": ["Obsolete Structure Name"]}
        """
        async with _tool_errors("delete_entities"):
            result = await bio.delete_entities(names)
            return _json_result(result)

    # -- Relation Tools -------------------------------------------------------

    @mcp.tool(
        name=ns + "create_relations",
        annotations=ToolAnnotations(
            title="Create Relations", readOnlyHint=False,
            destructiveHint=False, idempotentHint=True, openWorldHint=True,
        ),
    )
    async def create_relations(
        relations: list[dict[str, Any]] = Field(
            ...,
            description=(
                "List of relations. Each must have 'source' (name), 'target' (name), "
                "'type' (one of: CONNECTS_TO, PARTICIPATES_IN, GENERATES, DECOMPOSES_INTO, "
                "COMPOSES_INTO, DEMONSTRATES, SUPPORTS, CHALLENGES, EXPLAINS, WOULD_FALSIFY, "
                "STUDIED_IN, REPORTED_IN), and optional 'properties' dict. "
                "DEMONSTRATES requires {effect: collapse|preservation|severing|rerouting|gain_change}. "
                "WOULD_FALSIFY requires {severity: falsify|invalidate|constrain|weaken}. "
                "Direction is enforced: e.g. PARTICIPATES_IN must be NeuralStructure -> EdgeConfiguration. "
                "Use list_relation_types to see all constraints."
            ),
        ),
    ) -> ToolResult:
        """Create relationships with full schema validation.

        Enforces direction constraints (e.g. PARTICIPATES_IN: NeuralStructure -> EdgeConfiguration),
        required properties (e.g. DEMONSTRATES requires 'effect'), and property enum values.
        t_created auto-set. Idempotent via MERGE.

        Example:
        {
            "relations": [
                {"source": "Hippocampus", "target": "Entorhinal-Hippocampal Gateway Circuit",
                 "type": "PARTICIPATES_IN"},
                {"source": "Patient SM", "target": "Fear Valence",
                 "type": "DEMONSTRATES", "properties": {"effect": "collapse"}}
            ]
        }
        """
        async with _tool_errors("create_relations"):
            result = await bio.create_relations(relations)
            return _json_result(result)

    @mcp.tool(
        name=ns + "delete_relations",
        annotations=ToolAnnotations(
            title="Delete Relations", readOnlyHint=False,
            destructiveHint=True, idempotentHint=False, openWorldHint=True,
        ),
    )
    async def delete_relations(
        relations: list[dict[str, Any]] = Field(
            ...,
            description="List of relations to delete. Each must have 'source', 'target', and 'type'.",
        ),
    ) -> ToolResult:
        """Delete specific relationships by source, target, and type.

        Example: {"relations": [{"source": "A", "target": "B", "type": "CONNECTS_TO"}]}
        """
        async with _tool_errors("delete_relations"):
            result = await bio.delete_relations(relations)
            return _json_result(result)

    # -- Query Tools ----------------------------------------------------------

    @mcp.tool(
        name=ns + "search",
        annotations=ToolAnnotations(
            title="Search", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=True,
        ),
    )
    async def search(
        query: str = Field(..., description="Fulltext search query across all node types"),
        limit: int = Field(default=10, description="Max results (default 10, max 50)", ge=1, le=50),
    ) -> ToolResult:
        """Fulltext search across all node types on name and description.

        Example: {"query": "amygdala fear", "limit": 20}
        """
        async with _tool_errors("search"):
            result = await bio.search(query=query, limit=limit)
            return _json_result(result)

    @mcp.tool(
        name=ns + "find_by_name",
        annotations=ToolAnnotations(
            title="Find By Name", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=True,
        ),
    )
    async def find_by_name(
        names: list[str] = Field(..., description="Exact entity names to look up"),
        limit: int = Field(default=20, description="Max results (default 20, max 50)", ge=1, le=50),
    ) -> ToolResult:
        """Exact name lookup with relationships between found nodes.

        Example: {"names": ["Hippocampus", "Patient SM", "Fear Valence"]}
        """
        async with _tool_errors("find_by_name"):
            result = await bio.find_by_name(names=names, limit=limit)
            return _json_result(result)

    # -- Taxonomy Tools -------------------------------------------------------

    @mcp.tool(
        name=ns + "list_node_types",
        annotations=ToolAnnotations(
            title="List Node Types", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def list_node_types() -> ToolResult:
        """List all node types with their required and optional properties.

        Use this to understand what properties each entity type expects.
        """
        async with _tool_errors("list_node_types"):
            types = {}
            for nt in NodeType:
                schema = NODE_SCHEMAS[nt.value]
                types[nt.value] = {
                    "required": list(schema["required"].keys()),
                    "optional": list(schema.get("optional", {}).keys()),
                }
                if "validators" in schema:
                    types[nt.value]["constrained_values"] = {
                        k: str(v) for k, v in schema["validators"].items()
                    }
            return _json_result(types)

    @mcp.tool(
        name=ns + "list_relation_types",
        annotations=ToolAnnotations(
            title="List Relation Types", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def list_relation_types() -> ToolResult:
        """List all relation types with direction constraints, properties, and enum values.

        Use this to understand what relationships are valid and their requirements.
        """
        async with _tool_errors("list_relation_types"):
            types = {}
            for rt in RelationType:
                schema = RELATION_SCHEMAS[rt.value]
                info: dict[str, Any] = {
                    "source_types": sorted(schema["source_types"]) if schema.get("source_types") else "any",
                    "target_types": sorted(schema["target_types"]) if schema.get("target_types") else "any",
                }
                if schema.get("properties"):
                    info["properties"] = list(schema["properties"].keys())
                if schema.get("required_properties"):
                    info["required_properties"] = list(schema["required_properties"])
                if schema.get("validators"):
                    info["constrained_values"] = {}
                    if "effect" in schema.get("validators", {}):
                        info["constrained_values"]["effect"] = sorted(EFFECT_VALUES)
                    if "severity" in schema.get("validators", {}):
                        info["constrained_values"]["severity"] = sorted(SEVERITY_VALUES)
                    if "directionality" in schema.get("validators", {}):
                        info["constrained_values"]["directionality"] = ["bidirectional", "unidirectional"]
                types[rt.value] = info
            return _json_result(types)

    # -- Schema Tool ----------------------------------------------------------

    @mcp.tool(
        name=ns + "get_schema",
        annotations=ToolAnnotations(
            title="Get Schema", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def get_schema() -> ToolResult:
        """Get the current graph schema via APOC meta introspection.

        Returns nodes, properties, and relationships as they exist in the database.
        """
        async with _tool_errors("get_schema"):
            result = await bio.driver.execute_query(
                Query(
                    "CALL apoc.meta.schema({sample: 1000}) YIELD value RETURN value",
                    timeout=read_timeout,
                ),
                routing_=RoutingControl.READ,
            )
            if result.records:
                schema = _value_sanitize(result.records[0]["value"])
                text = json.dumps(schema, indent=2, default=str)
                if len(text) > 200_000:
                    text = text[:200_000] + "\n... (truncated)"
                return _text_result(text)
            return _text_result("{}")

    # -- Cypher Tool ----------------------------------------------------------

    @mcp.tool(
        name=ns + "read_cypher",
        annotations=ToolAnnotations(
            title="Read Cypher", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=True,
        ),
    )
    async def read_cypher(
        query: str = Field(..., description="The Cypher query to execute."),
        params: dict[str, Any] = Field(default_factory=dict, description="Parameters for the query."),
    ) -> ToolResult:
        """Execute a read-only Cypher query. Write queries are rejected."""
        async with _tool_errors("read_cypher"):
            if await _is_write_query(query, bio.driver):
                raise ToolError(
                    "Write queries are not allowed via read_cypher. "
                    "Use the bounded mutation tools instead."
                )
            result = await bio.driver.execute_query(
                Query(query, timeout=read_timeout),
                parameters_=params,
                routing_=RoutingControl.READ,
            )
            records = [r for r in (_value_sanitize(dict(r)) for r in result.records) if r is not None]
            text = json.dumps(records, indent=2, default=str)
            if len(text) > 200_000:
                text = text[:200_000] + "\n... (truncated — add LIMIT to your query)"
            return _text_result(text, structured={"result": records})

    # -- GDS Analytics Tools --------------------------------------------------

    @mcp.tool(
        name=ns + "gds_create_projection",
        annotations=ToolAnnotations(
            title="GDS Create Projection", readOnlyHint=False,
            destructiveHint=False, idempotentHint=False, openWorldHint=False,
        ),
    )
    async def gds_create_projection(
        name: str = Field(..., description="Name for the graph projection"),
        node_types: list[str] | None = Field(
            default=None,
            description="Node types to include (defaults to all). Filter to specific types for focused analysis.",
        ),
        rel_types: list[str] | None = Field(
            default=None,
            description="Relationship types to include (defaults to all)",
        ),
        undirected: bool = Field(default=True, description="Treat relationships as undirected (default true)"),
    ) -> ToolResult:
        """Create a GDS graph projection for analytics.

        Projects the biomechanisms graph into GDS memory for PageRank,
        Betweenness, Louvain, and WCC analysis. Always clean up with
        gds_drop_projection when done.

        Example: {"name": "bio_full"}
        Example: {"name": "circuits_only", "node_types": ["NeuralStructure", "EdgeConfiguration"]}
        """
        async with _tool_errors("gds_create_projection"):
            if rel_types:
                rel_filter = "|".join(f"`{rt}`" for rt in rel_types)
                match_clause = f"MATCH (source)-[r:{rel_filter}]->(target)"
            else:
                match_clause = "MATCH (source)-[r]->(target)"

            where_parts = []
            if node_types:
                source_labels = " OR ".join(f"source:`{nt}`" for nt in node_types)
                target_labels = " OR ".join(f"target:`{nt}`" for nt in node_types)
                where_parts.append(f"({source_labels})")
                where_parts.append(f"({target_labels})")

            where_clause = ""
            if where_parts:
                where_clause = "WHERE " + " AND ".join(where_parts)

            config_parts = []
            if undirected:
                config_parts.append("undirectedRelationshipTypes: ['*']")
            config_map = "{" + ", ".join(config_parts) + "}" if config_parts else "{}"

            query = f"""
                {match_clause}
                {where_clause}
                RETURN gds.graph.project($name, source, target, {{}}, {config_map})
            """

            result = await bio.driver.execute_query(
                query, parameters_={"name": name}, routing_=RoutingControl.READ,
            )
            records = [r for r in (_value_sanitize(dict(r)) for r in result.records) if r is not None]
            return _json_result(records)

    @mcp.tool(
        name=ns + "gds_drop_projection",
        annotations=ToolAnnotations(
            title="GDS Drop Projection", readOnlyHint=False,
            destructiveHint=True, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def gds_drop_projection(
        name: str = Field(..., description="Name of the graph projection to drop"),
    ) -> ToolResult:
        """Drop a GDS graph projection to free memory. Always clean up after analysis."""
        async with _tool_errors("gds_drop_projection"):
            result = await bio.driver.execute_query(
                "CALL gds.graph.drop($name)",
                name=name,
                routing_=RoutingControl.WRITE,
            )
            return _json_result([dict(r) for r in result.records])

    @mcp.tool(
        name=ns + "gds_pagerank",
        annotations=ToolAnnotations(
            title="GDS PageRank", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def gds_pagerank(
        projection: str = Field(..., description="Name of the graph projection"),
        result_limit: int = Field(default=20, ge=1, le=1000, description="Max results (default 20)"),
    ) -> ToolResult:
        """Run PageRank — what matters most? Structural centrality across the graph."""
        async with _tool_errors("gds_pagerank"):
            result = await bio.driver.execute_query(
                "CALL gds.pageRank.stream($projection) YIELD nodeId, score "
                "RETURN gds.util.asNode(nodeId).name AS node, "
                "labels(gds.util.asNode(nodeId))[0] AS type, score "
                "ORDER BY score DESC LIMIT $result_limit",
                projection=projection, result_limit=result_limit,
                routing_=RoutingControl.READ,
            )
            return _json_result([dict(r) for r in result.records])

    @mcp.tool(
        name=ns + "gds_betweenness",
        annotations=ToolAnnotations(
            title="GDS Betweenness Centrality", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def gds_betweenness(
        projection: str = Field(..., description="Name of the graph projection"),
        result_limit: int = Field(default=20, ge=1, le=1000, description="Max results (default 20)"),
    ) -> ToolResult:
        """Run Betweenness Centrality — what bridges? Shortest-path integration points."""
        async with _tool_errors("gds_betweenness"):
            result = await bio.driver.execute_query(
                "CALL gds.betweenness.stream($projection) YIELD nodeId, score "
                "RETURN gds.util.asNode(nodeId).name AS node, "
                "labels(gds.util.asNode(nodeId))[0] AS type, score "
                "ORDER BY score DESC LIMIT $result_limit",
                projection=projection, result_limit=result_limit,
                routing_=RoutingControl.READ,
            )
            return _json_result([dict(r) for r in result.records])

    @mcp.tool(
        name=ns + "gds_louvain",
        annotations=ToolAnnotations(
            title="GDS Louvain", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def gds_louvain(
        projection: str = Field(..., description="Name of the graph projection"),
        result_limit: int = Field(default=20, ge=1, le=1000, description="Max results (default 20)"),
    ) -> ToolResult:
        """Run Louvain community detection — how does the graph cluster?"""
        async with _tool_errors("gds_louvain"):
            result = await bio.driver.execute_query(
                "CALL gds.louvain.stream($projection) YIELD nodeId, communityId "
                "RETURN gds.util.asNode(nodeId).name AS node, "
                "labels(gds.util.asNode(nodeId))[0] AS type, communityId "
                "ORDER BY communityId, node LIMIT $result_limit",
                projection=projection, result_limit=result_limit,
                routing_=RoutingControl.READ,
            )
            return _json_result([dict(r) for r in result.records])

    @mcp.tool(
        name=ns + "gds_wcc",
        annotations=ToolAnnotations(
            title="GDS Weakly Connected Components", readOnlyHint=True,
            destructiveHint=False, idempotentHint=True, openWorldHint=False,
        ),
    )
    async def gds_wcc(
        projection: str = Field(..., description="Name of the graph projection"),
        result_limit: int = Field(default=20, ge=1, le=1000, description="Max results (default 20)"),
    ) -> ToolResult:
        """Run WCC — are there disconnected islands in the graph?"""
        async with _tool_errors("gds_wcc"):
            result = await bio.driver.execute_query(
                "CALL gds.wcc.stream($projection) YIELD nodeId, componentId "
                "RETURN gds.util.asNode(nodeId).name AS node, "
                "labels(gds.util.asNode(nodeId))[0] AS type, componentId "
                "ORDER BY componentId, node LIMIT $result_limit",
                projection=projection, result_limit=result_limit,
                routing_=RoutingControl.READ,
            )
            return _json_result([dict(r) for r in result.records])

    return mcp


# -- Server Entry Point -------------------------------------------------------

async def main(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str,
    transport: Literal["stdio", "sse", "http", "streamable-http"] = "stdio",
    namespace: str = "",
    host: str = "127.0.0.1",
    port: int = 8000,
    path: str = "/mcp/",
    allow_origins: list[str] = [],
    allowed_hosts: list[str] = [],
    read_timeout: int = 30,
) -> None:
    logger.info("Starting Biomechanisms MCP Server")
    logger.info(f"Connecting to Neo4j at: {neo4j_uri}")

    neo4j_driver = AsyncGraphDatabase.driver(
        neo4j_uri, auth=(neo4j_user, neo4j_password), database=neo4j_database,
    )

    try:
        await neo4j_driver.verify_connectivity()
        logger.info(f"Connected to Neo4j at {neo4j_uri}")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        exit(1)

    bio = Neo4jBiomechanisms(neo4j_driver)
    await bio.create_fulltext_index()

    custom_middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        ),
        Middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts),
    ]

    mcp = create_mcp_server(bio, namespace, read_timeout=read_timeout)

    match transport:
        case "streamable-http" | "http":
            await mcp.run_http_async(
                host=host, port=port, path=path,
                middleware=custom_middleware,
                transport="streamable-http",
                stateless_http=True,
            )
        case "stdio":
            await mcp.run_stdio_async()
        case "sse":
            await mcp.run_http_async(
                host=host, port=port, path=path,
                middleware=custom_middleware,
                transport="sse",
            )
        case _:
            raise ValueError(
                f"Unsupported transport: {transport}. "
                "Must be one of: stdio, sse, http, streamable-http"
            )
