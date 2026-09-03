# TokenOpt Enterprise — Free vs Paid Component Analysis
## Complete Cost Breakdown with Free Alternatives for Local Development

**Version:** 2.0.0  
**Date:** July 2026  
**Scope:** Local development & small-scale deployment

---

## Executive Summary

| Category | Production (Paid) | Local Dev (Free) | Savings |
|----------|-------------------|------------------|---------|
| **Infrastructure** | AWS EKS + RDS + ElastiCache (~$800/mo) | Docker Desktop + Docker Compose ($0) | $800/mo |
| **LLM Provider** | OpenAI/Azure/Anthropic (~$500/mo) | Ollama + Local Models ($0) | $500/mo |
| **Monitoring** | Managed Prometheus/Grafana (~$50/mo) | Self-hosted Prometheus/Grafana ($0) | $50/mo |
| **CI/CD** | GitHub Actions (paid minutes) + ECR | Local Git + Docker Hub (free tier) | ~$20/mo |
| **DNS/SSL** | Route 53 + ACM ($25/mo) | Localhosts / mkcert ($0) | $25/mo |
| **TOTAL** | **~$1,395/month** | **$0/month** | **$1,395/month** |

**Bottom Line:** You can run the entire TokenOpt stack locally for **$0**. The production AWS setup costs ~$1,395/month at baseline scale.

---

## 1. Infrastructure Layer

### 1.1 Kubernetes (EKS → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| Control Plane | AWS EKS | $0.10/hour = ~$73/month |
| Worker Nodes | 3x m6i.2xlarge (on-demand) | ~$500/month |
| Load Balancer | AWS ALB | ~$25/month |
| Data Transfer | Cross-AZ traffic | ~$50/month |
| **Subtotal** | | **~$648/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **Docker Desktop** | Built-in Kubernetes (single-node) | $0 (free for personal use) |
| **Minikube** | Local Kubernetes cluster in VM | $0 (open source) |
| **k3s / k3d** | Lightweight K8s, runs in Docker | $0 (open source, CNCF) |
| **kind** | Kubernetes-in-Docker (multi-node) | $0 (open source, Kubernetes SIG) |
| **Rancher Desktop** | k3s-based, cross-platform | $0 (open source) |

**Recommendation for Local Dev:** Use **Docker Desktop's built-in Kubernetes** (easiest) or **k3d** (lightweight, multi-node support). Both are zero-cost and sufficient for development and small-scale testing. citeweb_search:17#5web_search:17#9web_search:17#13

**Setup Command (k3d):**
```bash
# Install k3d
brew install k3d  # macOS
# OR
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash  # Linux

# Create a 3-node cluster (1 server + 2 agents)
k3d cluster create tokenopt-dev   --servers 1   --agents 2   --port "8080:80@loadbalancer"   --port "8443:443@loadbalancer"   --volume "$(pwd)/data:/data@all"   --wait

# Verify
kubectl get nodes
```

---

### 1.2 PostgreSQL (RDS → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| Instance | db.r6g.xlarge (Multi-AZ) | ~$350/month |
| Storage | 100GB gp3 + IOPS | ~$25/month |
| Backup | Automated snapshots | ~$15/month |
| **Subtotal** | | **~$390/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **Docker PostgreSQL** | Official postgres:15 image | $0 |
| **pgAdmin** | Web-based PostgreSQL admin | $0 (open source) |
| **DBeaver** | Universal DB client | $0 (community edition) |

**Setup (Docker Compose):**
```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: tokenopt_admin
      POSTGRES_PASSWORD: dev_password_123
      POSTGRES_DB: tokenopt
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tokenopt_admin"]
      interval: 5s
      timeout: 5s
      retries: 5

  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@tokenopt.local
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres

volumes:
  postgres_data:
```

**Run:**
```bash
docker-compose up -d postgres pgadmin
# Access pgAdmin at http://localhost:5050
```

---

### 1.3 Redis (ElastiCache → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| Instance | cache.r6g.xlarge (2 nodes) | ~$200/month |
| Data Transfer | Cross-AZ replication | ~$20/month |
| **Subtotal** | | **~$220/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **Docker Redis** | Official redis:7 image | $0 |
| **Redis Insight** | Redis GUI (Redis Labs) | $0 |
| **Redis Commander** | Web-based Redis manager | $0 (open source) |

