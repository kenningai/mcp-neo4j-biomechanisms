import logging
from enum import Enum
from typing import Any

from neo4j import AsyncDriver, RoutingControl

from .utils import load_cypher

logger = logging.getLogger("kenning_soma")
logger.setLevel(logging.INFO)


def _neo4j_datetime_to_str(val: Any) -> str | None:
    """Convert a Neo4j DateTime/Date to ISO string, or return None."""
    if val is None:
        return None
    return val.iso_format()


# -- Node Type Enum -----------------------------------------------------------

class NodeType(str, Enum):
    """Allowed node type labels for the biomechanisms knowledge graph.

    Designed for easy extension — adding a type is a minor version bump.
    """
    NEURAL_STRUCTURE = "NeuralStructure"
    EDGE_CONFIGURATION = "EdgeConfiguration"
    MANIFOLD_DIMENSION = "ManifoldDimension"
    PATIENT = "Patient"
    FALSIFICATION_CONDITION = "FalsificationCondition"
    THEORETICAL_PRINCIPLE = "TheoreticalPrinciple"
    EMPIRICAL_EVIDENCE = "EmpiricalEvidence"
    STUDY = "Study"


# -- Relation Type Enum ------------------------------------------------------

class RelationType(str, Enum):
    """Allowed relationship types for the biomechanisms knowledge graph."""
    # Structural
    CONNECTS_TO = "CONNECTS_TO"
    PARTICIPATES_IN = "PARTICIPATES_IN"
    GENERATES = "GENERATES"
    DECOMPOSES_INTO = "DECOMPOSES_INTO"
    COMPOSES_INTO = "COMPOSES_INTO"
    # Evidential
    DEMONSTRATES = "DEMONSTRATES"
    SUPPORTS = "SUPPORTS"
    CHALLENGES = "CHALLENGES"
    # Theoretical
    EXPLAINS = "EXPLAINS"
    WOULD_FALSIFY = "WOULD_FALSIFY"
    # Provenance
    STUDIED_IN = "STUDIED_IN"
    REPORTED_IN = "REPORTED_IN"


# -- Node Property Schemas ---------------------------------------------------
# Each entry defines required and optional properties per node type.
# Adding a new node type = adding an enum value + a schema entry here.

LAYER_VALUES = {"data", "envisioning", "affective"}
LATERALITY_VALUES = {"bilateral", "left", "right"}

NODE_SCHEMAS: dict[str, dict[str, Any]] = {
    "NeuralStructure": {
        "required": {"name": str, "description": str},
        "optional": {
            "brodmann_areas": str,
            "subdivisions": str,
            "layer_assignment": str,
            "laterality": str,
        },
        "validators": {
            "layer_assignment": lambda v: v in LAYER_VALUES,
            "laterality": lambda v: v in LATERALITY_VALUES,
        },
    },
    "EdgeConfiguration": {
        "required": {"name": str, "description": str},
        "optional": {
            "components": str,
            "mechanism": str,
            "disruption_prediction": str,
        },
    },
    "ManifoldDimension": {
        "required": {"name": str, "description": str, "layer": str},
        "optional": {
            "loss_phenomenology": str,
            "cross_frame_observation": str,
            "empirical_key": str,
        },
        "validators": {
            "layer": lambda v: v in LAYER_VALUES,
        },
    },
    "Patient": {
        "required": {"name": str, "condition": str},
        "optional": {
            "description": str,
            "damage_description": str,
            "key_finding": str,
            "framework_interpretation": str,
            "onset_age": str,
            "onset_type": str,
            "t_valid": str,
        },
    },
    "FalsificationCondition": {
        "required": {"name": str, "description": str},
        "optional": {
            "what_would_falsify": str,
            "current_evidence_status": str,
            "difficulty": str,
        },
    },
    "TheoreticalPrinciple": {
        "required": {"name": str, "description": str},
        "optional": {
            "status": str,
            "origin": str,
        },
        "validators": {
            "status": lambda v: v in {"proposed", "supported", "challenged", "falsified"},
        },
    },
    "EmpiricalEvidence": {
        "required": {"name": str, "description": str, "t_valid": str},
        "optional": {
            "key_studies": str,
            "framework_prediction": str,
            "constitutive_claim": str,
        },
    },
    "Study": {
        "required": {"name": str, "year": int, "t_valid": str},
        "optional": {
            "description": str,
            "title": str,
            "authors": str,
            "journal": str,
            "doi": str,
            "sample_size": str,
            "methodology": str,
        },
    },
}


