"""Unit tests for mcp-neo4j-biomechanisms.

Tests validation logic without requiring a Neo4j instance.
"""

import pytest

from mcp_neo4j_biomechanisms.biomechanisms import (
    NodeType,
    RelationType,
    validate_entity,
    validate_relation,
    NODE_SCHEMAS,
    RELATION_SCHEMAS,
)
from mcp_neo4j_biomechanisms.utils import _is_write_query, format_namespace


# -- NodeType Enum Tests ------------------------------------------------------

class TestNodeTypeEnum:
    def test_all_types_have_schemas(self):
        for nt in NodeType:
            assert nt.value in NODE_SCHEMAS, f"Missing schema for {nt.value}"

    def test_enum_count(self):
        assert len(NodeType) == 8


# -- RelationType Enum Tests --------------------------------------------------

class TestRelationTypeEnum:
    def test_all_types_have_schemas(self):
        for rt in RelationType:
            assert rt.value in RELATION_SCHEMAS, f"Missing schema for {rt.value}"

    def test_enum_count(self):
        assert len(RelationType) == 12


# -- Entity Validation Tests --------------------------------------------------

class TestEntityValidation:
    def test_neural_structure_valid(self):
        result = validate_entity("NeuralStructure", {
            "name": "Hippocampus",
            "description": "Critical for episodic memory",
            "laterality": "bilateral",
        })
        assert result["name"] == "Hippocampus"
        assert result["laterality"] == "bilateral"

    def test_neural_structure_missing_required(self):
        with pytest.raises(ValueError, match="requires properties"):
            validate_entity("NeuralStructure", {"name": "Hippocampus"})

    def test_neural_structure_invalid_laterality(self):
        with pytest.raises(ValueError, match="Invalid value"):
            validate_entity("NeuralStructure", {
                "name": "Hippocampus",
                "description": "test",
                "laterality": "diagonal",
            })

    def test_neural_structure_invalid_layer(self):
        with pytest.raises(ValueError, match="Invalid value"):
            validate_entity("NeuralStructure", {
                "name": "Hippocampus",
                "description": "test",
                "layer_assignment": "quantum",
            })

    def test_manifold_dimension_requires_layer(self):
        with pytest.raises(ValueError, match="requires properties"):
            validate_entity("ManifoldDimension", {
                "name": "Fear Valence",
                "description": "test",
            })

    def test_manifold_dimension_valid_layers(self):
        for layer in ["data", "envisioning", "affective"]:
            result = validate_entity("ManifoldDimension", {
                "name": "Test Dimension",
                "description": "test",
                "layer": layer,
            })
            assert result["layer"] == layer

    def test_manifold_dimension_invalid_layer(self):
        with pytest.raises(ValueError, match="Invalid value"):
            validate_entity("ManifoldDimension", {
                "name": "Test",
                "description": "test",
                "layer": "physical",
            })

    def test_patient_requires_condition(self):
        with pytest.raises(ValueError, match="requires properties"):
            validate_entity("Patient", {"name": "Patient SM"})

    def test_patient_valid(self):
        result = validate_entity("Patient", {
            "name": "Patient SM",
            "condition": "Bilateral amygdala calcification",
            "onset_age": "10",
        })
        assert result["condition"] == "Bilateral amygdala calcification"

    def test_study_requires_year_and_t_valid(self):
        with pytest.raises(ValueError, match="requires properties"):
            validate_entity("Study", {"name": "Voon et al. 2010"})

    def test_study_valid(self):
        result = validate_entity("Study", {
            "name": "Voon et al. 2010",
            "year": 2010,
            "t_valid": "2010-01-01",
            "methodology": "fMRI",
        })
        assert result["year"] == 2010

    def test_study_year_type_check(self):
        with pytest.raises(ValueError, match="must be int"):
            validate_entity("Study", {
                "name": "Test",
                "year": "2010",
                "t_valid": "2010-01-01",
            })

    def test_empirical_evidence_requires_t_valid(self):
        with pytest.raises(ValueError, match="requires properties"):
            validate_entity("EmpiricalEvidence", {
                "name": "Test",
                "description": "test",
            })

    def test_type_property_rejected(self):
        with pytest.raises(ValueError, match="'type' property is forbidden"):
            validate_entity("NeuralStructure", {
                "name": "test",
                "description": "test",
                "type": "NeuralStructure",
            })

    def test_unknown_property_rejected(self):
        with pytest.raises(ValueError, match="Unknown property"):
            validate_entity("NeuralStructure", {
                "name": "test",
                "description": "test",
                "flavor": "vanilla",
            })

    def test_unknown_node_type_rejected(self):
        with pytest.raises(ValueError, match="Unknown node type"):
            validate_entity("Unicorn", {"name": "test"})

    def test_t_created_stripped(self):
        result = validate_entity("NeuralStructure", {
            "name": "test",
            "description": "test",
            "t_created": "2024-01-01",
        })
        assert "t_created" not in result

    def test_theoretical_principle_status_enum(self):
        for status in ["proposed", "supported", "challenged", "falsified"]:
            result = validate_entity("TheoreticalPrinciple", {
                "name": "Test",
                "description": "test",
                "status": status,
            })
            assert result["status"] == status

    def test_theoretical_principle_invalid_status(self):
        with pytest.raises(ValueError, match="Invalid value"):
            validate_entity("TheoreticalPrinciple", {
                "name": "Test",
                "description": "test",
                "status": "maybe",
            })

    def test_edge_configuration_valid(self):
        result = validate_entity("EdgeConfiguration", {
            "name": "Affective Temporal Reach Circuit",
            "description": "Circuit generating affective temporal reach",
            "components": "vmPFC, ACC, Hippocampus",
            "mechanism": "Temporal bridging via hippocampal replay",
        })
        assert result["mechanism"] is not None

    def test_falsification_condition_valid(self):
        result = validate_entity("FalsificationCondition", {
            "name": "FC7",
            "description": "Data retrieval without entorhinal addressing",
            "difficulty": "Requires specific lesion patients",
        })
        assert result["name"] == "FC7"


