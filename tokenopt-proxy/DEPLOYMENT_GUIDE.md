# TokenOpt Enterprise — Complete Deployment Guide
## From Zero to Production in 12 Phases

**Version:** 2.0.0  
**Target Environment:** AWS EKS (Kubernetes)  
**Estimated Time:** 4-6 hours (first deployment)  
**Prerequisites:** AWS CLI, kubectl, Helm, Docker, Terraform

---

## Phase 0: Prerequisites & Environment Setup

### Step 0.1: Install Required Tools

#### On macOS (using Homebrew)
```bash
# Install all required tools
brew install awscli kubectl helm terraform docker jq python@3.11

# Verify installations
aws --version          # Should be >= 2.13.0
kubectl version        # Should be >= 1.28
helm version           # Should be >= 3.12
docker --version       # Should be >= 24.0
terraform --version    # Should be >= 1.5
python3 --version      # Should be >= 3.11
jq --version           # Should be >= 1.6
```

#### On Ubuntu/Debian
```bash
# Update package index
sudo apt-get update && sudo apt-get upgrade -y

# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Install kubectl
curl -LO "https://dl.k8s/release/$(curl -L -s https://dl.k8s/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# Install Terraform
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install terraform

# Install Docker
sudo apt-get install docker.io
sudo usermod -aG docker $USER
newgrp docker

# Install Python & pip
sudo apt-get install python3 python3-pip python3-venv

# Install jq
sudo apt-get install jq
```

### Step 0.2: Configure AWS Credentials

```bash
# Method 1: Using AWS CLI (recommended for initial setup)
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Enter your default region (e.g., us-east-1)
# Enter your output format (json)

# Verify configuration
aws sts get-caller-identity
# Expected output: Account ID, User ARN, User ID

# Method 2: Using environment variables (for CI/CD)
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-1"
```

### Step 0.3: Clone Repository and Project Layout

Clone the TokenOpt monorepo or navigate to the project root:

```bash
git clone https://github.com/rohit-naik36/TokenOpt.git
cd TokenOpt
```

The repository is structured as a unified monorepo containing the three core products:

```
TokenOpt/
├── tokenopt-proxy/        # Production HTTP proxy service (FastAPI v2.0)
│   ├── tokenopt_proxy_v2.py
│   ├── provider_client_v2.py
│   ├── persistence_layer_v2.py
│   ├── fidelity_validator_v2.py
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.tf
│   └── variables.tf
├── tokenopt-optimizer/    # Standalone, embeddable prompt optimization engine
│   ├── pyproject.toml
│   └── tokenopt_optimizer/
└── tokenopt-sdk/          # Published client SDK snapshot (v0.1.0)
    ├── pyproject.toml
    └── tokenopt/
```

> **Note:** The proxy depends on `tokenopt-optimizer` via relative editable install
> (`-e ../tokenopt-optimizer` in `requirements.txt`) and a multi-context Docker build
> (`--build-context tokenopt_sdk=../tokenopt-optimizer`).

---

## Phase 1: Infrastructure Provisioning with Terraform

### Step 1.1: Initialize Terraform Configuration

```bash
cd ~/tokenopt-enterprise/infrastructure/terraform

# Create main.tf
cat > main.tf << 'EOF'
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.23"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.11"
    }
  }

  backend "s3" {
    bucket         = "tokenopt-terraform-state"
    key            = "production/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "tokenopt-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "TokenOpt"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
EOF

# Create variables.tf
cat > variables.tf << 'EOF'
variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "cluster_name" {
  description = "EKS cluster name"
  type        = string
  default     = "tokenopt-production"
}

variable "node_instance_types" {
  description = "EC2 instance types for worker nodes"
  type        = list(string)
  default     = ["m6i.2xlarge"]
}

variable "node_desired_size" {
  description = "Desired number of worker nodes"
  type        = number
  default     = 3
}

variable "node_min_size" {
  description = "Minimum number of worker nodes"
  type        = number
  default     = 3
}

variable "node_max_size" {
  description = "Maximum number of worker nodes"
  type        = number
  default     = 20
}
EOF

# Create outputs.tf
cat > outputs.tf << 'EOF'
output "cluster_endpoint" {
  description = "EKS cluster endpoint"
  value       = aws_eks_cluster.tokenopt.endpoint
}

output "cluster_name" {
  description = "EKS cluster name"
  value       = aws_eks_cluster.tokenopt.name
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = aws_db_instance.tokenopt.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = aws_elasticache_replication_group.tokenopt.primary_endpoint_address
  sensitive   = true
}
EOF
```

### Step 1.2: Create VPC and Networking

```bash
cd ~/tokenopt-enterprise/infrastructure/terraform

# Create vpc.tf
cat > vpc.tf << 'EOF'
data "aws_availability_zones" "available" {
  state = "available"
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "tokenopt-${var.environment}"
  cidr = "10.0.0.0/16"

  azs             = slice(data.aws_availability_zones.available.names, 0, 3)
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
  database_subnets = ["10.0.201.0/24", "10.0.202.0/24", "10.0.203.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = false
  one_nat_gateway_per_az = true
  enable_vpn_gateway     = false

  enable_dns_hostnames = true
  enable_dns_support   = true

  public_subnet_tags = {
    "kubernetes.io/role/elb"                      = "1"
    "kubernetes.io/cluster/${var.cluster_name}"     = "shared"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"             = "1"
    "kubernetes.io/cluster/${var.cluster_name}"     = "shared"
  }

  tags = {
    Name = "tokenopt-${var.environment}"
  }
}
EOF
```

