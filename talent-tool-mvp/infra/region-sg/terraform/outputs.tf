# waibao region-sg outputs

output "eks_cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "rds_endpoint" {
  value = aws_db_instance.waibao_sg_ro.address
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.waibao_sg.primary_endpoint_address
}

output "kms_key_arn" {
  value = aws_kms_key.waibao_sg.arn
}
