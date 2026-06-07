output "sessions_table_name" {
  description = "Sessions DynamoDB table name"
  value       = aws_dynamodb_table.sessions.name
}

output "sessions_table_arn" {
  description = "Sessions DynamoDB table ARN"
  value       = aws_dynamodb_table.sessions.arn
}

output "messages_table_name" {
  description = "Messages DynamoDB table name"
  value       = aws_dynamodb_table.messages.name
}

output "messages_table_arn" {
  description = "Messages DynamoDB table ARN"
  value       = aws_dynamodb_table.messages.arn
}