### Step 1.3: Create EKS Cluster

```bash
cat > eks.tf << 'EOF'
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

  cluster_name    = var.cluster_name
  cluster_version = "1.28"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  cluster_addons = {
    coredns = {
      most_recent = true
    }
    kube-proxy = {
      most_recent = true
    }
    vpc-cni = {
      most_recent = true
    }
    aws-ebs-csi-driver = {
      most_recent = true
    }
  }

  eks_managed_node_groups = {
    tokenopt_nodes = {
      desired_size = var.node_desired_size
      min_size     = var.node_min_size
      max_size     = var.node_max_size

      instance_types = var.node_instance_types
      capacity_type  = "ON_DEMAND"

      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size           = 100
            volume_type           = "gp3"
            iops                  = 3000
            throughput            = 125
            encrypted             = true
            kms_key_id            = aws_kms_key.ebs.arn
            delete_on_termination = true
          }
        }
      }

      labels = {
        role = "tokenopt-workload"
      }

      tags = {
        Name = "tokenopt-node"
      }
    }
  }

  manage_aws_auth_configmap = true

  aws_auth_roles = [
    {
      rolearn  = aws_iam_role.tokenopt_admin.arn
      username = "tokenopt-admin"
      groups   = ["system:masters"]
    }
  ]

  tags = {
    Name = var.cluster_name
  }
}

# IAM role for admin access
resource "aws_iam_role" "tokenopt_admin" {
  name = "tokenopt-admin-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
      }
    ]
  })
}

data "aws_caller_identity" "current" {}
EOF
```

### Step 1.4: Create RDS PostgreSQL Database

```bash
cat > rds.tf << 'EOF'
resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_db_subnet_group" "tokenopt" {
  name       = "tokenopt-${var.environment}"
  subnet_ids = module.vpc.database_subnets

  tags = {
    Name = "tokenopt-db-subnet-group"
  }
}

resource "aws_security_group" "rds" {
  name_prefix = "tokenopt-rds-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "tokenopt-rds-sg"
  }
}

resource "aws_db_instance" "tokenopt" {
  identifier = "tokenopt-${var.environment}"

  engine         = "postgres"
  engine_version = "15.4"
  instance_class = "db.r6g.xlarge"

  allocated_storage     = 100
  max_allocated_storage = 1000
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id           = aws_kms_key.rds.arn

  db_name  = "tokenopt"
  username = "tokenopt_admin"
  password = random_password.rds_password.result

  db_subnet_group_name   = aws_db_subnet_group.tokenopt.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  multi_az               = true
  publicly_accessible    = false
  deletion_protection    = true
  skip_final_snapshot    = false
  final_snapshot_identifier = "tokenopt-final-${formatdate("YYYYMMDDhhmmss", timestamp())}"

  backup_retention_period = 35
  backup_window          = "03:00-04:00"
  maintenance_window     = "Mon:04:00-Mon:05:00"

  performance_insights_enabled    = true
  performance_insights_retention_period = 7

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  tags = {
    Name = "tokenopt-postgres"
  }
}

resource "random_password" "rds_password" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret" "rds_password" {
  name        = "tokenopt/rds-password-${var.environment}"
  description = "RDS password for TokenOpt"
}

resource "aws_secretsmanager_secret_version" "rds_password" {
  secret_id     = aws_secretsmanager_secret.rds_password.id
  secret_string = random_password.rds_password.result
}
EOF
```

### Step 1.5: Create ElastiCache Redis

```bash
cat > redis.tf << 'EOF'
resource "aws_elasticache_subnet_group" "tokenopt" {
  name       = "tokenopt-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "redis" {
  name_prefix = "tokenopt-redis-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = module.vpc.private_subnets_cidr_blocks
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "tokenopt-redis-sg"
  }
}

resource "aws_elasticache_replication_group" "tokenopt" {
  replication_group_id = "tokenopt-${var.environment}"
  description          = "TokenOpt Redis cluster"

  node_type            = "cache.r6g.xlarge"
  num_cache_clusters   = 2
  multi_az_enabled     = true
  automatic_failover_enabled = true

  engine               = "redis"
  engine_version       = "7.0"
  port                 = 6379
  parameter_group_name = "default.redis7"

  subnet_group_name  = aws_elasticache_subnet_group.tokenopt.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  snapshot_retention_limit = 7
  snapshot_window         = "05:00-06:00"

  tags = {
    Name = "tokenopt-redis"
  }
}
EOF
```

### Step 1.6: Initialize and Apply Terraform

```bash
# Initialize Terraform (downloads providers and modules)
terraform init

# Validate configuration
terraform validate

# Plan the deployment (review carefully)
terraform plan -out=tfplan

# Apply the plan (this takes 15-30 minutes)
terraform apply tfplan

# Save outputs for later use
terraform output -json > terraform-outputs.json
```