**Setup (Docker Compose):**
```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  redis-commander:
    image: rediscommander/redis-commander:latest
    environment:
      REDIS_HOSTS: local:redis:6379
    ports:
      - "8081:8081"
    depends_on:
      - redis

volumes:
  redis_data:
```

---

### 1.4 Kafka (Managed Kafka → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| Cluster | MSK (3 brokers, kafka.m5.large) | ~$300/month |
| Storage | 100GB per broker | ~$30/month |
| **Subtotal** | | **~$330/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **Docker Kafka (Bitnami)** | Single-node Kafka + Zookeeper | $0 |
| **Kafka UI** | Web-based Kafka management | $0 (open source) |
| **Redpanda** | Kafka-compatible, no Zookeeper | $0 (open source) |

**Setup (Docker Compose - Redpanda recommended, lighter):**
```yaml
services:
  redpanda:
    image: redpandadata/redpanda:latest
    command:
      - redpanda
      - start
      - --smp 1
      - --memory 1G
      - --overprovisioned
      - --node-id 0
      - --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092
      - --advertise-kafka-addr internal://redpanda:9092,external://localhost:19092
    ports:
      - "9092:9092"
      - "19092:19092"
      - "9644:9644"
    volumes:
      - redpanda_data:/var/lib/redpanda/data

  redpanda-console:
    image: redpandadata/console:latest
    environment:
      KAFKA_BROKERS: redpanda:9092
    ports:
      - "8082:8080"
    depends_on:
      - redpanda

volumes:
  redpanda_data:
```

---

## 2. LLM Provider Layer

### 2.1 LLM API (OpenAI/Azure/Anthropic → Free Alternative)

**Production (Paid):**
| Provider | Usage | Cost |
|----------|-------|------|
| OpenAI GPT-4 | ~10M tokens/month | ~$300-500/month |
| Azure OpenAI | ~10M tokens/month | ~$250-400/month |
| Anthropic Claude | ~5M tokens/month | ~$150-250/month |
| **Subtotal** | | **~$500-1,000/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **Ollama** | Download & run models locally (Llama, Mistral, Gemma) | $0 (open source) |
| **LM Studio** | GUI for local LLMs with OpenAI-compatible API | $0 (free tier) |
| **LocalAI** | OpenAI API-compatible local inference server | $0 (open source) |
| **llama.cpp** | C++ implementation for CPU/GPU inference | $0 (open source) |
| **vLLM** | High-throughput local inference (GPU recommended) | $0 (open source) |

**Recommendation:** Use **Ollama** for the simplest setup, or **LocalAI** if you need strict OpenAI API compatibility for testing TokenOpt's proxy behavior. citeweb_search:17#1web_search:17#4web_search:17#6

**Setup (Ollama):**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model (Llama 3.3 70B requires ~40GB RAM, use smaller for dev)
ollama pull llama3.3:70b      # Best quality, needs 40GB+ RAM
ollama pull llama3.2:3b       # Lightweight, runs on 8GB RAM  
ollama pull mistral:7b        # Good balance, runs on 16GB RAM
ollama pull gemma4:12b        # Google's model, runs on 16GB RAM citeweb_search:17#4

# Start the API server (OpenAI-compatible)
ollama serve

# Test
curl http://localhost:11434/api/generate -d '{
  "model": "llama3.2:3b",
  "prompt": "Hello, how are you?"
}'
```

**Setup (LocalAI - Strict OpenAI API Compatibility):**
```bash
# Run via Docker
docker run -p 8080:8080   -v $PWD/models:/models   localai/localai:latest   --models-path /models

