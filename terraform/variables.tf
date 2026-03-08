variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "billing-extractor"
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.small"
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for ALB"
  type        = list(string)
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS (optional)"
  type        = string
  default     = ""
}

# ECS Variables
variable "container_cpu" {
  description = "Container CPU units (1024 = 1 vCPU)"
  type        = number
  default     = 256
}

variable "container_memory" {
  description = "Container memory (MB) - set low to trigger OOM for demo"
  type        = number
  default     = 512
}

variable "minimax_api_key" {
  description = "MiniMax API key for image extraction"
  type        = string
  default     = ""
  sensitive   = true
}

variable "use_ecs" {
  description = "Use ECS instead of EC2"
  type        = bool
  default     = true
}