**Expected outputs:**
- `cluster_endpoint`: EKS API server URL
- `cluster_name`: EKS cluster identifier
- `rds_endpoint`: PostgreSQL connection endpoint
- `redis_endpoint`: Redis connection endpoint

---

## Phase 2: Configure kubectl and Helm

### Step 2.1: Update kubeconfig for EKS

```bash
# Configure kubectl to connect to your EKS cluster
aws eks update-kubeconfig --region $(terraform output -raw aws_region) --name $(terraform output -raw cluster_name)

# Verify connection
kubectl cluster-info
# Expected: Kubernetes control plane running at https://...

# Verify nodes are ready
kubectl get nodes
# Expected: 3 nodes in Ready state
```

### Step 2.2: Install Required Helm Repositories

```bash
# Add necessary Helm repositories
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add jetstack https://charts.jetstack.io
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add bitnami https://charts.bitnami.com/bitnami

# Update repositories
helm repo update
```

---

## Phase 3: Install Cluster-Level Dependencies

### Step 3.1: Install NGINX Ingress Controller

```bash
# Create namespace
kubectl create namespace ingress-nginx

# Install NGINX Ingress Controller
helm install ingress-nginx ingress-nginx/ingress-nginx   --namespace ingress-nginx   --set controller.replicaCount=2   --set controller.nodeSelector."role"="tokenopt-workload"   --set controller.service.type=LoadBalancer   --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-type"="nlb"   --set controller.service.annotations."service\.beta\.kubernetes\.io/aws-load-balancer-cross-zone-load-balancing-enabled"="true"

# Wait for LoadBalancer IP
kubectl get svc -n ingress-nginx -w
# Note the EXTERNAL-IP - this is your platform's public endpoint
```

### Step 3.2: Install cert-manager for TLS

```bash
# Install cert-manager CRDs
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.crds.yaml

# Install cert-manager
helm install cert-manager jetstack/cert-manager   --namespace cert-manager   --create-namespace   --version v1.13.0   --set installCRDs=false

# Verify installation
kubectl get pods -n cert-manager
```

### Step 3.3: Create ClusterIssuer for Let's Encrypt

```bash
# Create a ClusterIssuer for automatic TLS certificates
cat > cluster-issuer.yaml << 'EOF'
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: platform-engineering@yourcompany.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: nginx
EOF

kubectl apply -f cluster-issuer.yaml
```

### Step 3.4: Install Prometheus and Grafana

```bash
# Create monitoring namespace
kubectl create namespace monitoring

# Install kube-prometheus-stack
helm install prometheus prometheus-community/kube-prometheus-stack   --namespace monitoring   --set grafana.enabled=true   --set grafana.adminPassword='YourSecureGrafanaPassword123!'   --set prometheus.prometheusSpec.retention=30d   --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=100Gi

# Get Grafana admin password (if auto-generated)
kubectl get secret -n monitoring prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d
```

---

## Phase 4: Build and Push Docker Image

### Step 4.1: Production Dockerfile

Navigate to the `tokenopt-proxy/` directory:

```bash
cd tokenopt-proxy
```

The production `Dockerfile` uses a multi-stage build that bundles the core runtime and injects `tokenopt_optimizer` from its monorepo sibling context:

```dockerfile
FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir \
        "fastapi>=0.110.0,<1.0.0" \
        "uvicorn[standard]>=0.24.0,<1.0.0" \
        "pydantic>=2.0.0,<3.0.0" \
        "httpx>=0.24.0,<1.0.0" \
        "PyJWT>=2.8.0,<3.0.0" \
        "numpy>=1.24.0,<3.0.0" \
        "openai>=1.30.0,<2.0.0"

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Copy the installed core packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source (flat layout)
COPY tokenopt_proxy_v2.py provider_client_v2.py persistence_layer_v2.py fidelity_validator_v2.py ./

# Copy the tokenopt_optimizer SDK from its build context (monorepo sibling)
COPY --from=tokenopt_sdk tokenopt_optimizer/ ./tokenopt_optimizer/

# Non-root runtime user
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=5).status==200 else 1)" || exit 1

CMD ["sh", "-c", "uvicorn tokenopt_proxy_v2:app --host ${HOST} --port ${PORT} --workers 1"]
```

### Step 4.2: Application Dependencies (requirements.txt)

The production `requirements.txt` specifies core, sibling, and optional infrastructure packages:

```
fastapi>=0.110.0,<1.0.0
uvicorn[standard]>=0.24.0,<1.0.0
pydantic>=2.0.0,<3.0.0
httpx>=0.24.0,<1.0.0
PyJWT>=2.8.0,<3.0.0
numpy>=1.24.0,<3.0.0
openai>=1.30.0,<2.0.0

# Sibling optimizer engine in monorepo:
-e ../tokenopt-optimizer

# Optional: smart prompt compression (graceful fallback if absent)
headroom-ai>=0.33.0

# Optional infrastructure drivers (degrades gracefully if absent):
asyncpg>=0.28.0
redis>=4.5.0
aiokafka>=0.8.0
sentence-transformers>=2.2.0

pytest>=7.0.0
```

### Step 4.3: Build with Multi-Context and Push to ECR

Build using the `--build-context` flag so Docker can resolve `tokenopt_sdk` from `../tokenopt-optimizer`:

