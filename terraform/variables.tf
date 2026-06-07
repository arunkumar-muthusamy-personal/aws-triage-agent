variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region to deploy resources"
}

variable "environment" {
  type        = string
  default     = "dev"
  description = "Deployment environment (dev, prod)"
}

variable "project_name" {
  type        = string
  default     = "aws-triage-agent"
  description = "Project name used for resource naming"
}

variable "vpc_id" {
  type        = string
  description = "ID of existing VPC"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for ECS tasks"
}

variable "public_subnet_ids" {
  type        = list(string)
  description = "Public subnet IDs for ALB"
}

variable "use_vpc_endpoints" {
  type        = bool
  default     = true
  description = "Create VPC endpoints for Bedrock/DynamoDB/CW if they don't exist"
}

variable "ecs_cpu" {
  type        = number
  default     = 1024
  description = "ECS task CPU units"
}

variable "ecs_memory" {
  type        = number
  default     = 2048
  description = "ECS task memory in MiB"
}

variable "session_ttl_days" {
  type        = number
  default     = 30
  description = "Number of days before session data expires"
}

variable "max_tool_iterations" {
  type        = number
  default     = 15
  description = "Maximum tool iterations per agent run"
}
