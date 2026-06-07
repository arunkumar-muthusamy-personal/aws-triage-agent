module "ecr" {
  source       = "./modules/ecr"
  project_name = var.project_name
  environment  = var.environment
}

module "dynamodb" {
  source           = "./modules/dynamodb"
  project_name     = var.project_name
  environment      = var.environment
  session_ttl_days = var.session_ttl_days
}

module "iam" {
  source             = "./modules/iam"
  project_name       = var.project_name
  environment        = var.environment
  aws_region         = var.aws_region
  sessions_table_arn = module.dynamodb.sessions_table_arn
  messages_table_arn = module.dynamodb.messages_table_arn
}

module "networking" {
  source             = "./modules/networking"
  project_name       = var.project_name
  environment        = var.environment
  vpc_id             = var.vpc_id
  private_subnet_ids = var.private_subnet_ids
  public_subnet_ids  = var.public_subnet_ids
  use_vpc_endpoints  = var.use_vpc_endpoints
  aws_region         = var.aws_region
}

module "ecs" {
  source                = "./modules/ecs"
  project_name          = var.project_name
  environment           = var.environment
  aws_region            = var.aws_region
  vpc_id                = var.vpc_id
  private_subnet_ids    = var.private_subnet_ids
  ecr_repository_url    = module.ecr.repository_url
  task_role_arn         = module.iam.task_role_arn
  execution_role_arn    = module.iam.execution_role_arn
  sessions_table_name   = module.dynamodb.sessions_table_name
  messages_table_name   = module.dynamodb.messages_table_name
  alb_security_group_id = module.networking.alb_security_group_id
  ecs_security_group_id = module.networking.ecs_security_group_id
  ecs_cpu               = var.ecs_cpu
  ecs_memory            = var.ecs_memory
  max_tool_iterations   = var.max_tool_iterations
}

module "api_gateway" {
  source                = "./modules/api_gateway"
  project_name          = var.project_name
  environment           = var.environment
  vpc_id                = var.vpc_id
  alb_listener_arn      = module.ecs.alb_listener_arn
  private_subnet_ids    = var.private_subnet_ids
  ecs_security_group_id = module.networking.ecs_security_group_id
}

module "frontend" {
  source          = "./modules/frontend"
  project_name    = var.project_name
  environment     = var.environment
  api_gateway_url = module.api_gateway.api_url
}