# LocalAI exposes OpenAI-compatible endpoints at http://localhost:8080/v1
# TokenOpt can proxy to this directly
```

**Free Cloud LLM APIs (No Local GPU Required):**

If your machine can't run local models, these free cloud tiers work:

| Provider | Free Tier | Rate Limit | Best For |
|----------|-----------|------------|----------|
| **Groq** | 1,000 requests/day | 20 RPM | Speed, real-time apps |
| **Cerebras** | 1M tokens/day | 20 RPM | High volume batch |
| **Mistral** | 1B tokens/month | 5 RPM | Code generation |
| **OpenRouter** | 20+ free models | 200 RPD | Variety, failover |
| **Google AI Studio** | 1,500 req/day | Variable | Long context (1M tokens) |
| **GitHub Models** | GPT-4o, Claude 3.5 | Variable | Prototyping |
| **OVH AI Endpoints** | Anonymous, no signup | 2 RPM | Quick testing |

citeweb_search:17#1web_search:17#3web_search:17#6

**Important Caveats for Free Cloud Tiers:**
- Rate limits are strict (20-200 requests/day)
- Some providers use your prompts for model training (check terms)
- Not suitable for production load, but perfect for development
- OpenRouter is the best "single API key, multiple free providers" option

---

## 3. Monitoring & Observability Layer

### 3.1 Prometheus + Grafana (Managed → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| Managed Prometheus | Amazon Managed Prometheus | ~$30/month (base) + ingestion |
| Managed Grafana | Amazon Managed Grafana | ~$9/month/user |
| Alertmanager | Self-hosted on EKS | ~$10/month (compute) |
| **Subtotal** | | **~$50-100/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **Prometheus** | Metrics collection & storage | $0 (Apache 2.0, CNCF graduated) |
| **Grafana** | Visualization & dashboards | $0 (AGPL 3.0) |
| **Alertmanager** | Alert routing | $0 (Apache 2.0) |
| **Node Exporter** | Host metrics | $0 (Apache 2.0) |
| **cAdvisor** | Container metrics | $0 (Apache 2.0) |

**Recommendation:** Self-hosted Prometheus + Grafana is the industry standard and completely free. The kube-prometheus-stack Helm chart deploys everything in one command. citeweb_search:17#0web_search:17#7web_search:17#12

**Setup (Docker Compose):**
```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    depends_on:
      - prometheus

  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml

volumes:
  prometheus_data:
  grafana_data:
```

**Prometheus Config (prometheus.yml):**
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'tokenopt'
    static_configs:
      - targets: ['tokenopt:8000']
    metrics_path: /metrics

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']
```

---

## 4. CI/CD & Build Layer

### 4.1 Container Registry (ECR → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| Storage | Amazon ECR | ~$0.10/GB/month |
| Data Transfer | Image pulls | ~$0.09/GB |
| **Subtotal** | | **~$5-20/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **Docker Hub** | Public repositories unlimited, 1 private free | $0 |
| **GitHub Container Registry** | 500MB storage free, unlimited public | $0 |
| **Local Registry** | Docker registry running locally | $0 |

**Recommendation:** Use **GitHub Container Registry (ghcr.io)** for private images during development. For purely local work, build directly into your local Docker daemon — no registry needed.

---

### 4.2 CI/CD Pipeline (GitHub Actions Paid → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| GitHub Actions | 3,000 minutes included, then $0.008/minute | ~$0-50/month |
| **Subtotal** | | **~$0-50/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **GitHub Actions (Free Tier)** | 2,000 minutes/month (public repos), 500 min (private) | $0 |
| **GitLab CI (Self-hosted)** | Unlimited runners on your machine | $0 |
| **Local Scripts** | Shell scripts + Makefile | $0 |
| **Act** | Run GitHub Actions locally | $0 (open source) |

**Recommendation:** For local development, just use shell scripts or a Makefile. For CI-like testing, **act** lets you run GitHub Actions workflows locally.

```bash
# Install act
brew install act  # macOS

# Run GitHub Actions locally
act push
```

---

## 5. DNS & SSL Layer

### 5.1 DNS + Certificates (Route 53 + ACM → Free Alternative)

**Production (Paid):**
| Component | Service | Cost |
|-----------|---------|------|
| DNS | Route 53 Hosted Zone | $0.50/month/zone |
| Queries | DNS queries | ~$0.40/million queries |
| SSL | ACM certificates | $0 (free, but requires ALB = ~$25/month) |
| **Subtotal** | | **~$25-50/month** |

