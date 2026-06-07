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

variable "alb_listener_arn" {
  type        = string
  description = "ARN of the ALB listener to route traffic to"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for the VPC Link"
}

variable "ecs_security_group_id" {
  type        = string
  description = "Security group ID for ECS tasks (used by VPC Link)"
}
