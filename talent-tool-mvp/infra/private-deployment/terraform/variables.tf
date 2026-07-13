# v7.0 T3003 — Terraform variables for Waibao private deployment
#
# See main.tf for usage. Required:
#   - tenant_id      (string)
#   - domain         (string)
#   - route53_zone_id (string)
#   - db_password    (string, sensitive)
#
# Optional (defaults in main.tf):
#   - aws_region
#   - vpc_cidr
#   - eks_instance_type
#   - eks_min_size
#   - eks_max_size

# This file is intentionally short — most variables are declared
# inline in main.tf to keep the docs in one place. We keep it here
# for future extraction if the module grows beyond ~10 variables.

variable "extra_tags" {
  type        = map(string)
  default     = {}
  description = "Additional tags to apply to every resource."
}