# -- Relation Validation Tests ------------------------------------------------

class TestRelationValidation:
    def test_participates_in_correct_direction(self):
        result = validate_relation(
            "PARTICIPATES_IN", "NeuralStructure", "EdgeConfiguration"
        )
        assert result == {}

    def test_participates_in_wrong_direction(self):
        with pytest.raises(ValueError, match="requires source"):
            validate_relation(
                "PARTICIPATES_IN", "EdgeConfiguration", "NeuralStructure"
            )

    def test_generates_correct_direction(self):
        validate_relation("GENERATES", "EdgeConfiguration", "ManifoldDimension")

    def test_generates_wrong_source(self):
        with pytest.raises(ValueError, match="requires source"):
            validate_relation("GENERATES", "NeuralStructure", "ManifoldDimension")

    def test_generates_wrong_target(self):
        with pytest.raises(ValueError, match="requires target"):
            validate_relation("GENERATES", "EdgeConfiguration", "NeuralStructure")

    def test_demonstrates_requires_effect(self):
        with pytest.raises(ValueError, match="requires property 'effect'"):
            validate_relation(
                "DEMONSTRATES", "Patient", "ManifoldDimension", {}
            )

    def test_demonstrates_valid_effects(self):
        for effect in ["collapse", "preservation", "severing", "rerouting", "gain_change"]:
            result = validate_relation(
                "DEMONSTRATES", "Patient", "ManifoldDimension",
                {"effect": effect},
            )
            assert result["effect"] == effect

    def test_demonstrates_invalid_effect(self):
        with pytest.raises(ValueError, match="Invalid value"):
            validate_relation(
                "DEMONSTRATES", "Patient", "ManifoldDimension",
                {"effect": "explosion"},
            )

    def test_demonstrates_wrong_source(self):
        with pytest.raises(ValueError, match="requires source"):
            validate_relation(
                "DEMONSTRATES", "NeuralStructure", "ManifoldDimension",
                {"effect": "collapse"},
            )

    def test_would_falsify_requires_severity(self):
        with pytest.raises(ValueError, match="requires property 'severity'"):
            validate_relation(
                "WOULD_FALSIFY", "FalsificationCondition", "TheoreticalPrinciple",
                {},
            )

    def test_would_falsify_valid_severities(self):
        for severity in ["falsify", "invalidate", "constrain", "weaken"]:
            result = validate_relation(
                "WOULD_FALSIFY", "FalsificationCondition", "TheoreticalPrinciple",
                {"severity": severity},
            )
            assert result["severity"] == severity

    def test_would_falsify_invalid_severity(self):
        with pytest.raises(ValueError, match="Invalid value"):
            validate_relation(
                "WOULD_FALSIFY", "FalsificationCondition", "TheoreticalPrinciple",
                {"severity": "annihilate"},
            )

    def test_connects_to_neural_structures_only(self):
        validate_relation("CONNECTS_TO", "NeuralStructure", "NeuralStructure")
        with pytest.raises(ValueError, match="requires source"):
            validate_relation("CONNECTS_TO", "Patient", "NeuralStructure")

    def test_connects_to_directionality_enum(self):
        result = validate_relation(
            "CONNECTS_TO", "NeuralStructure", "NeuralStructure",
            {"directionality": "bidirectional"},
        )
        assert result["directionality"] == "bidirectional"
        with pytest.raises(ValueError, match="Invalid value"):
            validate_relation(
                "CONNECTS_TO", "NeuralStructure", "NeuralStructure",
                {"directionality": "sideways"},
            )

    def test_supports_any_target(self):
        # SUPPORTS has target_types=None, so any target is valid
        validate_relation("SUPPORTS", "EmpiricalEvidence", "TheoreticalPrinciple")
        validate_relation("SUPPORTS", "Study", "ManifoldDimension")

    def test_supports_wrong_source(self):
        with pytest.raises(ValueError, match="requires source"):
            validate_relation("SUPPORTS", "Patient", "TheoreticalPrinciple")

    def test_challenges_any_target(self):
        validate_relation("CHALLENGES", "EmpiricalEvidence", "TheoreticalPrinciple")
        validate_relation("CHALLENGES", "Study", "ManifoldDimension")

    def test_explains_direction(self):
        validate_relation("EXPLAINS", "TheoreticalPrinciple", "Patient")
        with pytest.raises(ValueError, match="requires source"):
            validate_relation("EXPLAINS", "Patient", "TheoreticalPrinciple")

    def test_studied_in_direction(self):
        validate_relation("STUDIED_IN", "Patient", "Study")
        with pytest.raises(ValueError, match="requires source"):
            validate_relation("STUDIED_IN", "Study", "Patient")

    def test_reported_in_direction(self):
        validate_relation("REPORTED_IN", "EmpiricalEvidence", "Study")
        with pytest.raises(ValueError, match="requires source"):
            validate_relation("REPORTED_IN", "Study", "EmpiricalEvidence")

    def test_unknown_relation_type(self):
        with pytest.raises(ValueError, match="Unknown relation type"):
            validate_relation("LOVES", "Patient", "Patient")

    def test_unknown_property_rejected(self):
        with pytest.raises(ValueError, match="Unknown property"):
            validate_relation(
                "CONNECTS_TO", "NeuralStructure", "NeuralStructure",
                {"color": "blue"},
            )

    def test_t_created_stripped(self):
        result = validate_relation(
            "CONNECTS_TO", "NeuralStructure", "NeuralStructure",
            {"t_created": "2024-01-01", "pathway": "arcuate fasciculus"},
        )
        assert "t_created" not in result
        assert result["pathway"] == "arcuate fasciculus"

    def test_decomposes_into_direction(self):
        validate_relation("DECOMPOSES_INTO", "NeuralStructure", "NeuralStructure")
        with pytest.raises(ValueError, match="requires source"):
            validate_relation("DECOMPOSES_INTO", "Patient", "NeuralStructure")

    def test_composes_into_direction(self):
        validate_relation("COMPOSES_INTO", "NeuralStructure", "NeuralStructure")


