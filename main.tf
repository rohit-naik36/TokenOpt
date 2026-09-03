# ============================================================
# TokenOpt Enterprise v2.0 - AWS Infrastructure
# EKS + RDS PostgreSQL + ElastiCache Redis + ALB + Route53
# ============================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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
      Project     = "tokenopt"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# VPC
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  name    = "tokenopt-${var.environment}"
  cidr    = var.vpc_cidr
  azs     = var.availability_zones
  private_subnets = var.private_subnets
  public_subnets  = var.public_subnets
  enable_nat_gateway   = true
  single_nat_gateway   = var.environment == "staging"
  enable_dns_hostnames = true
  public_subnet_tags   = { "kubernetes.io/role/elb" = "1" }
  private_subnet_tags  = { "kubernetes.io/role/internal-elb" = "1" }
}

# EKS
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"
  cluster_name    = "tokenopt-${var.environment}"
  cluster_version = "1.29"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets
  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true
  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true }
  }
  eks_managed_node_groups = {
    general = {
      desired_size = var.node_desired_size
      min_size     = var.node_min_size
      max_size     = var.node_max_size
      instance_types = var.node_instance_types
      capacity_type  = var.environment == "production" ? "ON_DEMAND" : "SPOT"
      labels = { workload = "general" }
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs = {
            volume_size = 100
            volume_type = "gp3"
            encrypted   = true
            kms_key_id  = aws_kms_key.ebs.arn
          }
        }
      }
    }
  }
  enable_irsa = true
}

# KMS
resource "aws_kms_key" "ebs" {
  description             = "KMS key for EBS encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true
}

# RDS PostgreSQL
resource "aws_db_subnet_group" "tokenopt" {
  name       = "tokenopt-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name_prefix = "tokenopt-rds-"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }
}

module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "~> 6.0"
  identifier           = "tokenopt-${var.environment}"
  engine               = "postgres"
  engine_version       = "15.4"
  family               = "postgres15"
  instance_class       = var.rds_instance_class
  allocated_storage    = 100
  max_allocated_storage = 1000
  storage_encrypted    = true
  kms_key_id           = aws_kms_key.rds.arn
  db_name              = "tokenopt"
  username             = "tokenopt_admin"
  multi_az             = var.environment == "production"
  db_subnet_group_name = aws_db_subnet_group.tokenopt.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  backup_retention_period = var.environment == "production" ? 30 : 7
  deletion_protection  = var.environment == "production"
  skip_final_snapshot  = var.environment != "production"
}

# ElastiCache Redis
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
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_elasticache_replication_group" "tokenopt" {
  replication_group_id = "tokenopt-${var.environment}"
  description          = "TokenOpt Redis"
  node_type            = var.redis_node_type
  num_cache_clusters   = var.environment == "production" ? 3 : 2
  automatic_failover_enabled = true
  multi_az_enabled           = var.environment == "production"
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  subnet_group_name  = aws_elasticache_subnet_group.tokenopt.name
  security_group_ids = [aws_security_group.redis.id]
}

# ALB
module "alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "~> 9.0"
  name               = "tokenopt-${var.environment}"
  load_balancer_type = "application"
  internal           = false
  vpc_id             = module.vpc.vpc_id
  subnets            = module.vpc.public_subnets
  security_groups    = [aws_security_group.alb.id]
  listeners = {
    https = {
      port            = 443
      protocol        = "HTTPS"
      certificate_arn = aws_acm_certificate.tokenopt.arn
      fixed_response = {
        content_type = "text/plain"
        message_body = "OK"
        status_code  = "200"
      }
    }
  }
}

resource "aws_security_group" "alb" {
  name_prefix = "tokenopt-alb-"
  vpc_id      = module.vpc.vpc_id
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Route53 + ACM
resource "aws_acm_certificate" "tokenopt" {
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_route53_record" "tokenopt" {
  zone_id = var.route53_zone_id
  name    = var.domain_name
  type    = "A"
  alias {
    name                   = module.alb.dns_name
    zone_id                = module.alb.zone_id
    evaluate_target_health = true
  }
}

# Secrets Manager
resource "aws_secretsmanager_secret" "tokenopt" {
  name        = "tokenopt/${var.environment}/api-keys"
  kms_key_id  = aws_kms_key.ebs.arn
}

resource "aws_secretsmanager_secret_version" "tokenopt" {
  secret_id = aws_secretsmanager_secret.tokenopt.id
  secret_string = jsonencode({
    openai_api_key    = var.openai_api_key
    azure_openai_key  = var.azure_openai_key
    anthropic_api_key = var.anthropic_api_key
    jwt_secret        = var.jwt_secret
    encryption_key    = var.encryption_key
  })
}

# CloudWatch
resource "aws_cloudwatch_log_group" "tokenopt" {
  name              = "/tokenopt/${var.environment}"
  retention_in_days = var.environment == "production" ? 90 : 30
  kms_key_id        = aws_kms_key.ebs.arn
}
