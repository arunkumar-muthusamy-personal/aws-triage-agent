variable "project_name" {
  type        = string
  description = "Project name used for resource naming"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
}

variable "vpc_id" {
  type        = string
  description = "ID of existing VPC"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs"
}

variable "use_vpc_endpoints" {
  type        = bool
  description = "Whether to create VPC endpoints"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
}
