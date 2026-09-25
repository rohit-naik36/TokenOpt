"""Unit tests for ContextAnalyzer.

Tests:
1. Deterministic structure detection across supported types and certainty levels.
2. Deterministic entity and constraint extraction across all 8 abstract categories.
3. False-positive resistance for ordinary prose, numbers, words, and punctuation.
4. Role authority defaults and preservation classification.
5. "Contains P1" != "Entire unit is P1" core preservation law.
6. Execution against the 12 evaluation corpus cases in isolation.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from evaluation.cases import get_core_cases
from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.analyzer import (
    AnalyzerStage,
    ContextAnalyzer,
    detect_structure,
    extract_invariants,
)
from tokenopt.pipeline.base import OptimizationContext, OptimizationPipeline
from tokenopt.pipeline.compressor import CompressorStage, ContextSummarizerStage
from tokenopt.pipeline.preservation import (
    DetectionCertainty,
    EntityCategory,
    InvariantType,
    PreservationClass,
    PreservationMap,
    StructuralType,
)
from tokenopt.pipeline.router import RouterStage
from tokenopt.utils.token_counter import count_message_tokens


class TestStructureDetection:
    """Test deterministic structure classification and certainty."""

    def test_detect_prose(self):
        text = "Hello! Could you please explain how microservices communicate?"
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.PROSE
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_python_fenced_valid(self):
        text = (
            "Here is the code:\n"
            "```python\n"
            "def add(a: int, b: int) -> int:\n"
            "    return a + b\n"
            "```\n"
            "Done."
        )
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.CODE_PYTHON
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_python_fenced_syntax_error(self):
        text = "```python\ndef broken(\n```"
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.CODE_PYTHON
        assert certainty == DetectionCertainty.AMBIGUOUS

    def test_detect_python_bare_code(self):
        text = (
            "Please review this class:\n\n"
            "class PaymentGatewayClient:\n"
            "    MAX_RETRIES = 3\n"
            "    def process_payment(self, amount: float) -> bool:\n"
            "        return True\n\n"
            "Could you verify the error handling?"
        )
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.CODE_PYTHON
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_python_bare_code_ambiguous(self):
        text = "class IncompleteClass:\n    def missing_body("
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.CODE_PYTHON
        assert certainty == DetectionCertainty.AMBIGUOUS

    def test_detect_empty_content_is_prose(self):
        stype, certainty = detect_structure("", "user")
        assert stype == StructuralType.PROSE
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_generic_fence_plain_text_is_prose(self):
        text = "```\nThis is just ordinary plain text inside a generic fence.\n```"
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.PROSE
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_generic_fence_with_valid_python(self):
        text = "```\ndef valid_func(x: int) -> int:\n    return x + 1\n```"
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.CODE_PYTHON
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_generic_fence_with_python_syntax_error(self):
        text = "```\ndef broken_func(\n```"
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.CODE_PYTHON
        assert certainty == DetectionCertainty.AMBIGUOUS

    def test_detect_json_valid(self):
        text = (
            "Please parse this configuration payload:\n\n"
            "{\n"
            '  "cluster_id": "us-east-prod-77",\n'
            '  "node_count": 12,\n'
            '  "auto_scaling": true\n'
            "}\n\n"
            "Could you check node_count?"
        )
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.JSON
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_json_fenced_valid(self):
        text = '```json\n{"service": "auth", "port": 8080}\n```'
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.JSON
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_json_fenced_malformed_is_ambiguous(self):
        text = '```json\n{"service": "auth", broken json\n```'
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.JSON
        assert certainty == DetectionCertainty.AMBIGUOUS

    def test_detect_json_malformed_ambiguous(self):
        text = '{"cluster_id": "us-east-prod-77", "node_count":'
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.JSON
        assert certainty == DetectionCertainty.AMBIGUOUS

    def test_detect_embedded_json_block(self):
        text = 'Here is the response data: {"status": "ok", "code": 200} in json format.'
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.JSON
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_markdown_table_valid(self):
        text = (
            "| Region | Tier | Status |\n"
            "|:---|:---:|:---|\n"
            "| US-East | Tier-1 | Compliant |\n"
            "| EU-Central | Tier-2 | Breach |\n"
        )
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.MARKDOWN_TABLE
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_markdown_table_mismatched_columns(self):
        text = (
            "| Region | Tier | Status |\n"
            "|:---|:---:|\n"  # Only 2 separator columns vs 3 header columns
            "| US-East | Tier-1 | Compliant |\n"
        )
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.MARKDOWN_TABLE
        assert certainty == DetectionCertainty.AMBIGUOUS

    def test_detect_markdown_table_broken_separator(self):
        text = (
            "| Region | Tier |\n"
            "| -- - - - | ---- |\n"
            "| US-East | Tier-1 |\n"
        )
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.MARKDOWN_TABLE
        assert certainty == DetectionCertainty.AMBIGUOUS

    def test_detect_casual_pipes_is_prose(self):
        text = "Please choose: Option A | Option B | Option C."
        stype, certainty = detect_structure(text, "user")
        assert stype == StructuralType.PROSE
        assert certainty == DetectionCertainty.DETECTED

    def test_detect_tool_payload(self):
        stype, certainty = detect_structure('{"result": "ok"}', "tool")
        assert stype == StructuralType.TOOL_PAYLOAD
        assert certainty == DetectionCertainty.DETECTED


class TestEntityExtraction:
    """Test deterministic entity extraction across all 8 abstract categories."""

    def test_extract_identifiers(self):
        content = (
            "See [DOC-401] for cluster prod-db-replica-02 on node-01 "
            "during MW-88 for project Apollo."
        )
        invs = extract_invariants(content, 0, "user")
        id_invs = [inv for inv in invs if inv.category == EntityCategory.IDENTIFIER]
        markers = {inv.marker for inv in id_invs}

        assert "[DOC-401]" in markers
        assert "prod-db-replica-02" in markers
        assert "node-01" in markers
        assert "MW-88" in markers
        assert "project Apollo" in markers
        for inv in id_invs:
            assert inv.invariant_type == InvariantType.LEXICAL

    def test_extract_error_codes(self):
        content = (
            "Encountered KERN-ERR-0x89AB and fatal 0xDEADBEEF "
            "causing ValueError. CRITICAL_ALERT_ASSERTION raised."
        )
        invs = extract_invariants(content, 0, "user")
        err_invs = [inv for inv in invs if inv.category == EntityCategory.ERROR_CODE]
        markers = {inv.marker for inv in err_invs}

        assert "KERN-ERR-0x89AB" in markers
        assert "0xDEADBEEF" in markers
        assert "ValueError" in markers
        assert "CRITICAL_ALERT_ASSERTION" in markers

    def test_extract_urls_and_endpoints(self):
        content = (
            "Endpoint https://dr.internal.net/v1 or /v2/telemetry listening on port 8443. "
            "Email security-ops@acme.corp."
        )
        invs = extract_invariants(content, 0, "user")
        url_invs = [inv for inv in invs if inv.category == EntityCategory.URL_OR_ENDPOINT]
        markers = {inv.marker for inv in url_invs}

        assert "https://dr.internal.net/v1" in markers
        assert "/v2/telemetry" in markers
        assert "port 8443" in markers
        assert "security-ops@acme.corp" in markers

    def test_extract_numeric_constraints(self):
        content = (
            "Structure into 5 sections with 150 words. Target 99.99% availability "
            "with 50,000 requests per minute and version 4.2."
        )
        invs = extract_invariants(content, 0, "user")
        num_invs = [inv for inv in invs if inv.category == EntityCategory.NUMERIC_CONSTRAINT]
        markers = {inv.marker for inv in num_invs}

        assert "5 sections" in markers
        assert "150 words" in markers
        assert "99.99%" in markers
        assert "50,000 requests per minute" in markers
        assert "version 4.2" in markers
        for inv in num_invs:
            assert inv.invariant_type == InvariantType.SEMANTIC

    def test_extract_datetime_constraints(self):
        content = "Delivery on 2026-01-15 during Q4 2025 at 14:00 UTC."
        invs = extract_invariants(content, 0, "user")
        dt_invs = [inv for inv in invs if inv.category == EntityCategory.DATETIME_CONSTRAINT]
        markers = {inv.marker for inv in dt_invs}

        assert "2026-01-15" in markers
        assert "Q4 2025" in markers
        assert "14:00 UTC" in markers

    def test_extract_negative_constraints(self):
        content = "Do not restart during peak hours. You must not deploy untested changes."
        invs = extract_invariants(content, 0, "user")
        neg_invs = [inv for inv in invs if inv.category == EntityCategory.NEGATIVE_CONSTRAINT]
        markers = {inv.marker for inv in neg_invs}

        assert any("Do not restart during peak hours" in m for m in markers)
        assert any("must not deploy untested changes" in m for m in markers)

    def test_extract_configuration_values(self):
        content = "Setting enforce_strict_validation=true on PostgreSQL 16 with MAX_RETRIES."
        invs = extract_invariants(content, 0, "user")
        cfg_invs = [inv for inv in invs if inv.category == EntityCategory.CONFIGURATION_VALUE]
        markers = {inv.marker for inv in cfg_invs}

        assert "enforce_strict_validation=true" in markers
        assert "PostgreSQL 16" in markers
        assert "MAX_RETRIES" in markers

    def test_extract_security_compliance(self):
        content = (
            "Must enforce Level-4 compliance with [EXEC-SUMMARY] using JWT tokens, "
            "gRPC, and Phase-2."
        )
        invs = extract_invariants(content, 0, "user")
        sec_invs = [inv for inv in invs if inv.category == EntityCategory.SECURITY_COMPLIANCE]
        markers = {inv.marker for inv in sec_invs}

        assert "Level-4" in markers
        assert "[EXEC-SUMMARY]" in markers
        assert "JWT tokens" in markers
        assert "gRPC" in markers
        assert "Phase-2" in markers


class TestFalsePositiveResistance:
    """Test that ordinary conversational prose is NOT over-classified as invariants."""

    def test_plain_numbers_without_units_are_not_numeric_constraints(self):
        content = "I have 3 cats and 2 dogs. Please see page 42 or chapter 1."
        invs = extract_invariants(content, 0, "user")
        num_invs = [inv for inv in invs if inv.category == EntityCategory.NUMERIC_CONSTRAINT]
        assert len(num_invs) == 0

    def test_numbered_lists_are_not_numeric_constraints(self):
        content = "Step 1: check connection. Step 2: verify logs. Step 3: report findings."
        invs = extract_invariants(content, 0, "user")
        num_invs = [inv for inv in invs if inv.category == EntityCategory.NUMERIC_CONSTRAINT]
        assert len(num_invs) == 0

    def test_ordinary_word_class_is_not_class_identifier(self):
        content = "I took a wonderful class yesterday in introductory biology."
        invs = extract_invariants(content, 0, "user")
        class_invs = [inv for inv in invs if "class" in inv.marker.lower()]
        assert len(class_invs) == 0

    def test_ordinary_slang_def_is_not_function_identifier(self):
        content = "I am def going to attend that meeting tomorrow."
        invs = extract_invariants(content, 0, "user")
        def_invs = [inv for inv in invs if "def" in inv.marker.lower()]
        assert len(def_invs) == 0

    def test_ordinary_word_exception_is_not_error_code(self):
        content = "There is an exception to every general rule."
        invs = extract_invariants(content, 0, "user")
        err_invs = [inv for inv in invs if inv.category == EntityCategory.ERROR_CODE]
        assert len(err_invs) == 0

    def test_ordinary_word_without_is_not_negative_constraint(self):
        content = "I enjoyed coffee without sugar and walked without hesitation."
        invs = extract_invariants(content, 0, "user")
        neg_invs = [inv for inv in invs if inv.category == EntityCategory.NEGATIVE_CONSTRAINT]
        assert len(neg_invs) == 0

    def test_ordinary_word_orders_is_not_table_identifier(self):
        content = "The supervisor gave several orders to the warehouse staff."
        invs = extract_invariants(content, 0, "user")
        id_invs = [inv for inv in invs if inv.marker == "orders"]
        assert len(id_invs) == 0

    def test_ordinary_word_project_is_not_project_identifier(self):
        content = "We are working on a new project for our team."
        invs = extract_invariants(content, 0, "user")
        proj_invs = [inv for inv in invs if "project" in inv.marker.lower()]
        assert len(proj_invs) == 0

    def test_ordinary_word_port_is_not_port_specification(self):
        content = "The historic port was crowded with commercial shipping vessels."
        invs = extract_invariants(content, 0, "user")
        port_invs = [inv for inv in invs if inv.category == EntityCategory.URL_OR_ENDPOINT]
        assert len(port_invs) == 0

    def test_simple_single_char_math_is_not_config(self):
        content = "Let x=1 and y=2."
        invs = extract_invariants(content, 0, "user")
        cfg_invs = [inv for inv in invs if inv.category == EntityCategory.CONFIGURATION_VALUE]
        assert len(cfg_invs) == 0

    def test_url_punctuation_stripping(self):
        content = (
            "Please refer to https://dr.internal.net/v1, and /v2/telemetry. "
            "Also security-ops@acme.corp!"
        )
        invs = extract_invariants(content, 0, "user")
        url_invs = {inv.marker for inv in invs if inv.category == EntityCategory.URL_OR_ENDPOINT}
        assert "https://dr.internal.net/v1" in url_invs
        assert "/v2/telemetry" in url_invs
        assert "security-ops@acme.corp" in url_invs


class TestPreservationClassificationRules:
    """Test role defaults and the core preservation law: 'Contains P1 != Entire unit is P1'."""

    def test_system_role_gets_p0_authority(self):
        analyzer = ContextAnalyzer()
        messages = [
            {
                "role": "system",
                "content": "You are a database specialist on prod-db-01. Follow Level-4.",
            },
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.role == "system"
        assert unit.preservation_class == PreservationClass.P0_AUTHORITY
        assert unit.eligibility.allow_lossless_normalization is True
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False
        assert unit.eligibility.required_validators == ()

    def test_contains_p1_does_not_make_entire_unit_p1(self):
        """CRITICAL PRESERVATION LAW:
        'Please deploy version 4.2 to staging-cluster-01. Do not restart during peak hours. Thanks.'
        Contains P1 version constraint, identifier, and negative constraint,
        BUT the message unit remains P2_COMPRESSIBLE with invariants attached.
        """
        analyzer = ContextAnalyzer()
        messages = [
            {
                "role": "user",
                "content": (
                    "Please deploy version 4.2 to staging-cluster-01. "
                    "Do not restart during peak hours. "
                    "Thanks."
                ),
            }
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]

        # Unit itself is P2_COMPRESSIBLE (NOT P1)
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert unit.structural_type == StructuralType.PROSE

        # Transformation eligibility allows condensation but prohibits removal/truncation
        assert unit.eligibility.allow_lossless_normalization is True
        assert unit.eligibility.allow_meaning_preserving_compression is True
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False
        assert unit.eligibility.required_validators == ()

        # Invariants are extracted and attached to the unit
        assert len(unit.invariants) >= 2
        markers = {inv.marker for inv in unit.invariants}
        assert "staging-cluster-01" in markers
        assert "version 4.2" in markers

    def test_pure_filler_gets_p3_removable(self):
        analyzer = ContextAnalyzer()
        messages = [
            {"role": "user", "content": "Thank you!"},
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.preservation_class == PreservationClass.P3_REMOVABLE
        assert unit.eligibility.allow_removal is True
        assert unit.eligibility.allow_truncation is False
        assert unit.eligibility.required_validators == ()

    def test_code_block_gets_p1_information(self):
        analyzer = ContextAnalyzer()
        messages = [
            {
                "role": "user",
                "content": "```python\ndef compute(x: int) -> int:\n    return x * 2\n```",
            }
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.CODE_PYTHON
        assert unit.preservation_class == PreservationClass.P1_INFORMATION
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False
        assert unit.eligibility.required_validators == ()

    def test_json_block_gets_p1_with_lossless_normalization(self):
        analyzer = ContextAnalyzer()
        messages = [
            {
                "role": "user",
                "content": '{\n  "cluster_id": "us-east-prod-77",\n  "node_count": 12\n}',
            }
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.JSON
        assert unit.preservation_class == PreservationClass.P1_INFORMATION
        # Whitespace minification allowed
        assert unit.eligibility.allow_lossless_normalization is True
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_truncation is False
        assert unit.eligibility.required_validators == ()

    def test_developer_role_gets_p0_authority(self):
        analyzer = ContextAnalyzer()
        messages = [
            {"role": "developer", "content": "Critical developer instructions."},
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.role == "developer"
        assert unit.preservation_class == PreservationClass.P0_AUTHORITY
        assert unit.eligibility.allow_lossless_normalization is True
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

    def test_tool_role_gets_p0_authority(self):
        analyzer = ContextAnalyzer()
        messages = [
            {"role": "tool", "content": '{"result": "success", "rows": 10}'},
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.role == "tool"
        assert unit.preservation_class == PreservationClass.P0_AUTHORITY
        assert unit.eligibility.allow_lossless_normalization is True
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

    def test_ambiguous_markdown_table_gets_p1(self):
        analyzer = ContextAnalyzer()
        messages = [
            {
                "role": "user",
                "content": "| Region | Tier |\n| -- - - - | ---- |\n| US-East | Tier-1 |",
            }
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.MARKDOWN_TABLE
        assert unit.detection_certainty == DetectionCertainty.AMBIGUOUS
        assert unit.preservation_class == PreservationClass.P1_INFORMATION
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False

    def test_ambiguous_syntax_gets_p1_information(self):
        analyzer = ContextAnalyzer()
        messages = [
            {
                "role": "user",
                "content": '{"cluster_id": "us-east-prod-77", "node_count":',
            }
        ]
        pmap = analyzer.analyze(messages)
        unit = pmap.units[0]
        assert unit.detection_certainty == DetectionCertainty.AMBIGUOUS
        assert unit.preservation_class == PreservationClass.P1_INFORMATION
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False


class TestEvaluationCorpusInIsolation:
    """Run ContextAnalyzer against all 12 evaluation corpus cases in isolation."""

    def test_all_12_cases_generate_valid_preservation_maps(self):
        cases = get_core_cases()
        assert len(cases) == 12
        analyzer = ContextAnalyzer()

        for case in cases:
            pmap = analyzer.analyze(case.messages)
            assert isinstance(pmap, PreservationMap)
            assert len(pmap.units) == len(case.messages)

            # Universal invariant: truncation is strictly prohibited across all units
            for unit in pmap.units:
                assert unit.eligibility.allow_truncation is False
                assert unit.start_char is None
                assert unit.end_char is None
                assert unit.eligibility.required_validators == ()

            # Case-specific expectations
            if case.id == "case_01_simple_conversation":
                u1_invs = {inv.marker for inv in pmap.get_invariants_for_message(0)}
                assert "service-auth" in u1_invs
                assert "service-billing" in u1_invs

            elif case.id == "case_02_instruction_heavy":
                assert pmap.units[0].preservation_class == PreservationClass.P0_AUTHORITY
                u0_invs = {inv.marker for inv in pmap.get_invariants_for_message(0)}
                assert "Level-4" in u0_invs
                assert "[EXEC-SUMMARY]" in u0_invs

            elif case.id == "case_03_system_user":
                assert pmap.units[0].preservation_class == PreservationClass.P0_AUTHORITY
                u0_invs = {inv.marker for inv in pmap.get_invariants_for_message(0)}
                assert "PostgreSQL 16" in u0_invs
                assert "prod-db-replica-02" in u0_invs

            elif case.id == "case_04_numeric_constraints":
                u1_invs = {inv.marker for inv in pmap.get_invariants_for_message(1)}
                assert "5 sections" in u1_invs
                assert "150 words" in u1_invs
                assert "Q4 2025" in u1_invs

            elif case.id == "case_05_date_constraints":
                u1_invs = {inv.marker for inv in pmap.get_invariants_for_message(1)}
                assert "2026-01-15" in u1_invs

            elif case.id == "case_06_code":
                assert pmap.units[0].structural_type == StructuralType.CODE_PYTHON
                assert pmap.units[0].detection_certainty == DetectionCertainty.DETECTED
                assert pmap.units[0].preservation_class == PreservationClass.P1_INFORMATION

            elif case.id == "case_07_json":
                assert pmap.units[0].structural_type == StructuralType.JSON
                assert pmap.units[0].detection_certainty == DetectionCertainty.DETECTED
                assert pmap.units[0].preservation_class == PreservationClass.P1_INFORMATION

            elif case.id == "case_08_markdown_table":
                assert pmap.units[0].structural_type == StructuralType.MARKDOWN_TABLE
                assert pmap.units[0].detection_certainty == DetectionCertainty.DETECTED
                assert pmap.units[0].preservation_class == PreservationClass.P1_INFORMATION

            elif case.id == "case_09_rag_context":
                u1_invs = {inv.marker for inv in pmap.get_invariants_for_message(1)}
                assert "[DOC-401]" in u1_invs
                assert "[DOC-402]" in u1_invs
                assert "[DOC-403]" in u1_invs
                assert "/v2/telemetry" in u1_invs

            elif case.id == "case_10_repetitive_patterns":
                u1_invs = {inv.marker for inv in pmap.get_invariants_for_message(1)}
                assert "AUTH-TOKEN-XY99" in u1_invs
                assert "enforce_strict_validation=true" in u1_invs

            elif case.id == "case_11_truncation_risk":
                u0_invs = {inv.marker for inv in pmap.get_invariants_for_message(0)}
                assert "CRITICAL_ALERT_ASSERTION" in u0_invs
                assert "KERN-ERR-0x89AB" in u0_invs


class TestAdversarialStructuralAmbiguityVsInformation:
    """Adversarial tests validating that STRUCTURAL UNCERTAINTY != INFORMATION IMPORTANCE.

    These tests prove that:
    1. Parsing failure / ambiguous fragments do NOT elevate ordinary prose to P1.
    2. Real protected constraints in prose remain attached to P2_COMPRESSIBLE units.
    3. Only content with strong evidence of being intended as structured syntax receives P1.
    """

    def test_case_01_ordinary_prose_containing_unmatched_brace(self):
        """1. Ordinary prose containing an unmatched '{' remains P2_COMPRESSIBLE."""
        analyzer = ContextAnalyzer()
        content = "Please note that { this is just conversational text with an open brace."
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.PROSE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert unit.eligibility.allow_meaning_preserving_compression is True
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

    def test_case_02_ordinary_prose_containing_def_foo(self):
        """2. Ordinary prose containing 'def foo(' remains P2_COMPRESSIBLE."""
        analyzer = ContextAnalyzer()
        content = "In Python, def foo( is an incomplete function definition."
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.PROSE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert unit.eligibility.allow_meaning_preserving_compression is True

    def test_case_03_ordinary_prose_containing_class_yesterday(self):
        """3. Ordinary prose containing 'class yesterday' extracts no invariants and is P2."""
        analyzer = ContextAnalyzer()
        content = "I attended a wonderful biology class yesterday afternoon."
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.PROSE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert len(unit.invariants) == 0

    def test_case_04_phase_2_migration_is_complete(self):
        """4. 'Phase-2 migration is complete' extracts Phase-2 invariant but unit is P2."""
        analyzer = ContextAnalyzer()
        content = "Phase-2 migration is complete."
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.PROSE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert len(unit.invariants) == 1
        assert unit.invariants[0].marker == "Phase-2"
        assert unit.invariants[0].category == EntityCategory.SECURITY_COMPLIANCE
        assert unit.eligibility.allow_meaning_preserving_compression is True

    def test_case_05_tier_1_customer_onboarding(self):
        """5. 'Tier-1 customer onboarding' extracts Tier-1 invariant but unit is P2."""
        analyzer = ContextAnalyzer()
        content = "Tier-1 customer onboarding."
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.PROSE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert len(unit.invariants) == 1
        assert unit.invariants[0].marker == "Tier-1"
        assert unit.invariants[0].category == EntityCategory.SECURITY_COMPLIANCE
        assert unit.eligibility.allow_meaning_preserving_compression is True

    def test_case_06_postgresql_16_mentioned_in_document(self):
        """6. 'PostgreSQL 16 is mentioned in the document' extracts PostgreSQL 16 but unit is P2."""
        analyzer = ContextAnalyzer()
        content = "PostgreSQL 16 is mentioned in the document."
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.PROSE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert len(unit.invariants) == 1
        assert unit.invariants[0].marker == "PostgreSQL 16"
        assert unit.invariants[0].category == EntityCategory.CONFIGURATION_VALUE
        assert unit.eligibility.allow_meaning_preserving_compression is True

    def test_case_07_malformed_json_intended_as_json(self):
        """7. Malformed JSON that clearly appears to be intended as JSON receives P1."""
        analyzer = ContextAnalyzer()
        content = (
            "```json\n"
            "{\n"
            '  "cluster_id": "us-east-prod-77",\n'
            '  "node_count": 12,\n'
            "```"
        )
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.JSON
        assert unit.detection_certainty == DetectionCertainty.AMBIGUOUS
        assert unit.preservation_class == PreservationClass.P1_INFORMATION
        assert unit.eligibility.allow_lossless_normalization is False
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

    def test_case_08_malformed_python_intended_as_python(self):
        """8. Malformed Python that clearly appears to be intended as Python receives P1."""
        analyzer = ContextAnalyzer()
        content = (
            "```python\n"
            "def calculate_total(items):\n"
            "    for item in items\n"
            "        print(item)\n"
            "```"
        )
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.CODE_PYTHON
        assert unit.detection_certainty == DetectionCertainty.AMBIGUOUS
        assert unit.preservation_class == PreservationClass.P1_INFORMATION
        assert unit.eligibility.allow_lossless_normalization is False
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

    def test_case_09_broken_markdown_table(self):
        """9. Broken Markdown table receives P1 protection as an intended table."""
        analyzer = ContextAnalyzer()
        content = (
            "| Region | Tier | SLA |\n"
            "|:---|:---:|\n"
            "| US-East | Tier-1 | 99.9% |"
        )
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.MARKDOWN_TABLE
        assert unit.detection_certainty == DetectionCertainty.AMBIGUOUS
        assert unit.preservation_class == PreservationClass.P1_INFORMATION
        assert unit.eligibility.allow_meaning_preserving_compression is False
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

    def test_case_10_mixed_prose_containing_real_protected_constraint(self):
        """10. Mixed prose containing real protected constraints remains P2 with
        invariants attached.
        """
        analyzer = ContextAnalyzer()
        content = (
            "Please ensure that the system does not exceed 50,000 requests per minute "
            "during the maintenance window. Do not restart during peak hours."
        )
        pmap = analyzer.analyze([{"role": "user", "content": content}])
        unit = pmap.units[0]
        assert unit.structural_type == StructuralType.PROSE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE
        assert unit.eligibility.allow_meaning_preserving_compression is True
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

        markers = {inv.marker for inv in unit.invariants}
        assert "50,000 requests per minute" in markers
        assert any("Do not restart during peak hours" in m for m in markers)


class TestP3RemovalSafetyAndFillerDetection:
    """Tests establishing that short length != removability.

    P3_REMOVABLE requires positive evidence of conversational filler/pleasantries.
    Short content containing decisions, instructions, constraints, or authority
    must never be classified P3 merely because of character count.
    """

    @pytest.mark.parametrize(
        "filler_text",
        [
            "Thanks!",
            "Thank you!",
            "OK.",
            "Okay.",
            "Got it.",
            "Sure.",
            "Great!",
            "Sounds good.",
            "Understood.",
            "Hello!",
            "Hi.",
        ],
    )
    def test_positive_filler_phrases_classified_p3(self, filler_text: str):
        """Positive filler and pleasantry patterns are safely classified as P3_REMOVABLE."""
        analyzer = ContextAnalyzer()
        pmap = analyzer.analyze([{"role": "user", "content": filler_text}])
        unit = pmap.units[0]
        assert unit.preservation_class == PreservationClass.P3_REMOVABLE
        assert unit.eligibility.allow_removal is True
        assert unit.eligibility.allow_truncation is False

    @pytest.mark.parametrize(
        "meaningful_text",
        [
            "Stop.",
            "Don't.",
            "Ship it.",
            "Use prod.",
            "Do not retry.",
            "Approved.",
            "Keep this.",
            "Deploy now.",
            "Yes.",
        ],
    )
    def test_short_meaningful_content_never_classified_p3(self, meaningful_text: str):
        """Short but potentially meaningful instructions/decisions must never be classified P3."""
        analyzer = ContextAnalyzer()
        pmap = analyzer.analyze([{"role": "user", "content": meaningful_text}])
        unit = pmap.units[0]

        # Critical safety contract: Short != Removable
        assert unit.preservation_class != PreservationClass.P3_REMOVABLE
        assert unit.eligibility.allow_removal is False
        assert unit.eligibility.allow_truncation is False

        # In natural prose, these concise operational commands are P2_COMPRESSIBLE
        assert unit.preservation_class == PreservationClass.P2_COMPRESSIBLE


class TestAnalyzerStage:
    """Test AnalyzerStage pipeline integration, contracts, and safety invariants."""

    def test_analyzer_stage_attaches_preservation_map(self):
        """1. AnalyzerStage attaches a valid PreservationMap."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Deploy cluster-prod-01 to port 8080."},
        ]
        config = TokenOptConfig()
        ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        stage = AnalyzerStage(config=config)

        res_ctx = stage(ctx)
        assert res_ctx.preservation_map is not None
        assert isinstance(res_ctx.preservation_map, PreservationMap)

    def test_expected_unit_count_produced(self):
        """2. Expected unit count is produced matching input message count."""
        messages = [
            {"role": "system", "content": "System directive."},
            {"role": "user", "content": "User question."},
            {"role": "assistant", "content": "Assistant answer."},
        ]
        config = TokenOptConfig()
        ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        stage = AnalyzerStage(config=config)

        stage(ctx)
        assert len(ctx.preservation_map.units) == 3

    def test_message_roles_preserved_in_units(self):
        """3. Message roles are preserved correctly across units."""
        messages = [
            {"role": "system", "content": "Rule 1"},
            {"role": "user", "content": "Query 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Query 2"},
        ]
        config = TokenOptConfig()
        ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        stage = AnalyzerStage(config=config)

        stage(ctx)
        expected_roles = ["system", "user", "assistant", "user"]
        actual_roles = [unit.role for unit in ctx.preservation_map.units]
        assert actual_roles == expected_roles

    def test_original_message_content_unchanged(self):
        """4. Original message content is completely unchanged."""
        messages = [
            {"role": "user", "content": "Do not delete this line under any circumstances."},
            {"role": "assistant", "content": "Understood. Maintaining status quo."},
        ]
        messages_snapshot = [dict(m) for m in messages]
        config = TokenOptConfig()
        ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        stage = AnalyzerStage(config=config)

        stage(ctx)
        assert ctx.messages == messages_snapshot
        assert ctx.original_messages == messages_snapshot

    def test_analyzer_stage_returns_same_context_object(self):
        """5. AnalyzerStage returns the identical OptimizationContext object."""
        messages = [{"role": "user", "content": "Hello"}]
        config = TokenOptConfig()
        ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        stage = AnalyzerStage(config=config)

        ret = stage(ctx)
        assert ret is ctx

    def test_pipeline_executes_with_analyzer_stage_present(self):
        """6. Existing pipeline can execute end-to-end with AnalyzerStage present."""
        messages = [
            {"role": "system", "content": "You are a code assistant."},
            {"role": "user", "content": "Please write a function for cluster-99."},
        ]
        config = TokenOptConfig()
        pipeline = OptimizationPipeline(
            [
                AnalyzerStage(config),
                RouterStage(config),
                CompressorStage(config),
                ContextSummarizerStage(config),
            ],
            config,
        )

        ctx = pipeline.run(messages, "gpt-4o")
        assert ctx.preservation_map is not None
        assert "analyzer_latency_ms" in ctx.metrics
        assert "router_latency_ms" in ctx.metrics
        assert "compressor_latency_ms" in ctx.metrics
        assert len(ctx.preservation_map.units) == 2

    def test_analyzer_stage_is_deterministic(self):
        """7. AnalyzerStage produces identical PreservationMap across repeated runs."""
        messages = [
            {"role": "system", "content": "Directive Level-4 [EXEC-SUMMARY]"},
            {"role": "user", "content": "Check node-prod-02 on 2026-03-31 with MAX_RETRIES=5."},
        ]
        config = TokenOptConfig()
        stage = AnalyzerStage(config=config)

        ctx1 = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        stage(ctx1)

        ctx2 = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        stage(ctx2)

        assert ctx1.preservation_map.to_dict() == ctx2.preservation_map.to_dict()

    def test_empty_and_minimal_input_works(self):
        """8. Empty and minimal message lists work gracefully without errors."""
        config = TokenOptConfig()
        stage = AnalyzerStage(config=config)

        # Empty messages
        ctx_empty = OptimizationContext(messages=[], model="gpt-4o", config=config)
        stage(ctx_empty)
        assert ctx_empty.preservation_map is not None
        assert len(ctx_empty.preservation_map.units) == 0
        assert len(ctx_empty.preservation_map.invariants) == 0

        # Minimal single empty message
        ctx_minimal = OptimizationContext(
            messages=[{"role": "user", "content": ""}],
            model="gpt-4o",
            config=config,
        )
        stage(ctx_minimal)
        assert ctx_minimal.preservation_map is not None
        assert len(ctx_minimal.preservation_map.units) == 1

    def test_existing_context_with_none_preservation_map_compatible(self):
        """9. Existing contexts with preservation_map=None remain fully compatible."""
        config = TokenOptConfig()
        ctx = OptimizationContext(
            messages=[{"role": "user", "content": "test"}],
            model="gpt-4o",
            config=config,
            preservation_map=None,
        )
        assert ctx.preservation_map is None
        # Downstream stages should handle preservation_map=None without error
        compressor = CompressorStage(config=config)
        res = compressor.process(ctx)
        assert res.preservation_map is None
        assert res.messages is not None

    def test_analyzer_exception_propagates_naturally(self):
        """10. AnalyzerStage propagates exceptions naturally without custom interception."""
        class ExplodingAnalyzer(ContextAnalyzer):
            def analyze(self, messages):
                raise RuntimeError("Analyzer internal fault")

        config = TokenOptConfig()
        failing_stage = AnalyzerStage(config=config, analyzer=ExplodingAnalyzer())
        ctx = OptimizationContext(
            messages=[{"role": "user", "content": "Important user request"}],
            model="gpt-4o",
            config=config,
        )

        # Direct stage invocation: exception propagates naturally
        with pytest.raises(RuntimeError, match="Analyzer internal fault"):
            failing_stage(ctx)

        # Pipeline invocation: pipeline's pre-existing generic exception handling catches it
        pipeline = OptimizationPipeline([failing_stage, RouterStage(config)], config)
        pipeline_ctx = pipeline.run(
            [{"role": "user", "content": "Important user request"}],
            "gpt-4o",
        )
        assert "analyzer_error" in pipeline_ctx.metrics
        assert pipeline_ctx.messages == [{"role": "user", "content": "Important user request"}]

    def test_analyzer_stage_does_not_modify_token_counts_or_message_content(self):
        """11. AnalyzerStage does not alter message text or token counts."""
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Please deploy service-auth to staging."},
        ]
        config = TokenOptConfig()
        ctx = OptimizationContext(messages=messages, model="gpt-4o", config=config)
        tokens_before = ctx.original_token_count
        messages_before = deepcopy(ctx.messages)

        stage = AnalyzerStage(config=config)
        stage.process(ctx)

        tokens_after = count_message_tokens(ctx.messages, ctx.model)
        assert tokens_after == tokens_before
        assert ctx.messages == messages_before