**Local Dev (Free):**
| Tool | Description | Cost |
|------|-------------|------|
| **localhost** | No DNS needed | $0 |
| **mkcert** | Local HTTPS certificates | $0 (open source) |
| **ngrok** | Public URL for local testing | $0 (free tier) |
| **localtunnel** | Alternative to ngrok | $0 (open source) |

**Setup (mkcert for local HTTPS):**
```bash
# Install mkcert
brew install mkcert  # macOS
# OR
curl -JLO "https://dl.filippo.io/mkcert/latest?for=linux/amd64"
chmod +x mkcert-v*-linux-amd64
sudo cp mkcert-v*-linux-amd64 /usr/local/bin/mkcert

# Create local CA
mkcert -install

# Generate cert for local domain
mkcert tokenopt.local localhost 127.0.0.1 ::1

# Use in your local ingress or reverse proxy
```

---

## 6. Complete Local Development Stack (Docker Compose)

### 6.1 Full docker-compose.yml for Local Dev

```yaml
version: "3.8"

services:
  # ============================================================
  # APPLICATION
  # ============================================================
  tokenopt:
    build:
      context: ./application
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      POSTGRES_DSN: postgresql://tokenopt_admin:dev_password_123@postgres:5432/tokenopt
      REDIS_URL: redis://redis:6379
      KAFKA_BROKERS: redpanda:9092
      OPENAI_API_KEY: http://localai:8080/v1  # Points to LocalAI
      JWT_SECRET: dev-jwt-secret-change-in-production
      ENCRYPTION_KEY: dev-encryption-key-change-in-production
      FIDELITY_THRESHOLD: "0.995"
      LOG_LEVEL: DEBUG
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
      redpanda:
        condition: service_started
      localai:
        condition: service_started
    volumes:
      - ./application/src:/app/src  # Hot reload for dev
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  # ============================================================
  # DATABASE
  # ============================================================
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: tokenopt_admin
      POSTGRES_PASSWORD: dev_password_123
      POSTGRES_DB: tokenopt
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tokenopt_admin"]
      interval: 5s
      timeout: 5s
      retries: 5

  pgadmin:
    image: dpage/pgadmin4:latest
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@tokenopt.local
      PGADMIN_DEFAULT_PASSWORD: admin
    ports:
      - "5050:80"
    depends_on:
      - postgres

  # ============================================================
  # CACHE
  # ============================================================
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  redis-commander:
    image: rediscommander/redis-commander:latest
    environment:
      REDIS_HOSTS: local:redis:6379
    ports:
      - "8081:8081"
    depends_on:
      - redis

  # ============================================================
  # MESSAGE QUEUE (Kafka-compatible)
  # ============================================================
  redpanda:
    image: redpandadata/redpanda:latest
    command:
      - redpanda
      - start
      - --smp 1
      - --memory 1G
      - --overprovisioned
      - --node-id 0
      - --kafka-addr internal://0.0.0.0:9092,external://0.0.0.0:19092
      - --advertise-kafka-addr internal://redpanda:9092,external://localhost:19092
    ports:
      - "9092:9092"
      - "19092:19092"
      - "9644:9644"
    volumes:
      - redpanda_data:/var/lib/redpanda/data

  redpanda-console:
    image: redpandadata/console:latest
    environment:
      KAFKA_BROKERS: redpanda:9092
    ports:
      - "8082:8080"
    depends_on:
      - redpanda

  # ============================================================
  # LOCAL LLM (OpenAI API Compatible)
  # ============================================================
  localai:
    image: localai/localai:latest
    ports:
      - "8080:8080"
    environment:
      THREADS: 4
      CONTEXT_SIZE: 2048
    volumes:
      - localai_models:/models
    # Pre-download a small model for quick startup
    entrypoint: >
      sh -c "
        if [ ! -f /models/llama3.2-3b.gguf ]; then
          echo 'Downloading model...';
          wget -O /models/llama3.2-3b.gguf https://huggingface.co/TheBloke/Llama-3.2-3B-Instruct-GGUF/resolve/main/llama-3.2-3b-instruct.Q4_K_M.gguf;
        fi;
        local-ai --models-path /models --address 0.0.0.0:8080
      "

  # ============================================================
  # MONITORING
  # ============================================================
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=15d'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/datasources:/etc/grafana/provisioning/datasources
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_INSTALL_PLUGINS: grafana-clock-panel
    depends_on:
      - prometheus

  alertmanager:
    image: prom/alertmanager:latest
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml

  # ============================================================
  # REVERSE PROXY (Replaces ALB + Ingress)
  # ============================================================
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/certs:/etc/nginx/certs
    depends_on:
      - tokenopt

volumes:
  postgres_data:
  redis_data:
  redpanda_data:
  localai_models:
  prometheus_data:
  grafana_data:
```

