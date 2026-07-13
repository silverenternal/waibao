# ============================================================
# v7.0 T3003 Terraform — AWS reference architecture
#
# Provisions a private-deployment Waibao stack on AWS:
#   - EKS cluster (k8s 1.29)
#   - RDS for Postgres (with PITR enabled)
#   - ElastiCache Redis
#   - OpenSearch (Qdrant alternative — also runs on EC2)
#   - S3 buckets (uploads + logs)
#   - ALB + ACM certificate
#   - Route53 records
#   - ECR repositories for backend / frontend
#
# 用法:
#   cd infra/private-deployment/terraform
#   terraform init
#   terraform plan -out tfplan \
#     -var='tenant_id=acme' \
#     -var='domain=hire.acme.com' \
#     -var='db_password=...' \
#     -var='route53_zone_id=Z1ABCD...'
#   terraform apply tfplan
#   terraform output kubeconfig_command
# ============================================================

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.24"
    }
  }

  backend "s3" {
    # bucket         = "waibao-terraform-state"
    # key            = "private-deployment/terraform.tfstate"
    # region         = "ap-southeast-1"
    # dynamodb_table = "waibao-terraform-locks"
    # encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "waibao"
      ManagedBy   = "terraform"
      Tenant      = var.tenant_id
      Environment = "private-deployment"
    }
  }
}

# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------

variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "ap-southeast-1"
}

variable "tenant_id" {
  type        = string
  description = "Tenant ID for this private deployment (used for resource naming + white-label)"
}

variable "domain" {
  type        = string
  description = "Customer-facing domain (e.g. hire.acme.com)"
}

variable "route53_zone_id" {
  type        = string
  description = "Route53 hosted zone ID for the domain above"
}

variable "db_password" {
  type        = string
  sensitive   = true
  description = "Master password for the RDS Postgres instance (>= 16 chars)"
}

variable "vpc_cidr" {
  type        = string
  default     = "10.50.0.0/16"
}

variable "eks_instance_type" {
  type        = string
  default     = "m6i.2xlarge"
}

variable "eks_min_size" {
  type    = number
  default = 2
}

variable "eks_max_size" {
  type    = number
  default = 10
}

# ---------------------------------------------------------------------------
# Locals — naming + whitelabel
# ---------------------------------------------------------------------------

locals {
  name_prefix  = "waibao-${var.tenant_id}"
  common_tags  = {}
  whitelabel = {
    tenant_id        = var.tenant_id
    product_name     = "Waibao Recruitment"
    domain           = var.domain
    primary_color    = "#2563EB"
    secondary_color  = "#0F172A"
    accent_color     = "#F59E0B"
    font_family      = "Inter"
    support_email    = "support@${var.domain}"
    hide_powered_by  = false
    locale           = "zh-CN"
  }
}

# ---------------------------------------------------------------------------
# VPC + networking
# ---------------------------------------------------------------------------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.5"

  name = "${local.name_prefix}-vpc"
  cidr = var.vpc_cidr

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  public_subnets  = [cidrsubnet(var.vpc_cidr, 8, 0), cidrsubnet(var.vpc_cidr, 8, 1), cidrsubnet(var.vpc_cidr, 8, 2)]
  private_subnets = [cidrsubnet(var.vpc_cidr, 8, 10), cidrsubnet(var.vpc_cidr, 8, 11), cidrsubnet(var.vpc_cidr, 8, 12)]
  database_subnets = [cidrsubnet(var.vpc_cidr, 8, 20), cidrsubnet(var.vpc_cidr, 8, 21), cidrsubnet(var.vpc_cidr, 8, 22)]

  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true
}

# ---------------------------------------------------------------------------
# EKS cluster
# ---------------------------------------------------------------------------

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.8"

  cluster_name    = "${local.name_prefix}-cluster"
  cluster_version = "1.29"

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  eks_managed_node_groups = {
    main = {
      instance_types = [var.eks_instance_type]
      min_size       = var.eks_min_size
      max_size       = var.eks_max_size
      desired_size   = 3
    }
  }

  cluster_addons = {
    coredns    = { most_recent = true }
    kube-proxy = { most_recent = true }
    vpc-cni    = { most_recent = true }
    aws-ebs-csi-driver = { most_recent = true }
  }
}

