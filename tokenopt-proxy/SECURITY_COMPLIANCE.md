# TokenOpt Enterprise — Security & Compliance Guide
## Policies, Procedures, and Technical Controls

**Version:** 2.0.0  
**Classification:** Confidential  
**Owner:** Security & Compliance Team

---

## 1. Security Architecture

### 1.1 Defense in Depth

TokenOpt implements security controls at every layer:

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 7: Application Security                                │
│  • Input validation, output encoding, JWT auth, RBAC         │
├─────────────────────────────────────────────────────────────┤
│  Layer 6: API Gateway Security                                │
│  • Rate limiting, WAF, DDoS protection, TLS termination      │
├─────────────────────────────────────────────────────────────┤
│  Layer 5: Container Security                                  │
│  • Non-root users, read-only filesystems, seccomp profiles   │
├─────────────────────────────────────────────────────────────┤
│  Layer 4: Orchestration Security                              │
│  • Network policies, pod security standards, RBAC           │
├─────────────────────────────────────────────────────────────┤
│  Layer 3: Network Security                                    │
│  • VPC isolation, security groups, private subnets, NAT       │
├─────────────────────────────────────────────────────────────┤
│  Layer 2: Host Security                                       │
│  • Encrypted EBS, minimal AMIs, automated patching           │
├─────────────────────────────────────────────────────────────┤
│  Layer 1: Physical & Infrastructure Security                  │
│  • AWS data center security, IAM, KMS, CloudTrail            │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Threat Model

| Threat | Likelihood | Impact | Mitigation |
|--------|-----------|--------|------------|
| Unauthorized API access | Medium | High | JWT auth, rate limiting, audit logging |
| Prompt injection | Medium | Medium | Input validation, content filtering |
| Data exfiltration | Low | Critical | Encryption, network policies, DLP |
| DDoS attack | Medium | Medium | WAF, rate limiting, auto-scaling |
| Insider threat | Low | High | RBAC, audit logs, least privilege |
| Supply chain attack | Low | Critical | SBOM scanning, signed images, dependency scanning |
| Provider API key compromise | Low | Critical | Secrets Manager, rotation, monitoring |

---

## 2. Authentication & Authorization

### 2.1 JWT Token Specification

**Algorithm:** HS256 (HMAC with SHA-256)

**Token Structure:**
```json
{
  "header": {
    "alg": "HS256",
    "typ": "JWT"
  },
  "payload": {
    "tenant_id": "engineering",
    "sub": "user@company.com",
    "roles": ["user"],
    "plan": "enterprise",
    "iat": 1721782800,
    "exp": 1729549200,
    "jti": "unique-token-id"
  }
}
```

**Validation Rules:**
- Signature verified against `JWT_SECRET`
- `exp` must be in the future
- `iat` must be in the past (with 5-minute clock skew tolerance)
- `tenant_id` must be active in database
- `jti` not in revocation blacklist

### 2.2 Role-Based Access Control (RBAC)

| Role | API Calls | Stats | Audit Logs | Config | Admin Panel |
|------|-----------|-------|------------|--------|-------------|
| `user` | ✅ Own tenant | ✅ Own tenant | ❌ | ❌ | ❌ |
| `admin` | ✅ All tenants* | ✅ All tenants | ✅ All tenants | ✅ Own tenant | ✅ |
| `super_admin` | ✅ All tenants | ✅ All tenants | ✅ All tenants | ✅ All tenants | ✅ |

*Subject to tenant isolation

### 2.3 Token Lifecycle

**Generation:**
```bash
# Admin generates token via CLI or admin panel
jwt encode --secret "$JWT_SECRET" --exp="+90d" '{
  "tenant_id": "engineering",
  "sub": "user@company.com",
  "roles": ["user"],
  "plan": "enterprise"
}'
```

**Rotation:**
- Standard rotation: Every 90 days
- Emergency rotation: Immediate (all existing tokens invalidated)
- Grace period: 24 hours (old secret accepted during rotation)

**Revocation:**
- Immediate: Add `jti` to Redis blacklist (TTL = token expiration)
- Bulk: Rotate `JWT_SECRET` (invalidates all tokens)

---

## 3. Data Protection

### 3.1 Encryption Standards

