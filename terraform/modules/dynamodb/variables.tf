variable "project_name" {
  type        = string
  description = "Project name used for resource naming"
}

variable "environment" {
  type        = string
  description = "Deployment environment"
}

variable "session_ttl_days" {
  type        = number
  description = "Number of days before session data expires"
}