```bash
# Create ECR repository
aws ECR create-repository --repository-name tokenopt-proxy --region us-east-1

# Get login token for ECR
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build Docker image using multi-context
docker build --build-context tokenopt_sdk=../tokenopt-optimizer -t tokenopt-proxy:v2.0.0 .

# Tag for ECR
docker tag tokenopt-proxy:v2.0.0 $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/tokenopt-proxy:v2.0.0

# Push to ECR
docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/tokenopt-proxy:v2.0.0

# Verify push
aws ecr describe-images --repository-name tokenopt-proxy --region us-east-1
```

---

## Phase 5: Create Kubernetes Secrets

### Step 5.1: Generate Encryption Keys

```bash
# Generate JWT secret (minimum 32 characters)
JWT_SECRET=$(openssl rand -base64 48)
echo "JWT_SECRET generated: ${JWT_SECRET:0:10}..."

# Generate AES-256 encryption key
ENCRYPTION_KEY=$(openssl rand -base64 32)
echo "ENCRYPTION_KEY generated: ${ENCRYPTION_KEY:0:10}..."

# Get RDS password from Secrets Manager
RDS_PASSWORD=$(aws secretsmanager get-secret-value   --secret-id tokenopt/rds-password-production   --query SecretString   --output text)

# Get RDS endpoint
RDS_ENDPOINT=$(terraform output -raw rds_endpoint)

# Get Redis endpoint
REDIS_ENDPOINT=$(terraform output -raw redis_endpoint)
```

### Step 5.2: Create Kubernetes Namespace and Secrets

```bash
# Create tokenopt namespace
kubectl create namespace tokenopt

# Create main secrets
kubectl create secret generic tokenopt-secrets \
  --namespace tokenopt \
  --from-literal=JWT_SECRET="$JWT_SECRET" \
  --from-literal=ENCRYPTION_KEY="$ENCRYPTION_KEY" \
  --from-literal=POSTGRES_DSN="postgresql://tokenopt_admin:${RDS_PASSWORD}@${RDS_ENDPOINT}:5432/tokenopt" \
  --from-literal=REDIS_URL="rediss://${REDIS_ENDPOINT}:6379" \
  --from-literal=OPENAI_API_KEY="sk-your-openai-api-key" \
  --from-literal=AZURE_OPENAI_KEY="your-azure-key" \
  --from-literal=AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com" \
  --from-literal=ANTHROPIC_API_KEY="sk-ant-your-anthropic-key" \
  --from-literal=GEMINI_API_KEY="your-gemini-api-key"

# Verify secrets (values are hidden)
kubectl get secret tokenopt-secrets -n tokenopt -o yaml
```

---

## Phase 6: Deploy TokenOpt Application

### Step 6.1: Create Helm Chart Structure

```bash
cd ~/tokenopt-enterprise/helm-chart

# Create Chart.yaml
cat > Chart.yaml << 'EOF'
apiVersion: v2
name: tokenopt
version: 2.0.0
description: TokenOpt Enterprise Platform
appVersion: "2.0.0"
EOF

# Create values.yaml
cat > values.yaml << 'EOF'
replicaCount: 3

image:
  repository: "YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/tokenopt-proxy"
  pullPolicy: IfNotPresent
  tag: "v2.0.0"

imagePullSecrets: []
nameOverride: ""
fullnameOverride: ""

serviceAccount:
  create: true
  annotations: {}
  name: ""

podAnnotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8000"
  prometheus.io/path: "/metrics"

podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000

securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL

service:
  type: ClusterIP
  port: 8000

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
    nginx.ingress.kubernetes.io/proxy-read-timeout: "300"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "300"
  hosts:
    - host: api.tokenopt.yourcompany.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: tokenopt-tls
      hosts:
        - api.tokenopt.yourcompany.com

resources:
  limits:
    cpu: 2000m
    memory: 2Gi
  requests:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 50
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80

nodeSelector:
  role: tokenopt-workload

tolerations: []

affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/name
                operator: In
                values:
                  - tokenopt
          topologyKey: kubernetes.io/hostname

env:
  - name: LOG_LEVEL
    value: "INFO"
  - name: FIDELITY_THRESHOLD
    value: "0.995"
  - name: ENABLE_LLM_JUDGE
    value: "true"
  - name: MAX_CONCURRENT_REQUESTS
    value: "100"

envFrom:
  - secretRef:
      name: tokenopt-secrets
EOF
```

### Step 6.2: Create Kubernetes Deployment Template

```bash
mkdir -p templates
cat > templates/deployment.yaml << 'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "tokenopt.fullname" . }}
  labels:
    {{- include "tokenopt.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "tokenopt.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      {{- with .Values.podAnnotations }}
      annotations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "tokenopt.selectorLabels" . | nindent 8 }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "tokenopt.serviceAccountName" . }}
      securityContext:
        {{- toYaml .Values.podSecurityContext | nindent 8 }}
      containers:
        - name: {{ .Chart.Name }}
          securityContext:
            {{- toYaml .Values.securityContext | nindent 12 }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8000
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          resources:
            {{- toYaml .Values.resources | nindent 12 }}
          env:
            {{- toYaml .Values.env | nindent 12 }}
          envFrom:
            {{- toYaml .Values.envFrom | nindent 12 }}
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
EOF
```