| Data State | Algorithm | Key Size | Key Management |
|------------|-----------|----------|----------------|
| Data in transit (external) | TLS 1.3 | 256-bit | Let's Encrypt / ACM |
| Data in transit (internal) | TLS 1.3 | 256-bit | Internal CA |
| Data at rest (EBS) | AES-256-XTS | 256-bit | AWS KMS CMK |
| Data at rest (RDS) | AES-256 | 256-bit | AWS KMS CMK |
| Data at rest (Redis) | AES-256 | 256-bit | AWS KMS CMK |
| Application secrets | AES-256-GCM | 256-bit | AWS Secrets Manager |
| Cache data | AES-256-GCM | 256-bit | Environment variable |
| Backup data | AES-256 | 256-bit | AWS KMS CMK |

### 3.2 Key Management

**AWS KMS Configuration:**
- Customer-managed keys (CMK) for all encryption
- Key rotation: Automatic annually
- Key deletion: 30-day waiting period
- Access logging: CloudTrail for all key usage

**Key Hierarchy:**
```
KMS Root Key (AWS managed)
  └── TokenOpt CMK (customer managed)
        ├── EBS Encryption Key
        ├── RDS Encryption Key
        ├── Redis Encryption Key
        ├── Secrets Manager Key
        └── S3 Backup Encryption Key
```

### 3.3 Data Classification

| Classification | Examples | Handling |
|----------------|----------|----------|
| **Public** | API documentation, marketing materials | No restrictions |
| **Internal** | Architecture diagrams, runbooks | Need-to-know basis |
| **Confidential** | Audit logs, tenant configs | Encrypted, access logged |
| **Restricted** | JWT secrets, provider API keys | HSM-protected, dual-control |

### 3.4 Data Retention & Deletion

**Retention Schedule:**

| Data Type | Retention Period | Archive Location | Deletion Method |
|-----------|-----------------|-------------------|-----------------|
| Audit logs | 90 days | S3 (Parquet) | Automatic after 2 years |
| Optimization stats | 1 year | S3 (CSV) | Automatic after 3 years |
| Rollback logs | 1 year | S3 | Automatic after 2 years |
| Tenant configs | Indefinite | — | On tenant deletion |
| Prompt templates | Indefinite | — | On template deletion |
| JWT tokens | Token lifetime | — | Automatic at expiration |

**GDPR Right to Deletion:**
```bash
# Delete all data for a tenant
DELETE FROM audit_logs WHERE tenant_id = 'tenant-to-delete';
DELETE FROM optimization_stats WHERE tenant_id = 'tenant-to-delete';
DELETE FROM tenant_configs WHERE tenant_id = 'tenant-to-delete';
# Redis keys
DEL rate_limit:tenant-to-delete:*
DEL cache:*:tenant-to-delete:*
```

---

## 4. Network Security

### 4.1 VPC Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         AWS Cloud                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  VPC: 10.0.0.0/16                                   │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │    │
│  │  │ Public Subnet│  │ Private Subnet│  │ Database │  │    │
│  │  │ 10.0.101.0/24│  │ 10.0.1.0/24  │  │ 10.0.201.0/24│  │    │
│  │  │              │  │              │  │          │  │    │
│  │  │ • ALB        │  │ • EKS Nodes  │  │ • RDS    │  │    │
│  │  │ • NAT Gateway│  │ • TokenOpt   │  │ • Redis  │  │    │
│  │  │ • Bastion    │  │ • Monitoring │  │          │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────┘  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Security Groups

**TokenOpt Proxy Security Group:**
| Direction | Protocol | Port | Source | Description |
|-----------|----------|------|--------|-------------|
| Ingress | TCP | 8000 | ALB SG | Application traffic |
| Egress | TCP | 5432 | RDS SG | Database access |
| Egress | TCP | 6379 | Redis SG | Cache access |
| Egress | TCP | 443 | 0.0.0.0/0 | Provider APIs |
| Egress | TCP | 9092 | Kafka SG | Event streaming |

### 4.3 Network Policies (Kubernetes)

```yaml
# Deny all ingress by default
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
  namespace: tokenopt
spec:
  podSelector: {}
  policyTypes:
    - Ingress

# Allow ingress from ingress-nginx only
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-ingress-nginx
  namespace: tokenopt
spec:
  podSelector:
    matchLabels:
      app.kubernetes.io/name: tokenopt
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000
```

### 4.4 AWS WAF Rules

**WebACL Configuration:**

