# TokenOpt Enterprise — Operations Runbooks
## Step-by-Step Procedures for Common Scenarios

**Version:** 2.0.0  
**Audience:** SREs, Platform Engineers, On-Call Engineers  
**Last Updated:** July 2026

---

## Runbook 1: Platform Health Check

### Objective
Verify all platform components are healthy and operating within normal parameters.

### Frequency
Daily (automated) + On-demand

### Steps

#### 1.1 Quick Health Check
```bash
# Check application health endpoint
curl -sf https://api.tokenopt.yourcompany.com/health | jq

# Expected output:
# {
#   "status": "healthy",
#   "version": "2.0.0",
#   "services": {
#     "database": "connected",
#     "redis": "connected",
#     "kafka": "connected",
#     "providers": {
#       "openai": "healthy",
#       "azure": "healthy",
#       "anthropic": "healthy"
#     }
#   }
# }
```

#### 1.2 Check Kubernetes Pods
```bash
# All namespaces
kubectl get pods --all-namespaces

# TokenOpt specific
kubectl get pods -n tokenopt -o wide

# Check pod status
kubectl get pods -n tokenopt
# STATUS should be Running for all pods
# RESTARTS should be 0 (or low number)
```

#### 1.3 Check Node Resources
```bash
# Node utilization
kubectl top nodes

# Expected:
# CPU: <70%
# Memory: <80%

# If high, check which pods are consuming resources
kubectl top pods -n tokenopt --sort-by=cpu
kubectl top pods -n tokenopt --sort-by=memory
```

#### 1.4 Check Services and Ingress
```bash
# Services
kubectl get svc -n tokenopt

# Ingress
kubectl get ingress -n tokenopt

# Ingress controller
kubectl get svc -n ingress-nginx
```

#### 1.5 Check Database Connectivity
```bash
# PostgreSQL
kubectl run pg-check --rm -i --restart=Never   --image=postgres:15-alpine   --namespace tokenopt   -- psql "$POSTGRES_DSN" -c "SELECT version();"

# Redis
kubectl run redis-check --rm -i --restart=Never   --image=redis:7-alpine   --namespace tokenopt   -- redis-cli -u "$REDIS_URL" PING
# Expected: PONG
```

#### 1.6 Review Recent Events
```bash
# Recent events
kubectl get events -n tokenopt --sort-by='.lastTimestamp' | tail -20

# Warning events
kubectl get events -n tokenopt --field-selector type=Warning
```

### Success Criteria
- All pods in `Running` state
- No recent restarts
- Node CPU <70%, Memory <80%
- Database and Redis responding
- No warning events

---

## Runbook 2: High Error Rate Response

### Objective
Diagnose and resolve elevated API error rates.

### Trigger
Alert: `TokenOptHighErrorRate` (error rate >1% for 2 minutes)

### Steps

#### 2.1 Verify Alert
```bash
# Check current error rate
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090 &
curl -s 'http://localhost:9090/api/v1/query?query=rate(tokenopt_requests_total{status=~"5.."}[5m])' | jq
```

#### 2.2 Check Application Logs
```bash
# Recent errors
kubectl logs -l app.kubernetes.io/name=tokenopt -n tokenopt --tail=100 | grep ERROR

# Follow logs in real-time
kubectl logs -l app.kubernetes.io/name=tokenopt -n tokenopt -f | grep ERROR

# Specific error patterns
kubectl logs -l app.kubernetes.io/name=tokenopt -n tokenopt | grep -i "error\|exception\|failed"
```

#### 2.3 Check Provider Health
```bash
# Provider status from health endpoint
curl -sf https://api.tokenopt.yourcompany.com/health | jq '.services.providers'

# Test direct provider access
curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY" | jq

# Check provider status pages
# OpenAI: https://status.openai.com
# Azure: https://status.azure.com
# Anthropic: https://status.anthropic.com
```

