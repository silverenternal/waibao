# waibao region-us outputs

output "eks_cluster_endpoint" {
  value = module.eks_us.cluster_endpoint
}

output "eks_cluster_name" {
  value = module.eks_us.cluster_name
}

output "rds_endpoint" {
  value = aws_db_instance.waibao_us_primary.address
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.waibao_us.primary_endpoint_address
}

output "kms_key_arn" {
  value = aws_kms_key.waibao_us.arn
}