| Rule | Priority | Action |
|------|----------|--------|
| Rate Limiting | 1 | Block (2000 req/5min per IP) |
| SQL Injection | 2 | Block |
| XSS Protection | 3 | Block |
| AWS Managed Rules (Common) | 4 | Block |
| Geo-blocking (optional) | 5 | Block |
| Custom IP Allowlist | 6 | Allow |

---

## 5. Container Security

### 5.1 Dockerfile Security

**Best Practices Implemented:**
- Multi-stage builds (minimal attack surface)
- Non-root user (`USER tokenopt`)
- Read-only root filesystem
- Distroless base image for production
- No secrets in layers
- Health checks defined
- Security scanning in CI/CD

### 5.2 Pod Security Standards

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: tokenopt-proxy
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: tokenopt
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop:
            - ALL
      resources:
        limits:
          cpu: "2000m"
          memory: "2Gi"
```

### 5.3 Image Security

**Scanning Pipeline:**
1. **Build-time:** Trivy scans base image and layers
2. **Registry:** ECR image scanning (Clair)
3. **Runtime:** Falco detects anomalous container behavior
4. **Weekly:** Snyk dependency scanning

**Signing:**
- Images signed with Cosign
- Verification required before deployment
- Key stored in AWS KMS

---

## 6. Secret Management

### 6.1 Secret Lifecycle

```
Generation → Storage → Distribution → Usage → Rotation → Destruction
```

**Generation:**
- Cryptographically random (OpenSSL / Python secrets)
- Minimum entropy: 128 bits

**Storage:**
- AWS Secrets Manager (primary)
- Kubernetes Secrets (ephemeral, for pod startup only)
- Environment variables (never for production secrets)

**Distribution:**
- IAM roles for AWS service access
- Kubernetes ServiceAccounts for in-cluster access
- Sealed Secrets for GitOps workflows

**Rotation:**
- Automated: AWS Secrets Manager rotation Lambda
- Manual: Emergency rotation via admin CLI
- Dual-key period: 24 hours during rotation

### 6.2 Provider API Key Security

**Storage:**
```bash
# Store in Secrets Manager
aws secretsmanager create-secret   --name tokenopt/openai-api-key   --secret-string "sk-..."   --kms-key-id alias/tokenopt-secrets
```

**Access:**
```bash
# Pod retrieves secret via IAM role
aws secretsmanager get-secret-value   --secret-id tokenopt/openai-api-key
```

**Rotation Schedule:**
- OpenAI keys: Monthly
- Azure keys: Monthly
- Anthropic keys: Monthly
- JWT secrets: Quarterly

### 6.3 Encryption Key Rotation

**Process:**
1. Generate new key
2. Re-encrypt data with new key
3. Update application configuration
4. Verify functionality
5. Mark old key for deletion (30-day grace)

---

## 7. Audit & Logging

### 7.1 Audit Log Schema

```json
{
  "timestamp": "2026-07-24T00:00:00Z",
  "event_type": "api_request",
  "severity": "INFO",
  "tenant_id": "engineering",
  "user_id": "user@company.com",
  "request_id": "uuid-v4",
  "source_ip": "192.168.1.1",
  "user_agent": "python-requests/2.31.0",
  "method": "POST",
  "path": "/v1/chat/completions",
  "status_code": 200,
  "duration_ms": 320,
  "optimization": {
    "original_tokens": 42,
    "optimized_tokens": 24,
    "savings_pct": 42.5,
    "fidelity_score": 0.9978,
    "techniques": ["filler_removal", "semantic_compression"]
  },
  "provider": "openai",
  "model": "gpt-4",
  "cost": {
    "original": 0.00126,
    "optimized": 0.00072,
    "savings": 0.00054
  }
}
```

### 7.2 Log Retention

| Log Type | Retention | Storage |
|----------|-----------|---------|
| Application logs | 30 days | CloudWatch Logs |
| Audit logs | 90 days | S3 (encrypted) |
| Access logs (ALB) | 90 days | S3 |
| CloudTrail | 1 year | S3 |
| VPC Flow Logs | 30 days | CloudWatch Logs |

### 7.3 SIEM Integration

**Splunk Integration:**
```bash
# Forward CloudWatch Logs to Splunk
aws logs put-subscription-filter   --log-group-name /aws/tokenopt/application   --filter-name splunk-forwarder   --filter-pattern ""   --destination-arn arn:aws:lambda:us-east-1:account:function:splunk-forwarder
```

**Alert Rules:**
- Unauthorized access attempts (>5 failures in 1 minute)
- Privilege escalation (admin actions from non-admin roles)
- Data exfiltration (large data downloads)
- Off-hours access (outside business hours)

---

## 8. Compliance

### 8.1 SOC 2 Type II

**Controls:**
- CC6.1: Logical access security (RBAC, MFA)
- CC6.2: Access removal (automated offboarding)
- CC6.3: Access reviews (quarterly)
- CC7.1: Security operations (monitoring, alerting)
- CC7.2: Vulnerability management (patching, scanning)
- CC7.3: Incident response (playbooks, drills)
- CC8.1: Change management (CAB, approvals)

**Audit Frequency:** Annual third-party audit

### 8.2 GDPR

**Data Processing:**
- Lawful basis: Legitimate interest (token optimization)
- Data minimization: Only necessary data collected
- Purpose limitation: Data used only for optimization and billing
- Storage limitation: 90-day retention for personal data

**Rights Implementation:**
- **Access:** `GET /v1/admin/audit` returns all tenant data
- **Rectification:** `PATCH /v1/admin/tenant` updates configs
- **Erasure:** `DELETE /v1/admin/tenant` triggers GDPR deletion
- **Portability:** Data export in JSON format
- **Objection:** Opt-out via tenant config

**DPA:** Data Processing Agreement available for enterprise customers.

### 8.3 HIPAA

**Eligibility:**
- Encryption at rest and in transit ✅
- Audit logging ✅
- Access controls ✅
- BAAs with providers ✅

**Limitations:**
- TokenOpt does not process PHI directly (proxy only)
- Downstream applications must implement additional safeguards
- BAAs required with OpenAI, Azure, Anthropic for HIPAA workloads

### 8.4 ISO 27001

**Annex A Controls:**
- A.9: Access control (RBAC, MFA, least privilege)
- A.12: Operations security (monitoring, backups)
- A.13: Communications security (TLS, VPN)
- A.16: Incident management (playbooks, drills)
- A.17: Business continuity (DR plan, RTO/RPO)

---

## 9. Incident Response

### 9.1 Severity Classification

| Severity | Criteria | Response Time | Escalation |
|----------|----------|---------------|------------|
| **P0 (Critical)** | Complete outage, data breach, security incident | 15 minutes | CEO, Legal, PR |
| **P1 (High)** | Major feature broken, significant data exposure | 1 hour | VP Engineering |
| **P2 (Medium)** | Minor feature issue, performance degradation | 4 hours | Engineering Manager |
| **P3 (Low)** | Cosmetic issue, documentation error | 24 hours | Team Lead |

### 9.2 Incident Response Playbook

**Phase 1: Detection (0-5 minutes)**
1. Alert received (PagerDuty, Slack)
2. On-call engineer acknowledges
3. Initial assessment: severity, scope, impact

**Phase 2: Containment (5-30 minutes)**
1. Isolate affected systems
2. Revoke compromised credentials
3. Block malicious traffic (WAF rules)
4. Preserve evidence (snapshots, logs)

**Phase 3: Investigation (30 minutes-4 hours)**
1. Root cause analysis
2. Impact assessment (affected tenants, data exposure)
3. Timeline reconstruction

**Phase 4: Remediation (4-24 hours)**
1. Deploy fixes
2. Verify resolution
3. Restore services
4. Monitor for recurrence

**Phase 5: Communication (24-48 hours)**
1. Internal post-mortem
2. Customer notification (if required by SLA)
3. Public disclosure (if required by regulation)

**Phase 6: Post-Incident (1-2 weeks)**
1. Root cause analysis document
2. Action items for prevention
3. Process improvements
4. Team retrospective

### 9.3 Security Incident Specifics

**Data Breach Response:**
1. Immediately revoke all affected tokens
2. Isolate compromised systems
3. Determine scope (tenant IDs, time window)
4. Notify affected tenants within 24 hours
5. File breach notification with regulators (if required)
6. Engage forensic experts if needed

**Ransomware Response:**
1. Isolate infected systems
2. Do not pay ransom
3. Restore from clean backups
4. Verify backup integrity before restoration
5. Patch vulnerability that enabled attack

---

## 10. Vulnerability Management

### 10.1 Scanning Schedule

| Scan Type | Tool | Frequency | Scope |
|-----------|------|-----------|-------|
| Dependency scanning | Snyk, Dependabot | Daily | All packages |
| Container scanning | Trivy, ECR scanning | Every build | Docker images |
| Infrastructure scanning | Checkov, Prowler | Weekly | Terraform, CloudFormation |
| DAST | OWASP ZAP | Monthly | Running application |
| SAST | SonarQube, Bandit | Every PR | Source code |
| Penetration testing | External firm | Annual | Full platform |

### 10.2 VSL (Vulnerability Severity Levels)

| CVSS Score | Severity | SLA | Example |
|------------|----------|-----|---------|
| 9.0-10.0 | Critical | 24 hours | Remote code execution |
| 7.0-8.9 | High | 7 days | SQL injection |
| 4.0-6.9 | Medium | 30 days | Information disclosure |
| 0.1-3.9 | Low | Next release | Missing headers |

### 10.3 Patch Management

**Automated Patches:**
- Dependabot PRs for Python dependencies
- AWS Systems Manager for OS patches
- EKS managed node group updates

**Manual Patches:**
- Security patches requiring testing
- Breaking changes in dependencies
- Custom code fixes

---

## 11. Business Continuity

### 11.1 Disaster Recovery Plan

**RTO/RPO Matrix:**

| Scenario | RTO | RPO | Recovery Method |
|----------|-----|-----|-----------------|
| Single pod failure | 30s | 0 | Kubernetes auto-restart |
| Node failure | 2 min | 0 | Pod rescheduling |
| AZ failure | 5 min | 0 | Multi-AZ failover |
| Region failure | 30 min | 5 min | Cross-region DR |
| Complete data loss | 1 hour | 24 hours | Snapshot restore |

**Cross-Region DR:**
- Primary: us-east-1
- Secondary: us-west-2
- RDS: Cross-region read replica (async replication)
- Redis: Global Datastore
- EKS: Separate cluster with automated failover

### 11.2 Backup Procedures

**PostgreSQL:**
```bash
# Automated daily snapshots
# Manual snapshot before changes
aws rds create-db-snapshot   --db-instance-identifier tokenopt-production   --db-snapshot-identifier tokenopt-pre-upgrade-$(date +%Y%m%d)