### Step 6.3: Create Service and HPA Templates

```bash
cat > templates/service.yaml << 'EOF'
apiVersion: v1
kind: Service
metadata:
  name: {{ include "tokenopt.fullname" . }}
  labels:
    {{- include "tokenopt.labels" . | nindent 4 }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "tokenopt.selectorLabels" . | nindent 4 }}
EOF

cat > templates/hpa.yaml << 'EOF'
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "tokenopt.fullname" . }}
  labels:
    {{- include "tokenopt.labels" . | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "tokenopt.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    {{- if .Values.autoscaling.targetCPUUtilizationPercentage }}
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
    {{- end }}
    {{- if .Values.autoscaling.targetMemoryUtilizationPercentage }}
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetMemoryUtilizationPercentage }}
    {{- end }}
{{- end }}
EOF
```

### Step 6.4: Create Helper Templates

```bash
cat > templates/_helpers.tpl << 'EOF'
{{/*
Expand the name of the chart.
*/}}
{{- define "tokenopt.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "tokenopt.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "tokenopt.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "tokenopt.labels" -}}
helm.sh/chart: {{ include "tokenopt.chart" . }}
{{ include "tokenopt.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "tokenopt.selectorLabels" -}}
app.kubernetes.io/name: {{ include "tokenopt.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "tokenopt.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "tokenopt.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
EOF
```

### Step 6.5: Deploy with Helm

```bash
# Update image repository in values.yaml with your actual ECR URI
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed -i "s|YOUR_ACCOUNT_ID|$ACCOUNT_ID|g" values.yaml

# Install the Helm chart
helm install tokenopt .   --namespace tokenopt   --create-namespace   --set image.tag=v2.0.0   --wait   --timeout 10m

# Verify deployment
kubectl get pods -n tokenopt
kubectl get svc -n tokenopt
kubectl get ingress -n tokenopt
```

---

## Phase 7: Configure DNS

### Step 7.1: Get LoadBalancer IP

```bash
# Get the external IP of the ingress controller
INGRESS_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "LoadBalancer hostname: $INGRESS_IP"
```

### Step 7.2: Create DNS Record

```bash
# Option 1: Using AWS Route 53 (if domain is hosted there)
# Get your hosted zone ID
HOSTED_ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name yourcompany.com --query 'HostedZones[0].Id' --output text | sed 's|/hostedzone/||')

# Create change batch
cat > dns-change.json << EOF
{
  "Changes": [
    {
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "api.tokenopt.yourcompany.com",
        "Type": "CNAME",
        "TTL": 300,
        "ResourceRecords": [
          {
            "Value": "$INGRESS_IP"
          }
        ]
      }
    }
  ]
}
EOF

# Apply DNS change
aws route53 change-resource-record-sets   --hosted-zone-id $HOSTED_ZONE_ID   --change-batch file://dns-change.json

# Option 2: Using your DNS provider
# Create a CNAME record:
# api.tokenopt.yourcompany.com -> $INGRESS_IP
```

### Step 7.3: Verify DNS Resolution

```bash
# Wait for DNS propagation (can take 5-30 minutes)
dig api.tokenopt.yourcompany.com

# Test HTTPS endpoint
curl -v https://api.tokenopt.yourcompany.com/health
```

---

## Phase 8: Database Migration and Initialization

### Step 8.1: Schema Initialization

TokenOpt Enterprise manages its own database schema automatically on application startup. When `tokenopt_proxy_v2.py` boots, `AuditDatabase.initialize()` connects via `POSTGRES_DSN` and runs:

- Table creation: `audit_logs` partitioned by date (`PARTITION BY RANGE (timestamp)`)
- Daily partition provisioning for current and upcoming periods
- B-tree and composite indexing on `tenant_id`, `request_id`, `timestamp`, and `was_rolled_back`

To verify or pre-provision the schema manually, run:

```bash
# Verify schema via temporary psql pod
kubectl run db-verify --rm -i --restart=Never \
  --image=postgres:15-alpine \
  --namespace tokenopt \
  --env="POSTGRES_DSN=$(kubectl get secret tokenopt-secrets -n tokenopt -o jsonpath='{.data.POSTGRES_DSN}' | base64 -d)" \
  -- psql "$POSTGRES_DSN" -c "\d+ audit_logs"
```

### Step 8.2: Verify Database Schema

```bash
# Connect to database and verify partitioned tables
kubectl run db-verify --rm -i --restart=Never \
  --image=postgres:15-alpine \
  --namespace tokenopt \
  --env="POSTGRES_DSN=$(kubectl get secret tokenopt-secrets -n tokenopt -o jsonpath='{.data.POSTGRES_DSN}' | base64 -d)" \
  -- psql "$POSTGRES_DSN" -c "SELECT relname FROM pg_class WHERE relname LIKE 'audit_logs%';"

# Expected output includes:
# - audit_logs (partitioned root)
# - audit_logs_yYYYYmMMdDD (daily active partitions)
```

---

## Phase 9: Configure Monitoring and Alerting

### Step 9.1: Import TokenOpt Dashboard

