locals {
  name_prefix    = "${var.project_name}-${var.environment}"
  endpoint_count = var.use_vpc_endpoints ? 1 : 0
  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

data "aws_vpc" "this" {
  id = var.vpc_id
}

data "aws_route_tables" "private" {
  vpc_id = var.vpc_id

  filter {
    name   = "association.subnet-id"
    values = var.private_subnet_ids
  }
}

# ── Security Groups ────────────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name        = "${local.name_prefix}-alb-sg"
  description = "Security group for the internal ALB"
  vpc_id      = var.vpc_id

  ingress {
    description = "HTTP from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS from anywhere"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name_prefix}-alb-sg" })
}

resource "aws_security_group" "ecs" {
  name        = "${local.name_prefix}-ecs-sg"
  description = "Security group for ECS tasks"
  vpc_id      = var.vpc_id

  ingress {
    description     = "App port from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name_prefix}-ecs-sg" })
}

# ── VPC Endpoints ──────────────────────────────────────────────────────────────

resource "aws_security_group" "vpc_endpoints" {
  count       = local.endpoint_count
  name        = "${local.name_prefix}-vpce-sg"
  description = "Security group for VPC Interface Endpoints"
  vpc_id      = var.vpc_id

  ingress {
    description     = "HTTPS from ECS tasks"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name_prefix}-vpce-sg" })
}

# Bedrock Runtime — Interface endpoint
resource "aws_vpc_endpoint" "bedrock_runtime" {
  count               = local.endpoint_count
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true

  tags = merge(local.tags, { Name = "${local.name_prefix}-bedrock-runtime-vpce" })
}

# DynamoDB — Gateway endpoint
resource "aws_vpc_endpoint" "dynamodb" {
  count             = local.endpoint_count
  vpc_id            = var.vpc_id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.private.ids

  tags = merge(local.tags, { Name = "${local.name_prefix}-dynamodb-vpce" })
}

# CloudWatch Logs — Interface endpoint
resource "aws_vpc_endpoint" "logs" {
  count               = local.endpoint_count
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true

  tags = merge(local.tags, { Name = "${local.name_prefix}-logs-vpce" })
}

# ECR API — Interface endpoint
resource "aws_vpc_endpoint" "ecr_api" {
  count               = local.endpoint_count
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.api"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true

  tags = merge(local.tags, { Name = "${local.name_prefix}-ecr-api-vpce" })
}

# ECR DKR — Interface endpoint
resource "aws_vpc_endpoint" "ecr_dkr" {
  count               = local.endpoint_count
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.ecr.dkr"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true

  tags = merge(local.tags, { Name = "${local.name_prefix}-ecr-dkr-vpce" })
}

# SSM — Interface endpoint
resource "aws_vpc_endpoint" "ssm" {
  count               = local.endpoint_count
  vpc_id              = var.vpc_id
  service_name        = "com.amazonaws.${var.aws_region}.ssm"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.private_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true

  tags = merge(local.tags, { Name = "${local.name_prefix}-ssm-vpce" })
}
