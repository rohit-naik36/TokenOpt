"""Corpus of deterministic evaluation cases for TokenOpt prompt compression.

This module defines exactly 12 representative evaluation cases across distinct
prompt categories to benchmark token reduction, preservation of critical
information, truncation damage, and deterministic behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExpectedMarker:
    """Specification of an expected marker associated with a specific message role and index.

    Attributes:
        message_index: 0-indexed position of the message in the conversation.
        role: Expected message role ('system', 'user', or 'assistant').
        marker: Concrete text substring that must survive in the designated message.
    """

    message_index: int
    role: str
    marker: str

    def to_dict(self) -> dict[str, Any]:
        """Convert marker specification to JSON-serializable dictionary."""
        return {
            "message_index": self.message_index,
            "role": self.role,
            "marker": self.marker,
        }


@dataclass(frozen=True)
class EvaluationCase:
    """Evaluation case specification for prompt compression benchmarking.

    Attributes:
        id: Unique case identifier.
        category: Benchmark category.
        messages: List of chat message dictionaries with 'role' and 'content'.
        expected_preserved: Role-specific markers that must survive compression.
        description: Brief explanation of the case scenario.
    """

    id: str
    category: str
    messages: list[dict[str, Any]]
    expected_preserved: list[ExpectedMarker] = field(default_factory=list)
    description: str = ""


CASES: list[EvaluationCase] = [
    # -------------------------------------------------------------------------
    # 1. simple_conversation
    # Multi-turn conversational exchange with polite filler and service context.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_01_simple_conversation",
        category="simple_conversation",
        description="Multi-turn dialogue with polite pleasantries and microservice deployment details.",
        messages=[
            {
                "role": "user",
                "content": (
                    "Hello! Could you please help me understand the deployment architecture "
                    "for project Apollo? I basically need to know how service-auth communicates "
                    "with service-billing."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Project Apollo uses gRPC for inter-service communication. "
                    "Service-auth issues signed JWT tokens that service-billing verifies using a shared public key."
                ),
            },
            {
                "role": "user",
                "content": (
                    "I think that makes sense. Would you please clarify if port 8443 "
                    "is used for TLS termination on service-billing?"
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(0, "user", "project Apollo"),
            ExpectedMarker(0, "user", "service-auth"),
            ExpectedMarker(0, "user", "service-billing"),
            ExpectedMarker(1, "assistant", "gRPC"),
            ExpectedMarker(1, "assistant", "JWT tokens"),
            ExpectedMarker(2, "user", "port 8443"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 2. instruction_heavy
    # Explicit negative constraints, formatting guidelines, and policy levels.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_02_instruction_heavy",
        category="instruction_heavy",
        description="Structured system directives imposing formatting limits and security classifications.",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an executive report generator. Follow these strict rules:\n"
                    "Rule 1: Always enforce Level-4 security compliance.\n"
                    "Rule 2: Limit output to exactly 3 bullet points.\n"
                    "Rule 3: Begin response with [EXEC-SUMMARY]."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Please kindly prepare the brief for the infrastructure migration. "
                    "I believe we must address cloud security."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Understood. I will follow Level-4 guidelines and generate "
                    "3 bullet points under [EXEC-SUMMARY]."
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(0, "system", "Level-4"),
            ExpectedMarker(0, "system", "3 bullet points"),
            ExpectedMarker(0, "system", "[EXEC-SUMMARY]"),
            ExpectedMarker(1, "user", "infrastructure migration"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 3. system_user
    # Explicit system persona and database maintenance query with identifiers.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_03_system_user",
        category="system_user",
        description="System role setting database target coupled with specific user maintenance request.",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a database specialist for PostgreSQL 16 on target cluster prod-db-replica-02."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Would you please check customer_orders for index idx_orders_customer_id "
                    "before maintenance MW-88?"
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(0, "system", "PostgreSQL 16"),
            ExpectedMarker(0, "system", "prod-db-replica-02"),
            ExpectedMarker(1, "user", "customer_orders"),
            ExpectedMarker(1, "user", "idx_orders_customer_id"),
            ExpectedMarker(1, "user", "MW-88"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 4. numeric_constraints
    # Quantitative performance indicators, counts, and financial thresholds.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_04_numeric_constraints",
        category="numeric_constraints",
        description="Performance review request with explicit numerical metrics, sections, and word counts.",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an editorial and financial assistant tracking report requirements."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Please kindly structure the Q4 2025 review into 5 sections with "
                    "approximately 150 words each."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Understood. Formatting Q4 2025 analysis into 5 sections with "
                    "150 words per section."
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(1, "user", "5 sections"),
            ExpectedMarker(1, "user", "150 words"),
            ExpectedMarker(1, "user", "Q4 2025"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 5. date_constraints
    # Milestone schedules with ISO dates and phase identifiers.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_05_date_constraints",
        category="date_constraints",
        description="Project launch schedule governed by binding contractual milestone dates.",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a scheduling coordinator tracking contractual milestones."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Would you please verify the launch window for Phase-2? "
                    "The agreement requires delivery on 2026-01-15."
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Confirmed. Phase-2 milestone is scheduled for delivery on 2026-01-15."
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(1, "user", "Phase-2"),
            ExpectedMarker(1, "user", "2026-01-15"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 6. code
    # Python source code with class declaration, methods, and error handling.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_06_code",
        category="code",
        description="Python class implementation with rate limiting and exception handling.",
        messages=[
            {
                "role": "user",
                "content": (
                    "Please review this Python implementation:\n\n"
                    "class PaymentGatewayClient:\n"
                    "    MAX_RETRIES = 3\n"
                    "    def process_payment(self, amount: float) -> bool:\n"
                    "        if amount <= 0.0:\n"
                    "            raise ValueError(\"Invalid amount\")\n"
                    "        return True\n\n"
                    "Could you verify the error handling?"
                ),
            }
        ],
        expected_preserved=[
            ExpectedMarker(0, "user", "class PaymentGatewayClient"),
            ExpectedMarker(0, "user", "MAX_RETRIES"),
            ExpectedMarker(0, "user", "def process_payment"),
            ExpectedMarker(0, "user", 'raise ValueError("Invalid amount")'),
        ],
    ),
    # -------------------------------------------------------------------------
    # 7. json
    # Structured JSON object payload with schema keys and critical values.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_07_json",
        category="json",
        description="Infrastructure configuration payload serialized as JSON.",
        messages=[
            {
                "role": "user",
                "content": (
                    "Please parse this configuration payload:\n\n"
                    "{\n"
                    '  "cluster_id": "us-east-prod-77",\n'
                    '  "node_count": 12,\n'
                    '  "auto_scaling": true,\n'
                    '  "instance_type": "c6i.2xlarge",\n'
                    '  "primary_zone": "us-east-1a",\n'
                    '  "failover_endpoint": "https://dr.internal.net/v1"\n'
                    "}\n\n"
                    "Could you check node_count?"
                ),
            }
        ],
        expected_preserved=[
            ExpectedMarker(0, "user", '"cluster_id": "us-east-prod-77"'),
            ExpectedMarker(0, "user", '"node_count": 12'),
            ExpectedMarker(0, "user", '"failover_endpoint": "https://dr.internal.net/v1"'),
        ],
    ),
    # -------------------------------------------------------------------------
    # 8. markdown_table
    # Formatted markdown table with SLA targets, regions, and status values.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_08_markdown_table",
        category="markdown_table",
        description="Regional SLA availability report formatted as a Markdown table.",
        messages=[
            {
                "role": "user",
                "content": (
                    "Please inspect the SLA status table below:\n\n"
                    "| Region | Tier | SLA Target | Actual Availability | Status |\n"
                    "|:---|:---:|:---:|:---:|:---|\n"
                    "| US-East | Tier-1 | 99.99% | 99.995% | Compliant |\n"
                    "| EU-Central | Tier-2 | 99.90% | 99.850% | Breach |\n"
                    "| AP-South | Tier-1 | 99.99% | 99.992% | Compliant |\n\n"
                    "Could you identify which region had the SLA Breach?"
                ),
            }
        ],
        expected_preserved=[
            ExpectedMarker(0, "user", "| Region | Tier | SLA Target | Actual Availability | Status |"),
            ExpectedMarker(0, "user", "US-East"),
            ExpectedMarker(0, "user", "EU-Central"),
            ExpectedMarker(0, "user", "Breach"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 9. rag_context
    # Retrieved document passages containing citation tags and factual claims.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_09_rag_context",
        category="rag_context",
        description="Technical documentation snippets with explicit document IDs and API constraints.",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a technical question-answering assistant. Base answers only on provided documents."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Reference Documents:\n"
                    "[DOC-401]: The ACME gateway uses OAuth 2.0 with mTLS for endpoint /v2/telemetry.\n"
                    "[DOC-402]: Rate limits for tier Platinum are set to 50,000 requests per minute.\n"
                    "[DOC-403]: Incident response requires Sev-1 notification to security-ops@acme.corp within 15 minutes.\n\n"
                    "What is the notification requirement in DOC-403?"
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(1, "user", "[DOC-401]"),
            ExpectedMarker(1, "user", "[DOC-402]"),
            ExpectedMarker(1, "user", "[DOC-403]"),
            ExpectedMarker(1, "user", "/v2/telemetry"),
            ExpectedMarker(1, "user", "50,000 requests per minute"),
            ExpectedMarker(1, "user", "security-ops@acme.corp"),
            ExpectedMarker(1, "user", "15 minutes"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 10. repetitive_context
    # Excessive newline spacing and repeated conversational fillers.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_10_repetitive_context",
        category="repetitive_context",
        description="Prompt containing excessive whitespace and multiple filler phrases around critical tokens.",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a configuration validator tracking deployment parameters."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Please kindly note that we basically need to verify the following.\n\n\n\n\n"
                    "I believe the token is AUTH-TOKEN-XY99.\n\n\n\n"
                    "    Would you please ensure that enforce_strict_validation=true is set?"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Understood. Verifying AUTH-TOKEN-XY99 and enforce_strict_validation=true for production."
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(1, "user", "AUTH-TOKEN-XY99"),
            ExpectedMarker(1, "user", "enforce_strict_validation=true"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 11. truncation_risk
    # Long prompt with critical assertion placed at the very end.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_11_truncation_risk",
        category="truncation_risk",
        description="Lengthy diagnostic log where naive truncation risks dropping terminal critical alerts.",
        messages=[
            {
                "role": "user",
                "content": (
                    "System telemetry audit log section 1: Normal operating parameters observed "
                    "across cluster node-01 through node-20. CPU load average 22.4%, memory utilization 41.2%, "
                    "network ingress 1.2 Gbps. All diagnostic checks passed for background worker threads. "
                    "Periodic health probe returned status code 200 OK. Standard maintenance tasks executed "
                    "without deviation from standard operating procedure.\n\n"
                    "CRITICAL_ALERT_ASSERTION: Node-99 entered fatal panic state with kernel error "
                    "KERN-ERR-0x89AB. Immediate failover required."
                ),
            }
        ],
        expected_preserved=[
            ExpectedMarker(0, "user", "System telemetry audit log"),
            ExpectedMarker(0, "user", "CRITICAL_ALERT_ASSERTION"),
            ExpectedMarker(0, "user", "KERN-ERR-0x89AB"),
        ],
    ),
    # -------------------------------------------------------------------------
    # 12. minimal_compression
    # Dense, non-redundant SQL statement with zero filler words.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_12_minimal_compression",
        category="minimal_compression",
        description="Dense structured SQL query with no conversational filler or excessive whitespace.",
        messages=[
            {
                "role": "system",
                "content": "You are a database query analyzer.",
            },
            {
                "role": "user",
                "content": (
                    "SELECT order_id, customer_id, total_amount "
                    "FROM orders WHERE status = 'SHIPPED';"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "Query confirmed: targeting orders table with status filter."
                ),
            },
        ],
        expected_preserved=[
            ExpectedMarker(1, "user", "SELECT order_id, customer_id, total_amount"),
            ExpectedMarker(1, "user", "FROM orders WHERE status = 'SHIPPED';"),
        ],
    ),
]


def get_cases() -> list[EvaluationCase]:
    """Return all defined evaluation cases."""
    return list(CASES)


def get_case_by_id(case_id: str) -> EvaluationCase | None:
    """Return a single evaluation case by its unique ID."""
    for case in CASES:
        if case.id == case_id:
            return case
    return None