# Verify snapshot
aws rds describe-db-snapshots   --db-snapshot-identifier tokenopt-pre-upgrade-$(date +%Y%m%d)
```

**Redis:**
```bash
# Manual backup
aws elasticache create-snapshot   --replication-group-id tokenopt-production   --snapshot-name tokenopt-manual-$(date +%Y%m%d)
```

**Kubernetes Manifests:**
```bash
# Backup all resources
kubectl get all -n tokenopt -o yaml > tokenopt-backup-$(date +%Y%m%d).yaml

# Backup secrets (encrypted)
kubectl get secrets -n tokenopt -o yaml > tokenopt-secrets-$(date +%Y%m%d).yaml
gpg --symmetric --cipher-algo AES256 tokenopt-secrets-$(date +%Y%m%d).yaml
```

### 11.3 Testing

**Quarterly DR Drill:**
1. Simulate region failure
2. Promote cross-region read replica
3. Redirect traffic to secondary region
4. Verify data consistency
5. Document recovery time
6. Identify gaps

---

## 12. Third-Party Risk Management

### 12.1 Provider Assessment

| Provider | Data Handling | SOC 2 | BAA | Pen Test |
|----------|--------------|-------|-----|----------|
| OpenAI | Prompts/Responses | ✅ | ✅ | ✅ |
| Azure OpenAI | Prompts/Responses | ✅ | ✅ | ✅ |
| Anthropic | Prompts/Responses | ✅ | ✅ | ✅ |
| AWS | Infrastructure | ✅ | ✅ | ✅ |

### 12.2 Subprocessor List

| Subprocessor | Purpose | Data Processed | Location |
|--------------|---------|----------------|----------|
| AWS | Infrastructure | All | US, EU |
| OpenAI | LLM API | Prompts/Responses | US |
| Azure | LLM API | Prompts/Responses | US, EU |
| Anthropic | LLM API | Prompts/Responses | US |
| Datadog (optional) | Monitoring | Metrics, Logs | US |
| PagerDuty | Alerting | Alerts | US |

---

**Document Owner:** Security & Compliance Team  
**Review Cycle:** Quarterly  
**Last Updated:** July 2026  
**Next Audit:** October 2026
