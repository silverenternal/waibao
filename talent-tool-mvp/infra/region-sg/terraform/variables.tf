# waibao region-sg variables

variable "rds_sg_ro_password" {
  description = "RDS SG 只读副本密码"
  type        = string
  sensitive   = true
}

variable "domain" {
  type    = string
  default = "waibao.io"
}
