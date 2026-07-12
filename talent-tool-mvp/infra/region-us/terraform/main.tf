# =============================================================================
# waibao region-us (AWS us-west-1 Oregon) — Terraform IaC
# T1503 多区域部署
# =============================================================================
terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.40" }
  }
  backend "s3" {
    bucket = "waibao-tfstate-us"
    key    = "prod/region-us/terraform.tfstate"
    region = "us-west-1"
    encrypt = true
  }
}

provider "aws" {
  region = "us-west-1"
  default_tags {
    tags = {
      Project    = "waibao"
      Region     = "us"
      Env        = "production"
      ManagedBy  = "terraform"
      Compliance = "GDPR,CCPA,SOC2-Type-II"
    }
  }
}

# ---------- VPC (10.30.0.0/16) ----------
resource "aws_vpc" "waibao_us" {
  cidr_block           = "10.30.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = { Name = "waibao-us-vpc" }
}

data "aws_availability_zones" "available_us" {
  provider = aws
  state    = "available"
}

resource "aws_subnet" "public_us" {
  count                   = 3
  vpc_id                  = aws_vpc.waibao_us.id
  cidr_block              = "10.30.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available_us.names[count.index]
  map_public_ip_on_launch = true
  tags = { Name = "waibao-us-public-${count.index}" }
}

resource "aws_subnet" "private_us" {
  count             = 3
  vpc_id            = aws_vpc.waibao_us.id
  cidr_block        = "10.30.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available_us.names[count.index]
  tags = { Name = "waibao-us-private-${count.index}" }
}

# ---------- 安全组 ----------
resource "aws_security_group" "backend_us" {
  name        = "waibao-us-backend"
  description = "Backend API + workers (us-west-1)"
  vpc_id      = aws_vpc.waibao_us.id

  ingress {
    description = "HTTPS from ALB"
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["10.30.0.0/16"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---------- RDS PostgreSQL 主库 (US 写主) ----------
resource "aws_db_subnet_group" "waibao_us" {
  name       = "waibao-us"
  subnet_ids = aws_subnet.private_us[*].id
}

resource "aws_db_instance" "waibao_us_primary" {
  identifier              = "waibao-us-rds-primary"
  engine                  = "postgres"
  engine_version          = "15.6"
  instance_class          = "db.m6g.large"
  allocated_storage       = 200
  max_allocated_storage   = 1000
  storage_type            = "gp3"
  storage_encrypted       = true
  kms_key_id              = aws_kms_key.waibao_us.arn
  username                = "waibao_app"
  password                = var.rds_us_password
  db_subnet_group_name    = aws_db_subnet_group.waibao_us.name
  vpc_security_group_ids  = [aws_security_group.backend_us.id]
  publicly_accessible     = false
  multi_az                = true
  backup_retention_period = 14
  backup_window           = "06:00-07:00"
  maintenance_window      = "Sun:07:00-Sun:08:00"
  deletion_protection     = true
  skip_final_snapshot     = false
  final_snapshot_identifier = "waibao-us-final"
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.waibao_us.arn
}

# ---------- ElastiCache Redis 7.0 ----------
resource "aws_elasticache_subnet_group" "waibao_us" {
  name       = "waibao-us"
  subnet_ids = aws_subnet.private_us[*].id
}

resource "aws_elasticache_replication_group" "waibao_us" {
  replication_group_id       = "waibao-us-redis"
  description                = "waibao US Redis cluster"
  engine                     = "redis"
  engine_version             = "7.0"
  node_type                  = "cache.m6g.large"
  num_cache_clusters         = 3
  parameter_group_name       = "default.redis7"
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.waibao_us.name
  security_group_ids         = [aws_security_group.backend_us.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = true
  snapshot_retention_limit   = 7
  snapshot_window            = "03:00-05:00"
}

# ---------- KMS ----------
resource "aws_kms_key" "waibao_us" {
  description             = "waibao US KMS key (PII / RDS / S3 / EBS)"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false
}

resource "aws_kms_alias" "waibao_us" {
  name          = "alias/waibao-us"
  target_key_id = aws_kms_key.waibao_us.key_id
}

# ---------- EKS ----------
module "eks_us" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "waibao-us"
  cluster_version = "1.30"
  vpc_id          = aws_vpc.waibao_us.id
  subnet_ids      = aws_subnet.private_us[*].id

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  eks_managed_node_groups = {
    main = {
      desired_size = 3
      min_size     = 3
      max_size     = 12

      instance_types = ["t3.large"]
      capacity_type  = "ON_DEMAND"
    }
  }

  tags = { "k8s.io/cluster-autoscaler/enabled" = "true" }
}

# ---------- S3 (美国主备份桶) ----------
resource "aws_s3_bucket" "backups_us" {
  bucket = "waibao-us-backups"
  tags = { Purpose = "region-us-primary-backup" }
}

resource "aws_s3_bucket_versioning" "backups_us" {
  bucket = aws_s3_bucket.backups_us.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_replication_configuration" "backups_us" {
  depends_on = [aws_s3_bucket_versioning.backups_us]
  role       = aws_iam_role.replication.arn
  bucket     = aws_s3_bucket.backups_us.id
  rule {
    id     = "replicate-to-sg"
    status = "Enabled"
    destination {
      bucket        = "arn:aws:s3:::waibao-sg-backups"
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_iam_role" "replication" {
  name = "waibao-backup-replication"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "s3.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

# ---------- CloudWatch ----------
resource "aws_cloudwatch_log_group" "app_us" {
  name              = "/aws/eks/waibao-us/app"
  retention_in_days = 90
}
