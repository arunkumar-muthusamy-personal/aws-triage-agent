variable "project_name" {
  type        = string
  description = "Project name used for resource naming"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
}

variable "aws_region" {
  type        = string
  description = "AWS region"
}

variable "vpc_id" {
  type        = string
  description = "ID of existing VPC"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs for ECS tasks and internal ALB"
}

variable "ecr_repository_url" {
  type        = string
  description = "ECR repository URL for the agent image"
}

variable "task_role_arn" {
  type        = string
  description = "ARN of the ECS task role"
}

variable "execution_role_arn" {
  type        = string
  description = "ARN of the ECS execution role"
}

variable "sessions_table_name" {
  type        = string
  description = "DynamoDB sessions table name"
}

variable "messages_table_name" {
  type        = string
  description = "DynamoDB messages table name"
}

variable "alb_security_group_id" {
  type        = string
  description = "Security group ID for the ALB"
}

variable "ecs_security_group_id" {
  type        = string
  description = "Security group ID for ECS tasks"
}

variable "ecs_cpu" {
  type        = number
  description = "ECS task CPU units"
}

variable "ecs_memory" {
  type        = number
  description = "ECS task memory in MiB"
}

variable "max_tool_iterations" {
  type        = number
  description = "Maximum tool iterations per agent run"
}