```bash
# Create Grafana dashboard ConfigMap
cat > grafana-dashboard.yaml << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: tokenopt-dashboard
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  tokenopt-dashboard.json: |
    {
      "dashboard": {
        "id": null,
        "title": "TokenOpt Main Dashboard",
        "tags": ["tokenopt"],
        "timezone": "utc",
        "panels": [
          {
            "id": 1,
            "title": "Request Rate",
            "type": "stat",
            "targets": [
              {
                "expr": "rate(tokenopt_requests_total[5m])"
              }
            ]
          },
          {
            "id": 2,
            "title": "Error Rate",
            "type": "stat",
            "targets": [
              {
                "expr": "rate(tokenopt_requests_total{status=~"5.."}[5m]) / rate(tokenopt_requests_total[5m])"
              }
            ]
          },
          {
            "id": 3,
            "title": "Fidelity Score",
            "type": "stat",
            "targets": [
              {
                "expr": "avg(tokenopt_fidelity_score)"
              }
            ]
          },
          {
            "id": 4,
            "title": "Rollback Rate",
            "type": "stat",
            "targets": [
              {
                "expr": "rate(tokenopt_rollbacks_total[5m]) / rate(tokenopt_requests_total[5m])"
              }
            ]
          },
          {
            "id": 5,
            "title": "Cache Hit Rate",
            "type": "stat",
            "targets": [
              {
                "expr": "rate(tokenopt_cache_hits_total[5m]) / rate(tokenopt_cache_requests_total[5m])"
              }
            ]
          },
          {
            "id": 6,
            "title": "Cost Savings ($)",
            "type": "stat",
            "targets": [
              {
                "expr": "sum(tokenopt_cost_savings_total)"
              }
            ]
          }
        ]
      }
    }
EOF

kubectl apply -f grafana-dashboard.yaml
```

### Step 9.2: Create Prometheus Rules

```bash
cat > prometheus-rules.yaml << 'EOF'
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: tokenopt-alerts
  namespace: monitoring
  labels:
    app: kube-prometheus-stack
spec:
  groups:
    - name: tokenopt
      rules:
        - alert: TokenOptHighErrorRate
          expr: rate(tokenopt_requests_total{status=~"5.."}[5m]) / rate(tokenopt_requests_total[5m]) > 0.01
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "TokenOpt error rate is above 1%"
            description: "Error rate is {{ $value | humanizePercentage }} for the last 5 minutes"

        - alert: TokenOptLowFidelity
          expr: avg(tokenopt_fidelity_score) < 0.99
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "TokenOpt fidelity score is below 0.99"
            description: "Current fidelity score: {{ $value }}"

        - alert: TokenOptHighRollbackRate
          expr: rate(tokenopt_rollbacks_total[5m]) / rate(tokenopt_requests_total[5m]) > 0.02
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "TokenOpt rollback rate is above 2%"
            description: "Rollback rate is {{ $value | humanizePercentage }}"

        - alert: TokenOptHighLatency
          expr: histogram_quantile(0.95, rate(tokenopt_request_duration_seconds_bucket[5m])) > 1
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "TokenOpt P95 latency is above 1 second"
            description: "P95 latency is {{ $value }}s"
EOF

kubectl apply -f prometheus-rules.yaml
```

### Step 9.3: Configure Alertmanager

```bash
# Create Alertmanager configuration for Slack/PagerDuty
cat > alertmanager-config.yaml << 'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: alertmanager-kube-prometheus-stack
  namespace: monitoring
type: Opaque
stringData:
  alertmanager.yaml: |
    global:
      smtp_smarthost: 'smtp.gmail.com:587'
      smtp_from: 'alerts@yourcompany.com'

    route:
      receiver: 'default'
      routes:
        - match:
            severity: critical
          receiver: 'pagerduty-critical'
        - match:
            severity: warning
          receiver: 'slack-warnings'

    receivers:
      - name: 'default'
        email_configs:
          - to: 'platform-engineering@yourcompany.com'

      - name: 'pagerduty-critical'
        pagerduty_configs:
          - service_key: '<YOUR_PAGERDUTY_KEY>'
            severity: critical

      - name: 'slack-warnings'
        slack_configs:
          - api_url: '<YOUR_SLACK_WEBHOOK_URL>'
            channel: '#tokenopt-alerts'
            title: 'TokenOpt Alert'
            text: '{{ .CommonAnnotations.summary }}'
EOF

kubectl apply -f alertmanager-config.yaml
```

---

## Phase 10: Load Testing and Validation

### Step 10.1: Generate Test JWT Token

```bash
# Install jwt-cli if not already installed
brew install mike-engel/jwt-cli/jwt-cli  # macOS

# Generate admin token
ADMIN_TOKEN=$(jwt encode --secret "$JWT_SECRET" --exp="+1h" '{
  "tenant_id": "test",
  "sub": "test@yourcompany.com",
  "roles": ["admin"],
  "plan": "enterprise"
}')

echo "Admin token generated: ${ADMIN_TOKEN:0:50}..."
```

### Step 10.2: Run Health Checks

```bash
# Test health endpoint
curl -f https://api.tokenopt.yourcompany.com/health

# Expected response:
# {
#   "status": "healthy",
#   "version": "2.0.0",
#   "services": {
#     "database": "connected",
#     "redis": "connected",
#     "providers": {
#       "openai": "healthy",
#       "azure": "healthy",
#       "anthropic": "healthy"
#     }
#   }
# }
```