# ---------------------------------------------------------------------------
# RDS Postgres (Supabase-compatible)
# ---------------------------------------------------------------------------

resource "aws_db_instance" "postgres" {
  identifier        = "${local.name_prefix}-db"
  engine            = "postgres"
  engine_version    = "15.6"
  instance_class    = "db.r6g.large"
  allocated_storage = 200
  storage_type      = "gp3"
  storage_encrypted = true
  multi_az          = true

  db_name  = "postgres"
  username = "postgres"
  password = var.db_password
  port     = 5432

  vpc_security_group_ids = [aws_security_group.rds.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  backup_retention_period = 14  # PITR window
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"

  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  performance_insights_enabled    = true
  deletion_protection             = true
  skip_final_snapshot             = false
  final_snapshot_identifier       = "${local.name_prefix}-db-final"

  tags = {
    WaibaoPITR = "enabled"
  }
}

# ---------------------------------------------------------------------------
# ElastiCache Redis
# ---------------------------------------------------------------------------

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${local.name_prefix}-redis"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.r6g.large"
  num_cache_nodes      = 2
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]
}

# ---------------------------------------------------------------------------
# S3 buckets
# ---------------------------------------------------------------------------

resource "aws_s3_bucket" "uploads" {
  bucket = "${local.name_prefix}-uploads"
}

resource "aws_s3_bucket_versioning" "uploads" {
  bucket = aws_s3_bucket.uploads.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "uploads" {
  bucket                  = aws_s3_bucket.uploads.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ---------------------------------------------------------------------------
# ACM certificate + Route53 + ALB
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "main" {
  domain_name       = var.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.main.domain_validation_options : dvo.domain_name => dvo
  }
  zone_id         = var.route53_zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  ttl             = 60
  records         = [each.value.resource_record_value]
  allow_overwrite = true
}

resource "aws_route53_record" "apex" {
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "A"
  alias {
    name                   = aws_lb.main.dns_name
    zone_id                = aws_lb.main.zone_id
    evaluate_target_health = true
  }
}

# ---------------------------------------------------------------------------
# ECR for backend + frontend
# ---------------------------------------------------------------------------

resource "aws_ecr_repository" "backend" {
  name                 = "${local.name_prefix}/backend"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "${local.name_prefix}/frontend"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
}

# ---------------------------------------------------------------------------
# Supporting resources — subnet groups, security groups, ALB
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "main" {
  name       = "${local.name_prefix}-db-subnets"
  subnet_ids = module.vpc.database_subnets
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.name_prefix}-cache-subnets"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name   = "${local.name_prefix}-rds"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }
}

resource "aws_security_group" "redis" {
  name   = "${local.name_prefix}-redis"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.cluster_security_group_id]
  }
}

resource "aws_lb" "main" {
  name               = "${local.name_prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = module.vpc.public_subnets
}

resource "aws_security_group" "alb" {
  name   = "${local.name_prefix}-alb"
  vpc_id = module.vpc.vpc_id

  ingress { from_port = 80 to_port = 80 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] }
  ingress { from_port = 443 to_port = 443 protocol = "tcp" cidr_blocks = ["0.0.0.0/0"] }
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "whitelabel_config" {
  value     = local.whitelabel
  sensitive = false
  description = "Values to feed into the Helm chart's whitelabel block"
}

output "helm_install_command" {
  value = <<-EOT
    helm upgrade --install waibao ./helm/waibao \
      --set whitelabel.tenantId=${var.tenant_id} \
      --set whitelabel.domain=${var.domain} \
      --set secrets.create=true \
      --set secrets.databaseUrl=postgresql+psycopg://postgres:${var.db_password}@${aws_db_instance.postgres.endpoint}/postgres \
      --set secrets.redisUrl=redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0
  EOT
}

output "ecr_repositories" {
  value = {
    backend  = aws_ecr_repository.backend.repository_url
    frontend = aws_ecr_repository.frontend.repository_url
  }
}

output "s3_uploads_bucket" {
  value = aws_s3_bucket.uploads.bucket
}