# =============================================================================
# waibao region-cn — outputs.tf
# =============================================================================

output "rds_endpoint" {
  description = "RDS 内网连接"
  value       = alicloud_db_instance.waibao_cn_rds.connection_string
}

output "redis_endpoint" {
  description = "Redis 内网连接"
  value       = "${alicloud_redis_instance.waibao_cn.connection_domain}:6379"
}

output "oss_bucket" {
  description = "OSS Bucket"
  value       = alicloud_oss_bucket.waibao_cn.bucket
}

output "ack_cluster_id" {
  description = "ACK 集群 ID"
  value       = alicloud_cs_managed_kubernetes.waibao_cn.id
}

output "ack_kubeconfig" {
  description = "ACK kubeconfig (敏感)"
  value       = alicloud_cs_managed_kubernetes.waibao_cn.kubeconfig
  sensitive   = true
}

output "log_project" {
  description = "日志项目名"
  value       = alicloud_log_project.waibao_cn.name
}
