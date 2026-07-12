# =============================================================================
# waibao region-cn (阿里云 cn-hangzhou) — Terraform IaC
# T1503 多区域部署
# =============================================================================
terraform {
  required_version = ">= 1.7"
  required_providers {
    alicloud = { source = "aliyun/alicloud", version = "~> 1.220" }
  }
  backend "oss" {
    bucket = "waibao-tfstate-cn"
    key    = "prod/region-cn/terraform.tfstate"
    region = "cn-hangzhou"
  }
}

provider "alicloud" {
  region = "cn-hangzhou"
}

# ---------- 资源组 + 标签 ----------
resource "alicloud_resource_manager_resource_group" "waibao_cn" {
  resource_group_name = "waibao-cn-prod"
  display_name        = "waibao 中国生产"
}

locals {
  common_tags = {
    Project     = "waibao"
    Region      = "cn"
    Env         = "production"
    ManagedBy   = "terraform"
    Compliance  = "PIPL,MLPS-2.0"
    BackupPolicy = "daily-7d,weekly-90d"
  }
}

# ---------- VPC ----------
resource "alicloud_vpc" "waibao_cn" {
  name       = "waibao-cn-vpc"
  cidr_block = "10.10.0.0/16"
  resource_group_id = alicloud_resource_manager_resource_group.waibao_cn.id
  tags = local.common_tags
}

resource "alicloud_vswitch" "waibao_cn_a" {
  vpc_id       = alicloud_vpc.waibao_cn.id
  cidr_block   = "10.10.1.0/24"
  zone_id      = "cn-hangzhou-h"
  name         = "waibao-cn-vsw-a"
}

resource "alicloud_vswitch" "waibao_cn_b" {
  vpc_id       = alicloud_vpc.waibao_cn.id
  cidr_block   = "10.10.2.0/24"
  zone_id      = "cn-hangzhou-i"
  name         = "waibao-cn-vsw-b"
}

# ---------- 安全组 ----------
resource "alicloud_security_group" "waibao_cn_backend" {
  name        = "waibao-cn-backend-sg"
  vpc_id      = alicloud_vpc.waibao_cn.id
  description = "Backend API + workers"
  resource_group_id = alicloud_resource_manager_resource_group.waibao_cn.id
}

resource "alicloud_security_group_rule" "backend_in_https" {
  type              = "ingress"
  ip_protocol       = "tcp"
  port_range        = "8000/8000"
  security_group_id = alicloud_security_group.waibao_cn_backend.id
  cidr_ip           = "10.10.0.0/16"   # 仅 VPC 内
  description       = "Backend HTTP from SLB"
}

# ---------- RDS PostgreSQL 15 (主 + 只读) ----------
resource "alicloud_db_instance" "waibao_cn_rds" {
  engine               = "PostgreSQL"
  engine_version       = "15.0"
  instance_type        = "pg.n4.2c.4m"           # 2 vCPU 4 GB
  instance_storage     = 100
  storage_type         = "cloud_essd"
  instance_charge_type = "Postpaid"
  db_instance_class    = "pg.n4.2c.4m"
  vswitch_id           = alicloud_vswitch.waibao_cn_a.id
  security_group_ids   = [alicloud_security_group.waibao_cn_backend.id]
  db_name              = "waibao"
  username             = "waibao_app"
  password             = var.rds_password
  backup_retention_period = 7
  backup_time          = "02:00Z-03:00Z"         # 北京时间 10:00-11:00
  log_backup            = true
  log_backup_retention_period = 30
  sql_collector_status = "Enabled"
  audit_log_retention_period = 90                  # MLPS 合规
  resource_group_id    = alicloud_resource_manager_resource_group.waibao_cn.id
  tags = local.common_tags
}

resource "alicloud_db_readonly_instance" "waibao_cn_rds_ro" {
  master_db_instance_id = alicloud_db_instance.waibao_cn_rds.id
  engine_version        = "15.0"
  instance_type         = "pg.n4.1c.2m"           # 1 vCPU 2 GB
  instance_storage      = 100
  vswitch_id            = alicloud_vswitch.waibao_cn_b.id
  instance_name         = "waibao-cn-rds-ro"
}

# ---------- 阿里云 Redis (主从) ----------
resource "alicloud_redis_instance" "waibao_cn" {
  instance_class       = "redis.n4.small.1"   # 1 GB
  vswitch_id           = alicloud_vswitch.waibao_cn_a.id
  security_group_ids   = [alicloud_security_group.waibao_cn_backend.id]
  instance_name        = "waibao-cn-redis"
  engine_version       = "7.0"
  instance_charge_type = "Postpaid"
  backup_policy = [{
    backup_time      = "02:00-03:00"
    backup_period    = ["Monday", "Wednesday", "Friday"]
    retention        = 7
  }]
  resource_group_id = alicloud_resource_manager_resource_group.waibao_cn.id
  tags = local.common_tags
}

# ---------- OSS 存储桶 ----------
resource "alicloud_oss_bucket" "waibao_cn" {
  bucket = "waibao-cn-prod"
  acl    = "private"
  versioning = {
    status = "Enabled"
  }
  server_side_encryption = {
    enabled = true
    sse_algorithm = "KMS"
  }
  replication = [{
    rule_name = "oss-replication-to-oss-cn-shanghai"
    destination = {
      bucket = "acs:oss:cn-shanghai:waibao-backup:waibao-cn-prod-backup"
    }
  }]
  lifecycle_rule = [{
    id      = "cleanup-temp"
    enabled = true
    expiration { days = 30 }
  }]
  resource_group_id = alicloud_resource_manager_resource_group.waibao_cn.id
  tags = local.common_tags
}

# ---------- 阿里云 SLB (内网) ----------
resource "alicloud_slb" "waibao_cn_internal" {
  name          = "waibao-cn-slb-internal"
  vswitch_id    = alicloud_vswitch.waibao_cn_a.id
  specification = "slb.s2.small"
  internet      = false
  bandwidth     = 5
  resource_group_id = alicloud_resource_manager_resource_group.waibao_cn.id
  tags = local.common_tags
}

# ---------- ACK 集群 ----------
resource "alicloud_cs_managed_kubernetes" "waibao_cn" {
  name                     = "waibao-cn-ack"
  cluster_spec            = "ack.pro.small"          # 生产专业版
  version                 = "1.30.0-aliyun.1"
  vpc_id                  = alicloud_vpc.waibao_cn.id
  vswitch_ids             = [alicloud_vswitch.waibao_cn_a.id, alicloud_vswitch.waibao_cn_b.id]
  new_nat_gateway         = true
  new_snat_entry          = true
  slb_internet_enabled    = false
  resource_group_id       = alicloud_resource_manager_resource_group.waibao_cn.id
  tags                    = local.common_tags
  deletion_protection     = true
}

# ---------- 日志 (合规留存 180 天) ----------
resource "alicloud_log_project" "waibao_cn" {
  name        = "waibao-cn-logs"
  description = "审计 / 业务 / 安全日志 (MLPS 2.0)"
  resource_group_id = alicloud_resource_manager_resource_group.waibao_cn.id
  tags = local.common_tags
}
