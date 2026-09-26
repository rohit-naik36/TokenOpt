"""Corpus of deterministic evaluation cases for TokenOpt prompt compression.

This module defines exactly 12 representative evaluation cases across distinct
prompt categories to benchmark token reduction, preservation of critical
information, truncation damage, and deterministic behavior.

Workload-sensitivity extensions:
- W1 (cases 13-15): repetitive_context_scaling - scaling via conversational history
- W2 (cases 16-18): system_instruction_scaling - scaling via system/instruction context
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


# -------------------------------------------------------------------------
# Workload-sensitivity scaling helpers (W1)
# The fixed task and preservation markers are identical across all three
# sizes; only repetitive conversational history volume changes.
# -------------------------------------------------------------------------
_SCALING_SYSTEM_CONTENT = (
    "You are an enterprise configuration validator tracking deployment "
    "parameters. Preserve binding deployment constraints, identifiers, "
    "security settings, and approved maintenance windows."
)

_SCALING_HISTORY_CYCLE: tuple[tuple[str, str], ...] = (
    ("user", "Thanks, I wanted to confirm the deployment status before we proceed."),
    ("assistant", "Understood. The deployment review is still in progress and the configuration remains under review."),
    ("user", "Okay, understood. Please keep the deployment context available while we continue."),
    ("assistant", "Acknowledged. I will retain the existing deployment context for the next step."),
    ("user", "Thanks for the update. Nothing has changed in the general deployment status."),
    ("assistant", "Noted. The status remains unchanged and the review can continue from the existing context."),
    ("user", "That makes sense. Please continue with the same deployment context."),
    ("assistant", "Understood. The same deployment context remains active for the next verification step."),
)

_SCALING_FIXED_TASK = (
    "Important deployment decisions:\n"
    "- The production deployment is approved only when the configured authentication token "
    "and strict validation setting are preserved.\n"
    "- The target cluster and security policy must remain associated with the approved "
    "maintenance window.\n"
    "- The rollback plan remains available if any binding deployment constraint is violated.\n\n"
    "Critical deployment parameters:\n"
    "AUTH-TOKEN-XY99\n"
    "enforce_strict_validation=true\n"
    "production\n"
    "CLUSTER-ID-7744\n"
    "MW-2026-042\n"
    "SECURITY-POLICY-ALPHA\n"
    "BACKUP-WINDOW-0300-0500\n\n"
    "CRITICAL VERIFICATION REQUIRED: Please verify that AUTH-TOKEN-XY99 is the correct token, "
    "that enforce_strict_validation=true is set for production, and that CLUSTER-ID-7744 with "
    "SECURITY-POLICY-ALPHA is authorized for production deployment under MW-2026-042 during "
    "BACKUP-WINDOW-0300-0500."
)

_SCALING_MARKERS = (
    "AUTH-TOKEN-XY99",
    "enforce_strict_validation=true",
    "production",
    "CLUSTER-ID-7744",
    "MW-2026-042",
    "SECURITY-POLICY-ALPHA",
    "BACKUP-WINDOW-0300-0500",
)


def _build_scaling_messages(repetitions: int) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SCALING_SYSTEM_CONTENT}
    ]
    for i in range(repetitions):
        role, content = _SCALING_HISTORY_CYCLE[i % len(_SCALING_HISTORY_CYCLE)]
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": _SCALING_FIXED_TASK})
    return messages


def _build_scaling_markers(repetitions: int) -> list[ExpectedMarker]:
    final_message_index = repetitions + 1
    return [
        ExpectedMarker(final_message_index, "user", marker)
        for marker in _SCALING_MARKERS
    ]


# -------------------------------------------------------------------------
# Workload-sensitivity scaling helpers (W2)
# The fixed task and preservation markers are identical across all three
# sizes; only system/instruction context volume changes.
# Independent variable: system/instruction context length.
# -------------------------------------------------------------------------
# W2 Scenario: Enterprise Security Policy Compliance Validator
# Critical markers represent binding security identifiers, policy versions,
# regulatory references, and approved configuration values.
_W2_SYSTEM_BASE = (
    "You are an enterprise security policy compliance validator. "
    "Your role is to verify that deployment configurations adhere to "
    "approved security policies, regulatory frameworks, and binding "
    "operational constraints. Preserve all critical identifiers, policy "
    "versions, regulatory references, and approved configuration values "
    "exactly as stated."
)

# Policy documentation blocks that scale the system context
_W2_POLICY_BLOCKS: tuple[str, ...] = (
    # Block 1: Core security policy framework (~400 tokens)
    (
        "\n\n## SECURITY POLICY FRAMEWORK - POL-SEC-2026-001 v3.2\n"
        "This policy governs all production deployment activities across "
        "the enterprise infrastructure. Compliance is mandatory and "
        "continuously audited.\n\n"
        "### 1.1 Authentication & Authorization Requirements\n"
        "All production systems MUST enforce mutual TLS (mTLS) with "
        "certificate rotation every 90 days. The approved certificate "
        "authority is ENT-CA-ROOT-2026. Client certificates must include "
        "the OU=Production, O=Enterprise-Security extension.\n\n"
        "### 1.2 Network Segmentation Policy\n"
        "Production workloads MUST reside in the SEC-ZONE-PROD network "
        "segment (10.44.0.0/16). East-west traffic between tiers is "
        "controlled by SEC-FW-POLICY-ALPHA-v4. Ingress is restricted to "
        "LB-EXT-PROD-01 through LB-EXT-PROD-04 load balancers only.\n\n"
        "### 1.3 Secrets Management Protocol\n"
        "All secrets MUST be stored in VAULT-PROD-CLUSTER under the "
        "path secret/prod/{service}/{environment}. Dynamic secrets with "
        "TTL of 1 hour are required for database credentials. Static "
        "secrets (API keys, certificates) rotate quarterly per "
        "ROT-SCHED-2026-Q3.\n\n"
        "### 1.4 Audit & Observability Mandate\n"
        "All administrative actions MUST generate audit events to "
        "SIEM-LOG-AGGREGATOR with event schema AUDIT-SCHEMA-v2. "
        "Retention is 7 years per REG-COMPLIANCE-SOX-2026. Real-time "
        "alerting on SEC-ALERT-RULESET-CRITICAL is mandatory."
    ),
    # Block 2: Regulatory compliance matrix (~450 tokens)
    (
        "\n\n## REGULATORY COMPLIANCE MATRIX - REG-MATRIX-2026 v1.4\n"
        "Mapping of security controls to regulatory requirements.\n\n"
        "### 2.1 SOX 2026 Controls (REG-SOX-2026)\n"
        "Control SOX-AC-01: Access control reviews quarterly. "
        "Control SOX-CM-03: Change management approval chain requires "
        "SEC-MGR-APPROVAL and CISO-SIGNATURE for production changes. "
        "Control SOX-AU-05: Audit log integrity verified via HMAC-SHA256 "
        "with key AUDIT-HMAC-KEY-2026.\n\n"
        "### 2.2 GDPR Article 32 Controls (REG-GDPR-2026)\n"
        "Control GDPR-DP-01: Data protection impact assessment (DPIA) "
        "required for new processing activities. DPIA reference "
        "DPIA-PROD-DEPLOY-2026-0887. Control GDPR-DS-03: Data subject "
        "requests processed within 30 days via DS-PORTAL-ENT.\n\n"
        "### 2.3 PCI DSS v4.0 Controls (REG-PCI-2026)\n"
        "Control PCI-REQ-03: Cardholder data protection via AES-256-GCM "
        "encryption with key PCI-ENC-KEY-ROT-2026. Control PCI-REQ-10: "
        "Audit trails for all access to cardholder data environment. "
        "Control PCI-REQ-12: Annual policy review per POL-REVIEW-PCI-ANNUAL."
    ),
    # Block 3: Approved configuration baselines (~500 tokens)
    (
        "\n\n## APPROVED CONFIGURATION BASELINES - CFG-BASELINE-PROD v5.1\n"
        "Immutable configuration values for production deployments.\n\n"
        "### 3.1 Kubernetes Security Baseline (K8S-SEC-BASE-v5.1)\n"
        "apiVersion: security.istio.io/v1beta1\n"
        "kind: PeerAuthentication\n"
        "metadata:\n"
        "  name: default\n"
        "  namespace: prod-ns-{service}\n"
        "spec:\n"
        "  mtls:\n"
        "    mode: STRICT\n"
        "---\n"
        "apiVersion: networking.k8s.io/v1\n"
        "kind: NetworkPolicy\n"
        "metadata:\n"
        "  name: deny-all-ingress\n"
        "  namespace: prod-ns-{service}\n"
        "spec:\n"
        "  podSelector: {}\n"
        "  policyTypes: [Ingress]\n"
        "  ingress:\n"
        "  - from:\n"
        "    - namespaceSelector:\n"
        "        matchLabels:\n"
        "          name: ingress-nginx\n"
        "    ports:\n"
        "    - protocol: TCP\n"
        "      port: 8443\n\n"
        "### 3.2 Database Security Configuration (DB-SEC-CFG-v3.0)\n"
        "postgresql.conf overrides:\n"
        "ssl = on\n"
        "ssl_cert_file = '/etc/ssl/certs/ENT-CA-ROOT-2026.crt'\n"
        "ssl_key_file = '/etc/ssl/private/ENT-CA-ROOT-2026.key'\n"
        "ssl_ca_file = '/etc/ssl/certs/ENT-CA-ROOT-2026-ca.crt'\n"
        "password_encryption = scram-sha-256\n"
        "log_connections = on\n"
        "log_disconnections = on\n"
        "log_statement = 'ddl'\n"
        "pgaudit.log = 'all, -misc'\n"
        "pgaudit.log_catalog = off\n\n"
        "### 3.3 Container Runtime Security (CONT-SEC-RUNTIME-v2.3)\n"
        "runtime: crun\n"
        "seccomp_profile: /etc/seccomp/prod-profile.json\n"
        "apparmor_profile: prod-apparmor-profile\n"
        "capabilities: drop=ALL, add=CAP_NET_BIND_SERVICE\n"
        "read_only_root_fs: true\n"
        "run_as_non_root: true\n"
        "run_as_user: 10000\n"
        "fs_group: 10000"
    ),
    # Block 4: Incident response & change procedures (~480 tokens)
    (
        "\n\n## INCIDENT RESPONSE & CHANGE PROCEDURES - PROC-IR-CHANGE v2.7\n"
        "Binding operational procedures for production incidents and changes.\n\n"
        "### 4.1 Incident Response Playbook (IR-PLAYBOOK-PROD-v2.7)\n"
        "SEV-1 Declaration: Requires ONCALL-SEC-LEAD + CISO notification "
        "within 15 minutes via PAGERDUTY-ESCALATION-POLICY-PROD. "
        "War room: SLACK-CHANNEL-#prod-sev1-warroom. "
        "Communication: STATUS-PAGE-ENT-UPDATES every 30 minutes.\n\n"
        "### 4.2 Change Management Workflow (CM-WORKFLOW-PROD-v3.1)\n"
        "All production changes require RFC submission via "
        "JIRA-SM-PJECT-PROD-CHANGE. Approval chain: "
        "TECH-LEAD-APPROVAL -> SEC-MGR-APPROVAL -> CAB-APPROVAL. "
        "Emergency changes (EC) bypass CAB but require POST-EC-REVIEW "
        "within 48 hours. Rollback plan MANDATORY for all changes.\n\n"
        "### 4.3 Deployment Validation Checklist (DEP-VAL-CHECKLIST-v1.9)\n"
        "Pre-deployment: SEC-SCAN-PASS, DEP-SMOKE-TEST-PASS, "
        "CONFIG-DRIFT-CHECK-PASS. Post-deployment: HEALTH-CHECK-PASS, "
        "METRICS-BASELINE-VERIFY, AUDIT-LOG-VERIFY. "
        "Sign-off: DEPLOY-ENGINEER + SEC-OPS-LEAD."
    ),
    # Block 5: Threat model & risk register (~520 tokens)
    (
        "\n\n## THREAT MODEL & RISK REGISTER - THREAT-REG-PROD v4.0\n"
        "Current threat landscape and risk acceptance decisions.\n\n"
        "### 5.1 Identified Threat Vectors (TV-PROD-2026)\n"
        "TV-001: Credential theft via phishing - MITIGATED by "
        "MFA-ENFORCE-POLICY v2.1 (FIDO2 required for prod access). "
        "TV-002: Supply chain compromise - MITIGATED by "
        "SBOM-VERIFY-POLICY (Syft+Grype scan on all images). "
        "TV-003: Insider threat - MONITORED via UEBA-ENGINE-PROD "
        "with RULE-PACK-INSIDER-v3. TV-004: DDoS on ingress - "
        "MITIGATED by CLOUD-ARMOR-PROD-TIER with RULE-SET-DDoS-v4.\n\n"
        "### 5.2 Accepted Risks (RISK-ACC-REG-2026)\n"
        "RISK-ACC-001: Legacy service LEGACY-API-v1 lacks mTLS - "
        "ACCEPTED with compensating control NET-SEG-LEGACY-ZONE, "
        "expires 2026-12-31, owner PLATFORM-TEAM-LEAD. "
        "RISK-ACC-002: Third-party SaaS SAAS-VENDOR-X does not support "
        "SCIM provisioning - ACCEPTED with manual quarterly access "
        "review, owner IDENTITY-TEAM-LEAD.\n\n"
        "### 5.3 Key Risk Indicators (KRI-PROD-2026)\n"
        "KRI-01: Failed auth rate > 5%/5min -> ALERT-SEC-OPS. "
        "KRI-02: Config drift detected -> ALERT-PLATFORM-TEAM. "
        "KRI-03: Certificate expiry < 30 days -> ALERT-PKI-TEAM. "
        "KRI-04: Unapproved change detected -> ALERT-CAB-CHAIR."
    ),
    # Block 6: Vendor & supply chain security (~550 tokens)
    (
        "\n\n## VENDOR & SUPPLY CHAIN SECURITY - VENDOR-SEC-PROD v1.8\n"
        "Third-party risk management and software supply chain controls.\n\n"
        "### 6.1 Approved Vendor Registry (VENDOR-REG-PROD-2026)\n"
        "VENDOR-001: CLOUD-PROVIDER-AWS - Contract AWS-ENT-AGMT-2026, "
        "SOC2-Type2 current, PCI-AOC current, renewal 2027-03-15. "
        "VENDOR-002: MONITORING-DATADOG - Contract DD-ENT-AGMT-2025, "
        "SOC2-Type2 current, renewal 2026-11-30. "
        "VENDOR-003: SECRETS-HASHICORP - Contract HC-ENT-AGMT-2026, "
        "SOC2-Type2 current, FIPS-140-2 validated, renewal 2027-06-01. "
        "VENDOR-004: CI-CD-GITHUB - Contract GH-ENT-AGMT-2026, "
        "SOC2-Type2 current, SLSA-Level3, renewal 2027-01-20.\n\n"
        "### 6.2 Software Supply Chain Controls (SSC-POLICY-PROD-v1.8)\n"
        "All container images MUST be built via BUILD-PIPELINE-PROD "
        "with SLSA-Level3 provenance. Base images from REGISTRY-APPROVED-"
        "BASE (distroless, wolfi, chainguard only). Dependency scanning "
        "via DEP-SCAN-TRIVY v0.48+ with POLICY-DEP-CRITICAL-BLOCK. "
        "SBOM generation mandatory (SPDX 2.3 format) stored in "
        "SBOM-REPOSITORY-PROD. Admission control via POLICY-SIGSTORE-"
        "VERIFY with ROOT-CA-SIGSTORE-ENT.\n\n"
        "### 6.3 Open Source Governance (OSS-GOV-PROD-v1.2)\n"
        "License allowlist: Apache-2.0, MIT, BSD-3-Clause, ISC. "
        "License denylist: GPL-3.0, AGPL-3.0, SSPL-1.0. "
        "Vulnerability SLA: CRITICAL 48h, HIGH 7d, MEDIUM 30d, "
        "LOW 90d per VULN-SLA-PROD-2026. Exception process via "
        "OSS-EXCEPTION-REQUEST-JIRA with SEC-ARCH-REVIEW."
    ),
)

_W2_FIXED_TASK = (
    "\n\n## COMPLIANCE VERIFICATION TASK\n"
    "Verify the following production deployment configuration for "
    "service PAYMENT-GATEWAY-SVC against the binding policies above.\n\n"
    "DEPLOYMENT SPECIFICATION:\n"
    "- Service: PAYMENT-GATEWAY-SVC\n"
    "- Namespace: prod-ns-payment-gateway\n"
    "- Image: registry.internal/payment-gateway:v2.4.1-sha.abc123\n"
    "- Replicas: 6 (min 4, max 12 via HPA)\n"
    "- Resources: CPU 2000m/4000m, Memory 4Gi/8Gi\n"
    "- Ingress: LB-EXT-PROD-02, TLS termination, mTLS backend\n"
    "- Database: PostgreSQL 16 on DB-PROD-CLUSTER-01, scram-sha-256\n"
    "- Secrets: VAULT-PROD-CLUSTER path secret/prod/payment-gateway/prod\n"
    "- Monitoring: DATADOG-APM, PROMETHEUS-SCRAPE, SIEM-LOG-AGGREGATOR\n\n"
    "CRITICAL VERIFICATION REQUIRED: Confirm that the deployment uses "
    "ENT-CA-ROOT-2026 for mTLS, enforces STRICT mode PeerAuthentication, "
    "references POL-SEC-2026-001 v3.2, complies with REG-SOX-2026 "
    "SOX-AC-01 and SOX-CM-03, uses VAULT-PROD-CLUSTER for secrets, "
    "and has ROLLBACK-PLAN-MANDATORY per CM-WORKFLOW-PROD-v3.1. "
    "Verify DPIA reference DPIA-PROD-DEPLOY-2026-0887 is documented. "
    "Confirm SEV-1 escalation via PAGERDUTY-ESCALATION-POLICY-PROD "
    "and SLACK-CHANNEL-#prod-sev1-warroom."
)

_W2_CRITICAL_MARKERS = (
    "ENT-CA-ROOT-2026",
    "POL-SEC-2026-001 v3.2",
    "SEC-ZONE-PROD",
    "VAULT-PROD-CLUSTER",
    "REG-SOX-2026",
    "SOX-AC-01",
    "SOX-CM-03",
    "DPIA-PROD-DEPLOY-2026-0887",
    "PAGERDUTY-ESCALATION-POLICY-PROD",
    "SLACK-CHANNEL-#prod-sev1-warroom",
    "ROLLBACK-PLAN-MANDATORY",
    "PAYMENT-GATEWAY-SVC",
    "prod-ns-payment-gateway",
    "DB-PROD-CLUSTER-01",
    "LB-EXT-PROD-02",
)


def _build_w2_messages(policy_block_count: int) -> list[dict[str, Any]]:
    """Build W2 messages with specified number of policy blocks in system context."""
    system_content = _W2_SYSTEM_BASE
    for i in range(policy_block_count):
        system_content += _W2_POLICY_BLOCKS[i % len(_W2_POLICY_BLOCKS)]
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": _W2_FIXED_TASK},
    ]


def _build_w2_markers() -> list[ExpectedMarker]:
    """Build W2 expected markers - all in the final user message (index 1)."""
    return [
        ExpectedMarker(1, "user", marker)
        for marker in _W2_CRITICAL_MARKERS
    ]


# -------------------------------------------------------------------------
# Evaluation Cases
# -------------------------------------------------------------------------
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
                    "    Would you please ensure that enforce_strict_validation=true "
                    "is set for production?"
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
    # -------------------------------------------------------------------------
    # 13-15. repetitive_context_scaling (W1)
    # Controlled workload scaling: same task and critical information,
    # with only repetitive conversational history volume changing.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_13_repetitive_500",
        category="repetitive_context_scaling",
        description="Repetitive conversational history targeting approximately 500 tokens.",
        messages=_build_scaling_messages(
            14,
        ),
        expected_preserved=_build_scaling_markers(
            14,
        ),
    ),
    EvaluationCase(
        id="case_14_repetitive_2000",
        category="repetitive_context_scaling",
        description="Repetitive conversational history targeting approximately 2,000 tokens.",
        messages=_build_scaling_messages(
            91,
        ),
        expected_preserved=_build_scaling_markers(
            91,
        ),
    ),
    EvaluationCase(
        id="case_15_repetitive_8000",
        category="repetitive_context_scaling",
        description="Repetitive conversational history targeting approximately 8,000 tokens.",
        messages=_build_scaling_messages(
            397,
        ),
        expected_preserved=_build_scaling_markers(
            397,
        ),
    ),
    # -------------------------------------------------------------------------
    # 16-18. system_instruction_scaling (W2)
    # Controlled workload scaling: same task and critical information,
    # with only system/instruction context volume changing.
    # Independent variable: system/instruction context length.
    # -------------------------------------------------------------------------
    EvaluationCase(
        id="case_16_system_500",
        category="system_instruction_scaling",
        description="System/instruction context scaling targeting approximately 500 tokens.",
        messages=_build_w2_messages(0),
        expected_preserved=_build_w2_markers(),
    ),
    EvaluationCase(
        id="case_17_system_2000",
        category="system_instruction_scaling",
        description="System/instruction context scaling targeting approximately 2,000 tokens.",
        messages=_build_w2_messages(5),
        expected_preserved=_build_w2_markers(),
    ),
    EvaluationCase(
        id="case_18_system_8000",
        category="system_instruction_scaling",
        description="System/instruction context scaling targeting approximately 8,000 tokens.",
        messages=_build_w2_messages(22),
        expected_preserved=_build_w2_markers(),
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


def get_core_cases() -> list[EvaluationCase]:
    """Return the original 12-case regression corpus."""
    return [
        case
        for case in CASES
        if case.category not in ("repetitive_context_scaling", "system_instruction_scaling")
    ]