#### 2.4 Check Circuit Breaker Status
```bash
# Check circuit breaker state in Redis
kubectl run redis-check --rm -i --restart=Never   --image=redis:7-alpine   --namespace tokenopt   -- redis-cli -u "$REDIS_URL" HGETALL circuit:openai

# Expected: state=closed, failures=0
# If state=open: circuit breaker has tripped
```

#### 2.5 Check Rate Limiting
```bash
# Check if TokenOpt is being rate-limited by provider
kubectl logs -l app.kubernetes.io/name=tokenopt -n tokenopt | grep -i "rate limit\|429\|too many requests"
```

#### 2.6 Common Fixes

**Fix A: Provider Outage**
```bash
# Circuit breaker should auto-failover
# Verify traffic is routing to healthy provider
kubectl logs -l app.kubernetes.io/name=tokenopt -n tokenopt | grep "routing to"

# If not failing over, manually restart provider connections
kubectl rollout restart deployment/tokenopt -n tokenopt
```

**Fix B: Database Connection Pool Exhausted**
```bash
# Check active connections
kubectl run pg-check --rm -i --restart=Never   --image=postgres:15-alpine   --namespace tokenopt   -- psql "$POSTGRES_DSN" -c "SELECT count(*) FROM pg_stat_activity;"

# If >80% of max, scale pods or increase pool size
# Edit configmap to increase pool_size
kubectl edit configmap tokenopt-config -n tokenopt
```

**Fix C: Memory Pressure**
```bash
# Check if pods are OOMKilled
kubectl get pods -n tokenopt -o json | jq '.items[].status.containerStatuses[].lastState.terminated'

# If OOMKilled, increase memory limits
helm upgrade tokenopt ./helm-chart   --namespace tokenopt   --set resources.limits.memory=4Gi
```

### Escalation
If error rate not resolved within 15 minutes:
1. Page L2 (Platform Engineer)
2. Prepare rollback plan
3. Notify #incidents Slack channel

---

## Runbook 3: Low Fidelity Score Response

### Objective
Investigate and resolve low optimization fidelity scores.

### Trigger
Alert: `TokenOptLowFidelity` (avg fidelity <0.99 for 5 minutes)

### Steps

#### 3.1 Check Rollback Logs
```bash
# Recent rollbacks
curl -H "Authorization: Bearer $ADMIN_TOKEN"   "https://api.tokenopt.yourcompany.com/v1/tokenopt/rollbacks?hours=1" | jq

# Analyze patterns
# - Which technique is causing rollbacks?
# - Which tenant is most affected?
# - What prompt types are failing?
```

#### 3.2 Check Optimization Settings
```bash
# Current fidelity threshold
kubectl get configmap tokenopt-config -n tokenopt -o json | jq '.data.FIDELITY_THRESHOLD'

# Current optimization level distribution
curl -H "Authorization: Bearer $ADMIN_TOKEN"   "https://api.tokenopt.yourcompany.com/v1/tokenopt/stats?hours=1" | jq '.optimization_level_distribution'
```

#### 3.3 Identify Affected Tenants
```bash
# Per-tenant fidelity scores
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090 &
curl -s 'http://localhost:9090/api/v1/query?query=avg(tokenopt_fidelity_score)by(tenant_id)' | jq
```

#### 3.4 Common Fixes

**Fix A: Temporarily Lower Fidelity Threshold**
```bash
# Reduce threshold to reduce rollbacks
kubectl patch configmap tokenopt-config -n tokenopt --type merge   -p '{"data":{"FIDELITY_THRESHOLD":"0.99"}}'

# Restart pods to pick up new config
kubectl rollout restart deployment/tokenopt -n tokenopt
```

**Fix B: Disable Aggressive Optimization**
```bash
# Switch affected tenants to standard optimization
for tenant in engineering marketing sales; do
  curl -X PATCH "https://api.tokenopt.yourcompany.com/v1/admin/tenant/config"     -H "Authorization: Bearer $ADMIN_TOKEN"     -H "Content-Type: application/json"     -d "{"tenant_id":"$tenant","optimization_level":"standard"}"
done
```