---

## 7. AWS Free Tier (If You Want Cloud Later)

### 7.1 What's Actually Free on AWS in 2026

**Always Free (Never Expires):**
| Service | Allowance |
|---------|-----------|
| Lambda | 1M requests + 400,000 GB-seconds/month |
| DynamoDB | 25GB storage + 200M requests/month |
| CloudFront | 1TB data transfer + 10M requests/month |
| S3 | 5GB standard storage |
| CloudWatch | 10 metrics + 10 alarms + 1M API requests |

**New Account Credit (2026 Model):**
- $200 credit for accounts created after July 15, 2025
- Valid for 6 months or until credit is used
- Covers EC2, RDS, EKS, ElastiCache, etc.
- After credit expires: pay-as-you-go pricing citeweb_search:17#2

**Legacy Free Tier (Accounts Before July 2025):**
- 750 hours/month of t2/t3.micro EC2 for 12 months
- 750 hours/month of RDS single-AZ micro for 12 months

**Important:** The old "12 months free EC2/RDS" structure was replaced in 2025. New accounts get a $200 credit instead of dedicated free instance hours.

---

## 8. Cost Comparison Summary Table

| Layer | Component | Production Cost | Free Alternative | Local Dev Cost |
|-------|-----------|-----------------|------------------|----------------|
| **Orchestration** | Kubernetes | $648/mo (EKS) | k3d / Docker Desktop K8s | $0 |
| **Database** | PostgreSQL | $390/mo (RDS) | Docker postgres:15 | $0 |
| **Cache** | Redis | $220/mo (ElastiCache) | Docker redis:7 | $0 |
| **Queue** | Kafka | $330/mo (MSK) | Redpanda (Docker) | $0 |
| **LLM Provider** | OpenAI/Azure | $500/mo | Ollama / LocalAI | $0 |
| **Monitoring** | Prometheus/Grafana | $50/mo (Managed) | Self-hosted (Docker) | $0 |
| **Registry** | ECR | $10/mo | Docker Hub / GHCR | $0 |
| **CI/CD** | GitHub Actions | $20/mo | Local scripts / act | $0 |
| **DNS/SSL** | Route 53 + ACM | $25/mo | localhost + mkcert | $0 |
| **Ingress** | ALB | $25/mo | nginx (Docker) | $0 |
| **TOTAL** | | **$2,218/mo** | | **$0** |

---

## 9. Hardware Requirements for Local Dev

### Minimum (Basic Testing):
| Component | Requirement |
|-----------|-------------|
| CPU | 4 cores (any modern CPU) |
| RAM | 8GB |
| Storage | 20GB SSD |
| GPU | Not required |

**Can run:** TokenOpt app, PostgreSQL, Redis, Redpanda, LocalAI with Llama 3.2 3B (CPU)

### Recommended (Full Development):
| Component | Requirement |
|-----------|-------------|
| CPU | 8+ cores |
| RAM | 16-32GB |
| Storage | 50GB SSD |
| GPU | Optional ( speeds up local LLM inference) |

**Can run:** Everything above + Larger models (Mistral 7B, Gemma 12B) + Multi-node k3d cluster

### Ideal (Production-like Local):
| Component | Requirement |
|-----------|-------------|
| CPU | 16+ cores |
| RAM | 64GB+ |
| Storage | 100GB NVMe SSD |
| GPU | NVIDIA RTX 4090 / A6000 (24GB VRAM) |