### Step 10.3: Test API Endpoints

```bash
# Test chat completion with optimization
curl -X POST https://api.tokenopt.yourcompany.com/v1/chat/completions   -H "Authorization: Bearer $ADMIN_TOKEN"   -H "Content-Type: application/json"   -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What are the benefits of token optimization in LLM applications? Please explain in detail."}
    ],
    "temperature": 0.7
  }' | jq

# Verify tokenopt metadata in response
curl -s -X POST https://api.tokenopt.yourcompany.com/v1/chat/completions   -H "Authorization: Bearer $ADMIN_TOKEN"   -H "Content-Type: application/json"   -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello, how are you today? I hope you are doing well."}
    ]
  }' | jq '.tokenopt'

# Test optimization preview
curl -X POST "https://api.tokenopt.yourcompany.com/v1/tokenopt/validate?prompt=Please+provide+a+detailed+explanation+of+quantum+computing+principles+and+their+applications+in+modern+cryptography." \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq
```

### Step 10.4: Run Load Test with k6

```bash
# Install k6
brew install k6  # macOS

# Create load test script
cat > load-test.js << 'EOF'
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up
    { duration: '5m', target: 50 },   // Steady state
    { duration: '2m', target: 100 },  // Peak load
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<1000'], // 95% under 1s
    http_req_failed: ['rate<0.01'],     // Error rate < 1%
  },
};

const BASE_URL = 'https://api.tokenopt.yourcompany.com';
const TOKEN = __ENV.ADMIN_TOKEN;

export default function () {
  const payload = JSON.stringify({
    model: 'gpt-4',
    messages: [
      { role: 'user', content: 'Explain the concept of machine learning in simple terms.' }
    ],
    temperature: 0.7,
  });

  const res = http.post(`${BASE_URL}/v1/chat/completions`, payload, {
    headers: {
      'Authorization': `Bearer ${TOKEN}`,
      'Content-Type': 'application/json',
    },
  });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'response has tokenopt metadata': (r) => r.json('tokenopt') !== undefined,
    'fidelity score > 0.99': (r) => r.json('tokenopt.fidelity_score') > 0.99,
    'savings percentage > 0': (r) => r.json('tokenopt.savings_pct') > 0,
  });

  sleep(1);
}
EOF

# Run load test
k6 run --env ADMIN_TOKEN=$ADMIN_TOKEN load-test.js
```

---

## Phase 11: Security Hardening

### Step 11.1: Enable AWS WAF

```bash
# Create WAF WebACL
cat > waf.tf << 'EOF'
resource "aws_wafv2_web_acl" "tokenopt" {
  name        = "tokenopt-production"
  description = "WAF rules for TokenOpt API"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # Rate limiting rule
  rule {
    name     = "RateLimit"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "RateLimit"
      sampled_requests_enabled   = true
    }
  }

  # SQL injection protection
  rule {
    name     = "SQLInjection"
    priority = 2

    action {
      block {}
    }

    statement {
      or_statement {
        statement {
          sqli_match_statement {
            field_to_match {
              body {}
            }
            text_transformation {
              priority = 0
              type     = "URL_DECODE"
            }
          }
        }
        statement {
          sqli_match_statement {
            field_to_match {
              query_string {}
            }
            text_transformation {
              priority = 0
              type     = "URL_DECODE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "SQLInjection"
      sampled_requests_enabled   = true
    }
  }

  # AWS Managed Rules
  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesCommonRuleSet"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "tokenopt-waf"
    sampled_requests_enabled   = true
  }
}

# Associate WAF with ALB
resource "aws_wafv2_web_acl_association" "tokenopt" {
  resource_arn = aws_lb.tokenopt.arn
  web_acl_arn  = aws_wafv2_web_acl.tokenopt.arn
}
EOF
```

### Step 11.2: Enable VPC Flow Logs

```bash
# Add to vpc.tf
resource "aws_flow_log" "tokenopt" {
  vpc_id                   = module.vpc.vpc_id
  traffic_type             = "ALL"
  log_destination_type     = "cloud-watch-logs"
  log_destination          = aws_cloudwatch_log_group.vpc_flow.arn
  iam_role_arn             = aws_iam_role.flow_logs.arn
  max_aggregation_interval = 60
}

resource "aws_cloudwatch_log_group" "vpc_flow" {
  name              = "/aws/vpc/tokenopt-flow-logs"
  retention_in_days = 30
}
```

### Step 11.3: Enable GuardDuty

```bash
# Enable GuardDuty for threat detection
aws guardduty create-detector --enable

# Get detector ID
DETECTOR_ID=$(aws guardduty list-detectors --query 'DetectorIds[0]' --output text)

# Enable EKS protection
aws guardduty update-detector   --detector-id $DETECTOR_ID   --finding-publishing-frequency FIFTEEN_MINUTES   --data-sources '{"kubernetes":{"auditLogs":{"enable":true}}}'
```

---

## Phase 12: Production Readiness Checklist

### Step 12.1: Final Verification