**Fix C: Disable Problematic Technique**
```bash
# If specific technique is causing issues
# Edit tenant config to disable technique
# Example: disable semantic_compression for legal tenant
curl -X PATCH "https://api.tokenopt.yourcompany.com/v1/admin/tenant/config"   -H "Authorization: Bearer $ADMIN_TOKEN"   -H "Content-Type: application/json"   -d '{
    "tenant_id": "legal",
    "disabled_techniques": ["semantic_compression"]
  }'
```

### Escalation
If fidelity not restored within 30 minutes:
1. Page ML Engineering team
2. Consider full rollback to previous version
3. Notify affected tenants

---

## Runbook 4: Database Maintenance

### Objective
Perform routine PostgreSQL maintenance tasks.

### Frequency
Monthly

### Steps

#### 4.1 Refresh Materialized Views
```bash
# Connect to database and refresh views
kubectl exec -it deployment/tokenopt -n tokenopt --   python -c "
import asyncio
from persistence_layer_v2 import AuditDatabase
db = AuditDatabase()
asyncio.run(db.initialize())
asyncio.run(db.refresh_materialized_view())
print('Materialized views refreshed')
"
```

#### 4.2 Clean Old Partitions
```bash
# Remove partitions older than 90 days
kubectl exec -it deployment/tokenopt -n tokenopt --   python -c "
import asyncio
from persistence_layer_v2 import AuditDatabase
db = AuditDatabase()
asyncio.run(db.initialize())
asyncio.run(db.cleanup_old_data(days=90))
print('Old partitions cleaned')
"
```

#### 4.3 Analyze Tables
```bash
# Update table statistics
kubectl run pg-maintenance --rm -i --restart=Never   --image=postgres:15-alpine   --namespace tokenopt   -- psql "$POSTGRES_DSN" -c "ANALYZE audit_logs;"
```

#### 4.4 Vacuum Tables
```bash
# Reclaim storage and update visibility map
kubectl run pg-maintenance --rm -i --restart=Never   --image=postgres:15-alpine   --namespace tokenopt   -- psql "$POSTGRES_DSN" -c "VACUUM ANALYZE audit_logs;"
```

#### 4.5 Check Table Sizes
```bash
# Monitor table growth
kubectl run pg-maintenance --rm -i --restart=Never   --image=postgres:15-alpine   --namespace tokenopt   -- psql "$POSTGRES_DSN" -c "
SELECT schemaname, tablename, 
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

### Success Criteria
- Materialized views refreshed without errors
- Old partitions removed
- Table statistics updated
- No bloat detected

---

## Runbook 5: Scaling Operations

### Objective
Scale platform resources to handle increased load.

### Trigger
- Sustained CPU >70%
- Sustained memory >80%
- Request queue depth >100
- Latency P95 >1s

### Steps

#### 5.1 Horizontal Pod Scaling
```bash
# Manual scale
kubectl scale deployment tokenopt --replicas=10 -n tokenopt

# Or update Helm values
helm upgrade tokenopt ./helm-chart   --namespace tokenopt   --set replicaCount=10   --wait

# Verify
kubectl get pods -n tokenopt
kubectl get hpa -n tokenopt
```

#### 5.2 Vertical Pod Scaling
```bash
# Increase resource limits
helm upgrade tokenopt ./helm-chart   --namespace tokenopt   --set resources.limits.cpu=4000m   --set resources.limits.memory=4Gi   --set resources.requests.cpu=1000m   --set resources.requests.memory=1Gi   --wait
```

#### 5.3 Cluster Autoscaling
```bash
# Check if cluster autoscaler is active
kubectl get nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# If nodes are at capacity, cluster autoscaler will add nodes
# Monitor node addition
kubectl get nodes -w

# Manual node scaling (if needed)
terraform apply -var="node_desired_size=7" -var="node_max_size=25"
```

#### 5.4 Database Scaling
```bash
# Scale RDS instance
aws rds modify-db-instance   --db-instance-identifier tokenopt-production   --db-instance-class db.r6g.2xlarge   --apply-immediately