**Can run:** Full multi-node k3s cluster + Llama 3.3 70B + All monitoring + Load testing

---

## 10. Step-by-Step: Run TokenOpt Locally for $0

### Step 1: Install Prerequisites
```bash
# macOS
brew install docker docker-compose kubectl helm git curl jq

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker.io docker-compose git curl jq
sudo usermod -aG docker $USER
newgrp docker
```

### Step 2: Clone and Setup
```bash
git clone https://github.com/yourcompany/tokenopt.git
cd tokenopt
mkdir -p monitoring dashboards nginx/certs init-scripts
```

### Step 3: Start Everything
```bash
# Start all services
docker-compose up -d

# Wait for health checks
sleep 30

# Verify everything is running
docker-compose ps
```

### Step 4: Verify Components
```bash
# TokenOpt API
curl http://localhost:8000/health

# PostgreSQL
docker-compose exec postgres psql -U tokenopt_admin -d tokenopt -c "\dt"

# Redis
docker-compose exec redis redis-cli PING

# Redpanda
docker-compose exec redpanda rpk topic list

# LocalAI
curl http://localhost:8080/v1/models

# Prometheus
curl http://localhost:9090/api/v1/status/targets

# Grafana (login: admin/admin)
open http://localhost:3000
```

### Step 5: Test Optimization
```bash
# Generate a test JWT (for local dev, any secret works)
ADMIN_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0ZW5hbnRfaWQiOiJkZXYiLCJzdWIiOiJkZXZAdG9rZW5vcHQubG9jYWwiLCJyb2xlcyI6WyJhZG1pbiJdLCJwbGFuIjoiZW50ZXJwcmlzZSJ9.local_dev_signature"

# Test chat completion with optimization
curl -X POST http://localhost:8000/v1/chat/completions   -H "Authorization: Bearer $ADMIN_TOKEN"   -H "Content-Type: application/json"   -d '{
    "model": "llama3.2:3b",
    "messages": [
      {"role": "user", "content": "Please provide a detailed explanation of how token optimization works in large language models."}
    ]
  }' | jq

# Preview optimization without calling LLM
curl -X POST http://localhost:8000/v1/tokenopt/validate   -H "Authorization: Bearer $ADMIN_TOKEN"   -H "Content-Type: application/json"   -d '{
    "model": "llama3.2:3b",
    "messages": [
      {"role": "user", "content": "I would like to request that you please explain the concept of machine learning in very simple terms that a beginner could understand."}
    ]
  }' | jq
```

### Step 6: View Dashboards
```bash
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
# pgAdmin: http://localhost:5050 (admin@tokenopt.local / admin)
# Redis Commander: http://localhost:8081
# Redpanda Console: http://localhost:8082
```

---

## 11. When to Move to Paid Cloud

| Signal | Action |
|--------|--------|
| Local machine can't handle load | Upgrade hardware OR move to cloud |
| Need 99.9%+ uptime | Move to AWS/GCP/Azure with Multi-AZ |
| Team >5 developers | Shared cloud dev environment |
| Need production SLAs | Managed services (RDS, ElastiCache) |
| Data compliance requirements | Cloud with SOC2/ISO27001/GDPR |
| Token volume >10M/month | Cloud autoscaling becomes cost-effective |

**Hybrid Approach:** Keep local dev for development/testing, use cloud only for production. This is the most common pattern.

---

## 12. Free Cloud Credits for Startups (If You Need Cloud)

| Provider | Credit | Requirements |
|----------|--------|--------------|
| AWS Activate | $1,000-$100,000 | Startup, <10 years old, VC-funded or accelerator |
| Google Cloud for Startups | $2,000-$200,000 | Startup, partner referral |
| Microsoft for Startups | $1,000-$150,000 | Startup, <7 years old |
| DigitalOcean Hatch | $10,000 | Startup, accelerator/incubator |
| IBM Cloud for Startups | $1,000-$120,000 | Startup, partner referral |
| Oracle for Startups | $10,000-$100,000 | Startup, <5 years old |

These programs can cover 1-2 years of cloud costs for early-stage companies.

---

**Document Owner:** Platform Engineering  
**Last Updated:** July 2026