# -- Relation Schemas ---------------------------------------------------------
# Direction constraints, allowed source/target types, and property enums.

EFFECT_VALUES = {"collapse", "preservation", "severing", "rerouting", "gain_change"}
SEVERITY_VALUES = {"falsify", "invalidate", "constrain", "weaken"}

RELATION_SCHEMAS: dict[str, dict[str, Any]] = {
    "CONNECTS_TO": {
        "source_types": {"NeuralStructure"},
        "target_types": {"NeuralStructure"},
        "properties": {
            "pathway": str, "directionality": str,
            "function": str, "evidence": str,
        },
        "validators": {
            "directionality": lambda v: v in {"bidirectional", "unidirectional"},
        },
    },
    "PARTICIPATES_IN": {
        "source_types": {"NeuralStructure"},
        "target_types": {"EdgeConfiguration"},
        "properties": {},
    },
    "GENERATES": {
        "source_types": {"EdgeConfiguration"},
        "target_types": {"ManifoldDimension"},
        "properties": {},
    },
    "DECOMPOSES_INTO": {
        "source_types": {"NeuralStructure"},
        "target_types": {"NeuralStructure"},
        "properties": {},
    },
    "COMPOSES_INTO": {
        "source_types": {"NeuralStructure"},
        "target_types": {"NeuralStructure"},
        "properties": {},
    },
    "DEMONSTRATES": {
        "source_types": {"Patient"},
        "target_types": {"ManifoldDimension", "EdgeConfiguration"},
        "properties": {"effect": str},
        "required_properties": {"effect"},
        "validators": {
            "effect": lambda v: v in EFFECT_VALUES,
        },
    },
    "SUPPORTS": {
        "source_types": {"EmpiricalEvidence", "Study"},
        "target_types": None,  # any node
        "properties": {},
    },
    "CHALLENGES": {
        "source_types": {"EmpiricalEvidence", "Study"},
        "target_types": None,  # any node
        "properties": {},
    },
    "EXPLAINS": {
        "source_types": {"TheoreticalPrinciple"},
        "target_types": {"Patient", "ManifoldDimension", "EdgeConfiguration"},
        "properties": {},
    },
    "WOULD_FALSIFY": {
        "source_types": {"FalsificationCondition"},
        "target_types": None,  # any claim node
        "properties": {"severity": str},
        "required_properties": {"severity"},
        "validators": {
            "severity": lambda v: v in SEVERITY_VALUES,
        },
    },
    "STUDIED_IN": {
        "source_types": {"Patient"},
        "target_types": {"Study"},
        "properties": {},
    },
    "REPORTED_IN": {
        "source_types": {"EmpiricalEvidence"},
        "target_types": {"Study"},
        "properties": {},
    },
}


# -- Validation Functions -----------------------------------------------------

