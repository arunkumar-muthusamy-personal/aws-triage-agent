variable "project_name" {
  type        = string
  description = "Project name used for resource naming"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
}

variable "api_gateway_url" {
  type        = string
  description = "API Gateway invoke URL to inject into the frontend build"
}