# Scale Redis
aws elasticache modify-replication-group   --replication-group-id tokenopt-production   --cache-node-type cache.r6g.xlarge   --apply-immediately
```

#### 5.5 Verify Scaling
```bash
# Check new pods are ready
kubectl get pods -n tokenopt

# Check load distribution
kubectl top pods -n tokenopt

# Verify latency improvement
curl -w "@curl-format.txt" -o /dev/null -s   https://api.tokenopt.yourcompany.com/health
```

---

## Runbook 6: Secret Rotation

### Objective
Rotate security credentials without service disruption.

### Frequency
Quarterly (JWT), Monthly (Provider keys)

### Steps

#### 6.1 Rotate JWT Secret

**Step 1: Generate New Secret**
```bash
NEW_JWT_SECRET=$(openssl rand -base64 48)
echo "New JWT secret generated"
```

**Step 2: Update Kubernetes Secret**
```bash
# Create new secret
kubectl create secret generic tokenopt-secrets-new   --namespace tokenopt   --from-literal=JWT_SECRET="$NEW_JWT_SECRET"   --from-literal=ENCRYPTION_KEY="$(kubectl get secret tokenopt-secrets -n tokenopt -o jsonpath='{.data.ENCRYPTION_KEY}' | base64 -d)"

# Update deployment to use new secret
kubectl patch deployment tokenopt -n tokenopt --type json   -p='[{"op": "replace", "path": "/spec/template/spec/containers/0/envFrom/0/secretRef/name", "value": "tokenopt-secrets-new"}]'
```

**Step 3: Rolling Restart**
```bash
# Rolling restart to pick up new secret
kubectl rollout restart deployment/tokenopt -n tokenopt
kubectl rollout status deployment/tokenopt -n tokenopt
```

**Step 4: Update Token Generation**
```bash
# Update admin scripts and CI/CD to use new secret
# Notify users to regenerate tokens
```

**Step 5: Cleanup Old Secret**
```bash
# After 24-hour grace period
kubectl delete secret tokenopt-secrets -n tokenopt
kubectl rename secret tokenopt-secrets-new tokenopt-secrets -n tokenopt
```

#### 6.2 Rotate Provider API Keys

**Step 1: Generate New Key**
```bash
# OpenAI
NEW_OPENAI_KEY=$(curl -s -X POST https://api.openai.com/v1/keys   -H "Authorization: Bearer $OPENAI_API_KEY" | jq -r '.key')
```

**Step 2: Dual-Key Period**
```bash
# Add new key to secrets (both old and new active)
kubectl patch secret tokenopt-secrets -n tokenopt --type merge   -p="{"stringData":{"OPENAI_API_KEY_NEW":"$NEW_OPENAI_KEY"}}"

# Update application to accept both keys
# (Implementation detail: app checks both keys during transition)
```

**Step 3: Verify New Key**
```bash
# Test with new key
curl -s https://api.openai.com/v1/models   -H "Authorization: Bearer $NEW_OPENAI_KEY" | jq
```

**Step 4: Remove Old Key**
```bash
# After 24 hours
kubectl patch secret tokenopt-secrets -n tokenopt --type json   -p='[{"op": "remove", "path": "/data/OPENAI_API_KEY"}]'

# Update secret to use new key name
kubectl patch secret tokenopt-secrets -n tokenopt --type json   -p='[{"op": "replace", "path": "/data/OPENAI_API_KEY", "value": "'$(echo -n "$NEW_OPENAI_KEY" | base64)'"}]'
```

---

## Runbook 7: Backup and Restore

### Objective
Create and verify backups, and perform restores when needed.

### Steps

#### 7.1 Create Manual Backup

**PostgreSQL:**
```bash
# Create snapshot
aws rds create-db-snapshot   --db-instance-identifier tokenopt-production   --db-snapshot-identifier tokenopt-manual-$(date +%Y%m%d-%H%M%S)

# Verify snapshot
aws rds describe-db-snapshots   --db-snapshot-identifier tokenopt-manual-$(date +%Y%m%d-%H%M%S)
```

**Redis:**
```bash
# Create snapshot
aws elasticache create-snapshot   --replication-group-id tokenopt-production   --snapshot-name tokenopt-manual-$(date +%Y%m%d-%H%M%S)
```

**Kubernetes:**
```bash
# Export all resources
kubectl get all -n tokenopt -o yaml > tokenopt-resources-$(date +%Y%m%d).yaml
kubectl get configmap -n tokenopt -o yaml > tokenopt-configmaps-$(date +%Y%m%d).yaml
kubectl get secrets -n tokenopt -o yaml > tokenopt-secrets-$(date +%Y%m%d).yaml

# Encrypt secrets
gpg --symmetric --cipher-algo AES256 tokenopt-secrets-$(date +%Y%m%d).yaml
rm tokenopt-secrets-$(date +%Y%m%d).yaml
```

#### 7.2 Restore from Backup

**PostgreSQL:**
```bash
# Restore from snapshot
aws rds restore-db-instance-from-db-snapshot   --db-instance-identifier tokenopt-production-restored   --db-snapshot-identifier tokenopt-manual-YYYYMMDD-HHMMSS   --db-instance-class db.r6g.xlarge

# Wait for restoration
aws rds wait db-instance-available   --db-instance-identifier tokenopt-production-restored

# Update application to point to restored database
# (Modify DSN in Kubernetes secret)
```

**Redis:**
```bash
# Restore from snapshot
aws elasticache create-replication-group   --replication-group-id tokenopt-production-restored   --replication-group-description "Restored from snapshot"   --snapshot-name tokenopt-manual-YYYYMMDD-HHMMSS
```

#### 7.3 Verify Backup Integrity

```bash
# Weekly restore test
# Create ephemeral instance from latest snapshot
aws rds restore-db-instance-from-db-snapshot   --db-instance-identifier tokenopt-backup-test   --db-snapshot-identifier $(aws rds describe-db-snapshots     --query 'DBSnapshots[?DBInstanceIdentifier==`tokenopt-production`]|sort_by(@, &SnapshotCreateTime)[-1].DBSnapshotIdentifier'     --output text)   --db-instance-class db.t3.micro

# Run integrity checks
kubectl run pg-test --rm -i --restart=Never   --image=postgres:15-alpine   -- psql "postgresql://..." -c "
SELECT count(*) FROM audit_logs;
SELECT count(*) FROM tenant_configs;
SELECT pg_size_pretty(pg_database_size('tokenopt'));
"

# Clean up test instance
aws rds delete-db-instance   --db-instance-identifier tokenopt-backup-test   --skip-final-snapshot
```

---

## Runbook 8: Incident Response

### Objective
Standardized response to platform incidents.

### Steps

#### 8.1 Incident Declaration
```bash
# Create incident channel
/slack create-incident "TokenOpt API latency spike"

# Page on-call engineer
/pagerduty trigger "TokenOpt P95 latency >2s"
```

#### 8.2 Initial Assessment
```bash
# Check severity
# P0: Complete outage, data breach
# P1: Major feature broken
# P2: Performance degradation
# P3: Minor issue

# Gather context
kubectl get pods -n tokenopt
kubectl top nodes
kubectl logs -l app.kubernetes.io/name=tokenopt -n tokenopt --tail=50
curl -sf https://api.tokenopt.yourcompany.com/health | jq
```

#### 8.3 Communication
```bash
# Update status page
# P0/P1: Post to status page immediately
# P2: Post if not resolved in 15 minutes
# P3: No status page update needed

# Internal communication
# P0: #incidents + executive team
# P1: #incidents
# P2: #tokenopt-alerts
```

#### 8.4 Resolution and Post-Mortem
```bash
# After resolution, create post-mortem
# Template: /docs/templates/post-mortem.md

# Required sections:
# - Timeline
# - Root cause
# - Impact assessment
# - Action items
# - Lessons learned
```

---

**Document Owner:** SRE Team  
**Review Cycle:** Monthly  
**Last Updated:** July 2026