def validate_entity(node_type: str, properties: dict[str, Any]) -> dict[str, Any]:
    """Validate entity properties against the schema registry.

    Returns cleaned properties dict with t_created excluded (auto-set).
    Raises ValueError on validation failure.
    """
    if node_type not in NODE_SCHEMAS:
        valid = ", ".join(sorted(NODE_SCHEMAS.keys()))
        raise ValueError(f"Unknown node type '{node_type}'. Valid types: {valid}")

    schema = NODE_SCHEMAS[node_type]

    # Reject 'type' property — label IS the type (invariant 9)
    if "type" in properties:
        raise ValueError(
            "The 'type' property is forbidden. The Neo4j label IS the type. "
            "Remove 'type' from properties."
        )

    # Check required properties
    missing = []
    for prop in schema["required"]:
        if prop not in properties or properties[prop] is None:
            missing.append(prop)
    if missing:
        raise ValueError(
            f"{node_type} requires properties: {missing}"
        )

    # Type-check and collect valid properties
    all_props = {**schema["required"], **schema.get("optional", {})}
    cleaned: dict[str, Any] = {}
    for key, value in properties.items():
        if key == "t_created":
            continue  # auto-set, skip
        if key not in all_props:
            raise ValueError(
                f"Unknown property '{key}' for {node_type}. "
                f"Valid properties: {sorted(all_props.keys())}"
            )
        expected_type = all_props[key]
        if not isinstance(value, expected_type):
            raise ValueError(
                f"Property '{key}' on {node_type} must be {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        cleaned[key] = value

    # Run validators
    validators = schema.get("validators", {})
    for prop, validator in validators.items():
        if prop in cleaned and not validator(cleaned[prop]):
            raise ValueError(
                f"Invalid value '{cleaned[prop]}' for {node_type}.{prop}"
            )

    return cleaned


def validate_relation(
    rel_type: str,
    source_label: str,
    target_label: str,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a relationship against the schema registry.

    Enforces direction constraints, source/target type restrictions,
    required properties, and property enum values.
    Returns cleaned properties dict.
    """
    if rel_type not in RELATION_SCHEMAS:
        valid = ", ".join(sorted(RELATION_SCHEMAS.keys()))
        raise ValueError(f"Unknown relation type '{rel_type}'. Valid types: {valid}")

    schema = RELATION_SCHEMAS[rel_type]
    properties = properties or {}

    # Direction constraint: source type
    allowed_sources = schema.get("source_types")
    if allowed_sources and source_label not in allowed_sources:
        raise ValueError(
            f"{rel_type} requires source to be one of {allowed_sources}, "
            f"got {source_label}"
        )

    # Direction constraint: target type
    allowed_targets = schema.get("target_types")
    if allowed_targets and target_label not in allowed_targets:
        raise ValueError(
            f"{rel_type} requires target to be one of {allowed_targets}, "
            f"got {target_label}"
        )

    # Check required properties
    required = schema.get("required_properties", set())
    for prop in required:
        if prop not in properties or properties[prop] is None:
            raise ValueError(
                f"{rel_type} requires property '{prop}'"
            )

    # Validate property values
    allowed_props = schema.get("properties", {})
    cleaned: dict[str, Any] = {}
    for key, value in properties.items():
        if key == "t_created":
            continue
        if key not in allowed_props:
            raise ValueError(
                f"Unknown property '{key}' for {rel_type}. "
                f"Valid properties: {sorted(allowed_props.keys())}"
            )
        cleaned[key] = value

    # Run validators
    validators = schema.get("validators", {})
    for prop, validator in validators.items():
        if prop in cleaned and not validator(cleaned[prop]):
            raise ValueError(
                f"Invalid value '{cleaned[prop]}' for {rel_type}.{prop}"
            )

    return cleaned


# -- Core Logic Class --------------------------------------------------------

class Neo4jBiomechanisms:
    """Core logic for the biomechanisms empirical knowledge graph."""

    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def create_fulltext_index(self) -> None:
        """Create fulltext search index spanning all node types.

        Self-healing: drops and recreates on startup.
        """
        try:
            # Drop old index if exists
            try:
                await self.driver.execute_query(
                    "DROP INDEX biomechanisms_index IF EXISTS",
                    routing_control=RoutingControl.WRITE,
                )
            except Exception:
                pass

            await self.driver.execute_query(
                load_cypher("index_create"),
                routing_control=RoutingControl.WRITE,
            )
            logger.info("Created fulltext index biomechanisms_index")
        except Exception as e:
            logger.debug(f"Fulltext index creation: {e}")

    # -- Entity Tools ---------------------------------------------------------

    async def create_entities(
        self, entities: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create nodes. Validates type enum, required properties, no 'type' stored.

        Each entity dict must have 'type' (node label) and properties.
        t_created is auto-set. t_valid is set if provided and valid.
        """
        logger.info(f"Creating {len(entities)} entities")
        results = []

        for entity in entities:
            node_type = entity.get("type")
            if not node_type:
                raise ValueError("Each entity must have a 'type' field")

            # Extract properties (everything except 'type')
            properties = {k: v for k, v in entity.items() if k != "type"}

            # Validate against schema
            cleaned = validate_entity(node_type, properties)

            # Build SET clauses dynamically — only set what the caller actually
            # provided, so MERGE-on-existing doesn't wipe absent fields.
            set_clauses = []
            params: dict[str, Any] = {"name": cleaned["name"]}

            for key, value in cleaned.items():
                if key == "name":
                    continue
                if key == "t_valid":
                    set_clauses.append(f"SET n.t_valid = datetime(${key})")
                elif isinstance(value, int):
                    set_clauses.append(f"SET n.{key} = toInteger(${key})")
                else:
                    set_clauses.append(f"SET n.{key} = ${key}")
                params[key] = value

            extra_sets = "\n".join(set_clauses) if set_clauses else ""

            query = load_cypher("entity_create", label=node_type, extra_sets=extra_sets)

            result = await self.driver.execute_query(
                query, params, routing_control=RoutingControl.WRITE,
            )

            if result.records:
                r = result.records[0]
                record = {
                    "name": r["name"],
                    "type": r["type"],
                    "t_created": _neo4j_datetime_to_str(r["t_created"]),
                }
                results.append(record)

        return results

    async def delete_entities(
        self, names: list[str]
    ) -> list[dict[str, Any]]:
        """Delete nodes by exact name match. Returns what was deleted.

        DETACH DELETE removes the node and all its relationships.
        Destructive and irreversible.
        """
        logger.info(f"Deleting {len(names)} entities")
        results = []

        for name in names:
            # First, retrieve what we're about to delete
            preview = await self.driver.execute_query(
                "MATCH (n {name: $name}) "
                "OPTIONAL MATCH (n)-[r]-() "
                "RETURN labels(n)[0] AS type, n.name AS name, "
                "       n.description AS description, count(r) AS rel_count",
                {"name": name},
                routing_control=RoutingControl.READ,
            )

            if not preview.records or preview.records[0]["type"] is None:
                raise ValueError(f"Entity '{name}' not found")

            r = preview.records[0]
            deleted_info = {
                "name": r["name"],
                "type": r["type"],
                "description": r["description"],
                "relationships_removed": r["rel_count"],
                "deleted": True,
            }

            # Execute deletion
            await self.driver.execute_query(
                load_cypher("entity_delete"),
                {"name": name},
                routing_control=RoutingControl.WRITE,
            )

            results.append(deleted_info)

        return results

    # -- Relation Tools -------------------------------------------------------

    async def create_relations(
        self, relations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Create relationships with full schema validation.

        Validates: relation type enum, direction constraints, source/target
        type restrictions, required properties, property enum values.
        Auto-sets t_created on all relationships.
        """
        logger.info(f"Creating {len(relations)} relations")
        results = []

        for rel in relations:
            rel_type = rel.get("type")
            source_name = rel.get("source")
            target_name = rel.get("target")
            properties = rel.get("properties", {})

            if not rel_type or not source_name or not target_name:
                raise ValueError(
                    "Each relation must have 'type', 'source', and 'target'"
                )

            # Validate rel_type is in enum
            try:
                RelationType(rel_type)
            except ValueError:
                valid = ", ".join(r.value for r in RelationType)
                raise ValueError(
                    f"Unknown relation type '{rel_type}'. Valid types: {valid}"
                )

            # Resolve source and target nodes
            source_result = await self.driver.execute_query(
                "MATCH (n {name: $name}) RETURN labels(n)[0] AS label, "
                "elementId(n) AS eid, n.name AS name",
                {"name": source_name},
                routing_control=RoutingControl.READ,
            )
            if not source_result.records:
                raise ValueError(f"Source entity '{source_name}' not found")
            if len(source_result.records) > 1:
                raise ValueError(
                    f"Source entity '{source_name}' is ambiguous — "
                    f"found {len(source_result.records)} nodes with that name"
                )

            target_result = await self.driver.execute_query(
                "MATCH (n {name: $name}) RETURN labels(n)[0] AS label, "
                "elementId(n) AS eid, n.name AS name",
                {"name": target_name},
                routing_control=RoutingControl.READ,
            )
            if not target_result.records:
                raise ValueError(f"Target entity '{target_name}' not found")
            if len(target_result.records) > 1:
                raise ValueError(
                    f"Target entity '{target_name}' is ambiguous — "
                    f"found {len(target_result.records)} nodes with that name"
                )

            source_label = source_result.records[0]["label"]
            target_label = target_result.records[0]["label"]
            source_eid = source_result.records[0]["eid"]
            target_eid = target_result.records[0]["eid"]

            # Validate against relation schema
            cleaned_props = validate_relation(
                rel_type, source_label, target_label, properties
            )

            # Build property SET clause
            prop_sets = []
            params: dict[str, Any] = {
                "source_eid": source_eid,
                "target_eid": target_eid,
            }
            for key, value in cleaned_props.items():
                prop_sets.append(f"r.{key} = ${key}")
                params[key] = value

            prop_clause = ""
            if prop_sets:
                prop_clause = ", " + ", ".join(prop_sets)

            query = load_cypher(
                "relation_create",
                rel_type=rel_type,
                prop_clause=prop_clause,
            )

            await self.driver.execute_query(
                query, params, routing_control=RoutingControl.WRITE,
            )

            results.append({
                "source": source_name,
                "target": target_name,
                "type": rel_type,
                "properties": cleaned_props,
                "created": True,
            })

        return results

    async def delete_relations(
        self, relations: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Delete specific relationships by source, target, and type."""
        logger.info(f"Deleting {len(relations)} relations")
        results = []

        for rel in relations:
            rel_type = rel.get("type")
            source_name = rel.get("source")
            target_name = rel.get("target")

            if not rel_type or not source_name or not target_name:
                raise ValueError(
                    "Each relation must have 'type', 'source', and 'target'"
                )

            result = await self.driver.execute_query(
                load_cypher("relation_delete", rel_type=rel_type),
                {"source": source_name, "target": target_name},
                routing_control=RoutingControl.WRITE,
            )

            deleted = result.records[0]["deleted"] if result.records else 0
            if deleted == 0:
                raise ValueError(
                    f"Relation {rel_type} from '{source_name}' to "
                    f"'{target_name}' not found"
                )

            results.append({
                "source": source_name,
                "target": target_name,
                "type": rel_type,
                "deleted": True,
            })

        return results

    # -- Query Tools ----------------------------------------------------------

    async def search(
        self, query: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Fulltext search across all node types on name and description."""
        logger.info(f"Search: '{query}' (limit={limit})")

        result = await self.driver.execute_query(
            load_cypher("search_entities"),
            {"query": query, "limit": limit},
            routing_control=RoutingControl.READ,
        )

        if not result.records:
            return []

        entities = []
        for r in result.records:
            entity: dict[str, Any] = {
                "name": r["name"],
                "type": r["type"],
                "description": r["description"],
                "score": r["score"],
            }
            # Include all additional properties
            if r["properties"]:
                for key, value in r["properties"].items():
                    if key not in ("name", "description") and value is not None:
                        entity[key] = _neo4j_datetime_to_str(value) if hasattr(value, 'iso_format') else value
            entities.append(entity)

        return entities

    async def find_by_name(
        self, names: list[str], limit: int = 20
    ) -> dict[str, Any]:
        """Exact name lookup with relationships between found nodes."""
        logger.info(f"Find by name: {names}")

        result = await self.driver.execute_query(
            load_cypher("find_entities"),
            {"names": names, "limit": limit},
            routing_control=RoutingControl.READ,
        )

        entities = []
        for r in result.records:
            entity: dict[str, Any] = {
                "name": r["name"],
                "type": r["type"],
            }
            if r["properties"]:
                for key, value in r["properties"].items():
                    if key != "name" and value is not None:
                        entity[key] = _neo4j_datetime_to_str(value) if hasattr(value, 'iso_format') else value
            entities.append(entity)

        # Get relationships between found nodes
        if entities:
            rel_result = await self.driver.execute_query(
                load_cypher("search_relations"),
                {"names": [e["name"] for e in entities]},
                routing_control=RoutingControl.READ,
            )
            relations = [
                {
                    "source": r["source"],
                    "target": r["target"],
                    "type": r["type"],
                }
                for r in rel_result.records
            ]
        else:
            relations = []

        return {"entities": entities, "relations": relations}
