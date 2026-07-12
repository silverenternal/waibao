# =============================================================================
# waibao region-cn — variables.tf
# =============================================================================

variable "region" {
  description = "阿里云区域"
  type        = string
  default     = "cn-hangzhou"
}

variable "rds_password" {
  description = "RDS PostgreSQL 主密码 (从环境变量 TF_VAR_rds_password 注入)"
  type        = string
  sensitive   = true
}

variable "redis_password" {
  description = "Redis 密码 (从环境变量 TF_VAR_redis_password 注入)"
  type        = string
  sensitive   = true
}

variable "oss_access_key_id" {
  type      = string
  sensitive = true
}

variable "oss_access_key_secret" {
  type      = string
  sensitive = true
}

variable "domain_apex" {
  description = "主域"
  type        = string
  default     = "waibao.cn"
}

variable "icp_license" {
  description = "ICP 备案号"
  type        = string
  default     = "京ICP备2024xxxxxx号-1"
}

variable "log_retention_days" {
  description = "审计日志留存天数 (MLPS 2.0 要求 ≥180)"
  type        = number
  default     = 180
}

variable "backup_retention_days" {
  description = "RDS 自动备份留存天数"
  type        = number
  default     = 7
}
