# =============================================================================
# waibao region-sg (AWS ap-southeast-1 Singapore) — Terraform IaC
# T1503 多区域部署
# =============================================================================
terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
  backend "s3" {
    bucket = "waibao-tfstate-sg"
    key    = "prod/region-sg/terraform.tfstate"
    region = "ap-southeast-1"
    encrypt = true
  }
}

provider "aws" {
  region = "ap-southeast-1"
  default_tags {
    tags = {
      Project    = "waibao"
      Region     = "sg"
      Env        = "production"
      ManagedBy  = "terraform"
      Compliance = "GDPR,PDPA-SG"
    }
  }
}

# ---------- VPC (10.20.0.0/16) ----------
resource "aws_vpc" "waibao_sg" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "waibao-sg-vpc" }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.waibao_sg.id
  cidr_block              = "10.20.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true
  tags = { Name = "waibao-sg-public-${count.index}" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.waibao_sg.id
  cidr_block        = "10.20.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags = { Name = "waibao-sg-private-${count.index}" }
}

# ---------- 安全组 ----------
resource "aws_security_group" "backend" {
  name        = "waibao-sg-backend"
  description = "Backend API + workers"
  vpc_id      = aws_vpc.waibao_sg.id

  ingress {
    description = "HTTPS from ALB"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["10.20.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------- RDS PostgreSQL (cross-region replica, 只读) ----------
resource "aws_db_subnet_group" "waibao_sg" {
  name       = "waibao-sg"
  subnet_ids = aws_subnet.private[*].id
}

# 此实例作为 region-cn 主库的跨区域只读副本 (单向同步, read-only)
# 由 ops 手动或 scheduled lambda 触发: RDS Cross-Region Read Replica
resource "aws_db_instance" "waibao_sg_ro" {
  identifier              = "waibao-sg-rds-ro"
  engine                  = "postgres"
  engine_version          = "15.6"
  instance_class          = "db.t4g.medium"
  allocated_storage       = 100
  storage_type            = "gp3"
  storage_encrypted       = true
  kms_key_id              = aws_kms_key.waibao_sg.arn
  username                = "waibao_ro"
  password                = var.rds_sg_ro_password
  db_subnet_group_name    = aws_db_subnet_group.waibao_sg.name
  vpc_security_group_ids  = [aws_security_group.backend.id]
  publicly_accessible     = false
  multi_az                = true
  backup_retention_period = 7
  backup_window           = "02:00-03:00"
  maintenance_window      = "Sun:03:00-Sun:04:00"
  deletion_protection     = true
  skip_final_snapshot     = false
  final_snapshot_identifier = "waibao-sg-final"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  tags = { Role = "read-replica-of-cn" }
}

# ---------- ElastiCache Redis 7.0 ----------
resource "aws_elasticache_subnet_group" "waibao_sg" {
  name       = "waibao-sg"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_elasticache_replication_group" "waibao_sg" {
  replication_group_id       = "waibao-sg-redis"
  description                = "waibao SG Redis cluster"
  engine                     = "redis"
  engine_version             = "7.0"
  node_type                  = "cache.t4g.medium"
  num_cache_clusters         = 2
  parameter_group_name       = "default.redis7"
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.waibao_sg.name
  security_group_ids         = [aws_security_group.backend.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = true
  snapshot_retention_limit   = 5
  snapshot_window            = "03:00-05:00"
}

# ---------- KMS (PII 加密) ----------
resource "aws_kms_key" "waibao_sg" {
  description             = "waibao SG KMS key (PII / RDS / S3)"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false
}

resource "aws_kms_alias" "waibao_sg" {
  name          = "alias/waibao-sg"
  target_key_id = aws_kms_key.waibao_sg.key_id
}

# ---------- EKS ----------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "waibao-sg"
  cluster_version = "1.30"
  vpc_id          = aws_vpc.waibao_sg.id
  subnet_ids      = aws_subnet.private[*].id

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  eks_managed_node_groups = {
    main = {
      desired_size = 2
      min_size     = 2
      max_size     = 8

      instance_types = ["t3.medium"]
      capacity_type  = "ON_DEMAND"
    }
  }

  tags = { "k8s.io/cluster-autoscaler/enabled" = "true" }
}

# ---------- S3 (region-isolated backups) ----------
resource "aws_s3_bucket" "backups" {
  bucket = "waibao-sg-backups"
  tags = { Purpose = "region-sg-backup" }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id
  rule {
    id     = "archive"
    status = "Enabled"
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    expiration { days = 730 }  # 2 年
  }
}

# ---------- CloudWatch Logs ----------
resource "aws_cloudwatch_log_group" "app" {
  name              = "/aws/eks/waibao-sg/app"
  retention_in_days = 90
}
