import argparse
import os
import re
import logging
from pathlib import Path
from typing import Any, Union

logger = logging.getLogger("mcp_neo4j_biomechanisms")
logger.setLevel(logging.INFO)

# -- Cypher Query Loading -----------------------------------------------------

_CYPHER_DIR = Path(__file__).parent / "_cypher"
_CYPHER_CACHE: dict[str, str] = {}


def load_cypher(name: str, **replacements: str) -> str:
    """Load a Cypher query from _cypher/{name}.cypher.

    Caches file contents on first load. Template placeholders use
    __name__ convention (e.g. __label__, __rel_type__) to avoid
    collision with Cypher's {prop: $param} syntax.

    Args:
        name: Query filename without .cypher extension
        **replacements: Template substitutions (key -> __key__ in file)
    """
    if name not in _CYPHER_CACHE:
        path = _CYPHER_DIR / f"{name}.cypher"
        _CYPHER_CACHE[name] = path.read_text()
    query = _CYPHER_CACHE[name]
    for key, value in replacements.items():
        query = query.replace(f"__{key}__", value)
    return query


# -- Utilities ----------------------------------------------------------------

def format_namespace(namespace: str) -> str:
    """Format namespace by ensuring it ends with a hyphen if not empty."""
    if namespace:
        return namespace if namespace.endswith("-") else namespace + "-"
    return ""


def _is_write_query(query: str) -> bool:
    """Check if the query is a write query."""
    return (
        re.search(
            r"\b(MERGE|CREATE|INSERT|SET|DELETE|REMOVE|ADD)\b",
            query,
            re.IGNORECASE,
        )
        is not None
    )


def _value_sanitize(d: Any, list_limit: int = 128) -> Any:
    """Sanitize input by removing embedding-like values and oversized lists.

    Strips properties that would occupy significant context space without
    contributing to LLM reasoning (e.g. vector embeddings).
    """
    if isinstance(d, dict):
        new_dict = {}
        for key, value in d.items():
            if isinstance(value, dict):
                sanitized_value = _value_sanitize(value)
                if sanitized_value is not None:
                    new_dict[key] = sanitized_value
            elif isinstance(value, list):
                if len(value) < list_limit:
                    sanitized_value = _value_sanitize(value)
                    if sanitized_value is not None:
                        new_dict[key] = sanitized_value
            else:
                new_dict[key] = value
        return new_dict
    elif isinstance(d, list):
        if len(d) < list_limit:
            return [
                _value_sanitize(item)
                for item in d
                if _value_sanitize(item) is not None
            ]
        else:
            return None
    else:
        return d


def process_config(args: argparse.Namespace) -> dict[str, Union[str, int, None]]:
    """Process CLI arguments and environment variables into a config dict.

    Resolution order: CLI args -> environment variables -> defaults.
    """
    config: dict[str, Any] = {}

    # Neo4j connection
    config["neo4j_uri"] = (
        args.db_url
        or os.getenv("NEO4J_URL")
        or os.getenv("NEO4J_URI")
        or _default("neo4j_uri", "bolt://localhost:7687")
    )
    config["neo4j_user"] = (
        args.username
        or os.getenv("NEO4J_USERNAME")
        or _default("neo4j_user", "neo4j")
    )
    config["neo4j_password"] = (
        args.password
        or os.getenv("NEO4J_PASSWORD")
        or _default("neo4j_password", "password")
    )
    config["neo4j_database"] = (
        args.database
        or os.getenv("NEO4J_DATABASE")
        or _default("neo4j_database", "neo4j")
    )

    # Transport
    config["transport"] = (
        args.transport
        or os.getenv("NEO4J_TRANSPORT")
        or _default("transport", "stdio")
    )

    # Server host/port/path
    config["host"] = (
        args.server_host
        or os.getenv("NEO4J_MCP_SERVER_HOST")
        or (None if config["transport"] == "stdio" else "127.0.0.1")
    )
    config["port"] = (
        args.server_port
        or _env_int("NEO4J_MCP_SERVER_PORT")
        or (None if config["transport"] == "stdio" else 8000)
    )
    config["path"] = (
        args.server_path
        or os.getenv("NEO4J_MCP_SERVER_PATH")
        or (None if config["transport"] == "stdio" else "/mcp/")
    )

    # CORS and host security
    config["allow_origins"] = _parse_csv(
        args.allow_origins, "NEO4J_MCP_SERVER_ALLOW_ORIGINS", []
    )
    config["allowed_hosts"] = _parse_csv(
        args.allowed_hosts,
        "NEO4J_MCP_SERVER_ALLOWED_HOSTS",
        ["localhost", "127.0.0.1"],
    )

    # Namespace
    config["namespace"] = (
        args.namespace or os.getenv("NEO4J_NAMESPACE") or ""
    )

    # Read timeout
    config["read_timeout"] = (
        args.read_timeout
        or _env_int("NEO4J_READ_TIMEOUT")
        or 30
    )

    return config


def _default(key: str, value: str) -> str:
    logger.warning(f"No {key} provided. Using default: {value}")
    return value


def _env_int(var: str) -> int | None:
    val = os.getenv(var)
    return int(val) if val is not None else None


def _parse_csv(
    cli_val: str | None, env_var: str, default: list[str]
) -> list[str]:
    if cli_val is not None:
        return [s.strip() for s in cli_val.split(",") if s.strip()]
    env_val = os.getenv(env_var)
    if env_val is not None:
        return [s.strip() for s in env_val.split(",") if s.strip()]
    return default
