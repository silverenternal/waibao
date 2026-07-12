# waibao region-us variables

variable "rds_us_password" {
  description = "RDS US 主密码"
  type        = string
  sensitive   = true
}

variable "domain" {
  type    = string
  default = "waibao.io"
}
