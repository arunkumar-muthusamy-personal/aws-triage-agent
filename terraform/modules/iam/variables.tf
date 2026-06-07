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

variable "sessions_table_arn" {
  type        = string
  description = "ARN of the sessions DynamoDB table"
}

variable "messages_table_arn" {
  type        = string
  description = "ARN of the messages DynamoDB table"
}