```bash
# Run comprehensive health check
cat > production-check.sh << 'EOF'
#!/bin/bash
set -e

echo "=== TokenOpt Production Readiness Check ==="

# 1. Infrastructure
echo "[1/10] Checking Kubernetes cluster..."
kubectl cluster-info
kubectl get nodes

echo "[2/10] Checking pods status..."
kubectl get pods -n tokenopt
kubectl get pods -n ingress-nginx
kubectl get pods -n monitoring

echo "[3/10] Checking services..."
kubectl get svc -n tokenopt
kubectl get ingress -n tokenopt

# 2. Application Health
echo "[4/10] Checking application health..."
curl -sf https://api.tokenopt.yourcompany.com/health | jq

echo "[5/10] Checking database connectivity..."
curl -sf https://api.tokenopt.yourcompany.com/health | jq '.services.database'

echo "[6/10] Checking Redis connectivity..."
curl -sf https://api.tokenopt.yourcompany.com/health | jq '.services.redis'

# 3. Security
echo "[7/10] Checking TLS certificate..."
echo | openssl s_client -connect api.tokenopt.yourcompany.com:443 -servername api.tokenopt.yourcompany.com 2>/dev/null | openssl x509 -noout -dates -subject

echo "[8/10] Checking secrets rotation..."
kubectl get secret tokenopt-secrets -n tokenopt -o yaml | grep -q "JWT_SECRET" && echo "Secrets present"

# 4. Monitoring
echo "[9/10] Checking Prometheus targets..."
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090 &
sleep 5
curl -sf http://localhost:9090/api/v1/targets | jq '.data.activeTargets | length'
kill %1

echo "[10/10] Checking Grafana dashboards..."
kubectl port-forward svc/prometheus-grafana -n monitoring 3000:80 &
sleep 5
curl -sf http://admin:YourSecureGrafanaPassword123!@localhost:3000/api/search | jq '. | length'
kill %1

echo "=== All checks passed! TokenOpt is production ready. ==="
EOF

chmod +x production-check.sh
./production-check.sh
```

### Step 12.2: Document Deployment

```bash
# Create deployment manifest
cat > DEPLOYMENT_MANIFEST.md << 'EOF'
# TokenOpt Production Deployment Manifest

**Deployment Date:** $(date -u +"%Y-%m-%d %H:%M:%S UTC")
**Version:** 2.0.0
**Deployed By:** $(whoami)

## Infrastructure
- **Cluster:** tokenopt-production (EKS 1.28)
- **Region:** us-east-1
- **Nodes:** 3 x m6i.2xlarge
- **VPC:** 10.0.0.0/16

## Application
- **Image:** $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/tokenopt-proxy:v2.0.0
- **Replicas:** 3 (autoscaling to 50)
- **Resources:** 500m-2000m CPU, 512Mi-2Gi memory

## Endpoints
- **API:** https://api.tokenopt.yourcompany.com
- **Grafana:** https://grafana.tokenopt.yourcompany.com
- **Prometheus:** https://prometheus.tokenopt.yourcompany.com

## Secrets
- JWT_SECRET: [REDACTED]
- ENCRYPTION_KEY: [REDACTED]
- Database: tokenopt-production.cluster-xxx.us-east-1.rds.amazonaws.com
- Redis: tokenopt-production.xxx.cache.amazonaws.com

## Verification
- [x] Health checks passing
- [x] TLS certificate valid
- [x] Database migrations applied
- [x] Monitoring dashboards configured
- [x] Alerts configured
- [x] Load test passed (100 RPS, P95 < 1s)
- [x] WAF enabled
- [x] Backup configured
EOF

cat DEPLOYMENT_MANIFEST.md
```

---

## Appendix A: Rollback Procedures

### A.1: Rollback Application Version

```bash
# Rollback to previous Helm revision
helm rollback tokenopt 1 -n tokenopt

# Or deploy specific version
helm upgrade tokenopt .   --namespace tokenopt   --set image.tag=v1.9.0   --wait
```

### A.2: Rollback Infrastructure

```bash
# Restore from Terraform state backup
cd ~/tokenopt-enterprise/infrastructure/terraform
terraform state pull > terraform-backup-$(date +%Y%m%d).tfstate

# If needed, restore from backup
terraform init
terraform apply -backup=terraform-backup-$(date +%Y%m%d).tfstate
```

### A.3: Database Rollback

```bash
# Restore from RDS snapshot
aws rds restore-db-instance-from-db-snapshot   --db-instance-identifier tokenopt-production-restored   --db-snapshot-identifier tokenopt-pre-upgrade-YYYYMMDD   --db-instance-class db.r6g.xlarge
```

---

## Appendix B: Cost Optimization

### B.1: Reserved Instances

```bash
# Purchase Reserved Instances for steady-state workloads
aws ec2 purchase-reserved-instances-offering   --instance-count 3   --reserved-instances-offering-id <offering-id>   --region us-east-1
```

### B.2: Savings Plans

```bash
# Compute Savings Plans for EKS nodes
aws savingsplans create-savings-plan   --savings-plan-offering-id <offering-id>   --commitment 100.0   --upfront-payment-option PARTIAL
```

---

**Document Owner:** Platform Engineering  
**Last Updated:** July 2026  
**Next Review:** August 2026