# -- Utility Tests ------------------------------------------------------------

class TestUtils:
    def test_write_query_detection(self):
        assert _is_write_query("CREATE (n:Node)") is True
        assert _is_write_query("MERGE (n:Node {name: 'x'})") is True
        assert _is_write_query("MATCH (n) SET n.x = 1") is True
        assert _is_write_query("MATCH (n) DELETE n") is True
        assert _is_write_query("MATCH (n) REMOVE n.x") is True
        assert _is_write_query("MATCH (n) RETURN n") is False
        assert _is_write_query("CALL db.index.fulltext.queryNodes('idx', 'q')") is False

    def test_format_namespace(self):
        assert format_namespace("") == ""
        assert format_namespace("bio") == "bio-"
        assert format_namespace("bio-") == "bio-"


# -- Schema Completeness Tests ------------------------------------------------

class TestSchemaCompleteness:
    """Ensure the schema registry is self-consistent."""

    def test_all_node_types_have_name(self):
        for node_type, schema in NODE_SCHEMAS.items():
            assert "name" in schema["required"], (
                f"{node_type} must have 'name' as required property"
            )

    def test_all_relation_schemas_have_source_types(self):
        for rel_type, schema in RELATION_SCHEMAS.items():
            assert "source_types" in schema, (
                f"{rel_type} must define source_types"
            )
            assert "target_types" in schema, (
                f"{rel_type} must define target_types"
            )

    def test_relation_source_types_are_valid_node_types(self):
        valid_types = set(NODE_SCHEMAS.keys())
        for rel_type, schema in RELATION_SCHEMAS.items():
            source_types = schema.get("source_types")
            if source_types:
                for st in source_types:
                    assert st in valid_types, (
                        f"{rel_type} references unknown source type '{st}'"
                    )

    def test_relation_target_types_are_valid_node_types(self):
        valid_types = set(NODE_SCHEMAS.keys())
        for rel_type, schema in RELATION_SCHEMAS.items():
            target_types = schema.get("target_types")
            if target_types:
                for tt in target_types:
                    assert tt in valid_types, (
                        f"{rel_type} references unknown target type '{tt}'"
                    )
