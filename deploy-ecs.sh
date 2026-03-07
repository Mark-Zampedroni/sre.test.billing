#!/bin/bash
# Deploy billing extractor to ECS
set -euo pipefail

AWS_REGION="${AWS_REGION:-eu-central-1}"
APP_NAME="${APP_NAME:-billing-extractor}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}"

echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

echo "🏗️  Building Docker image..."
docker build -t "${APP_NAME}:latest" .

echo "🏷️  Tagging image..."
docker tag "${APP_NAME}:latest" "${ECR_REPO}:latest"

echo "📤 Pushing to ECR..."
docker push "${ECR_REPO}:latest"

echo "🚀 Updating ECS service..."
aws ecs update-service \
    --cluster "${APP_NAME}-cluster" \
    --service "${APP_NAME}" \
    --force-new-deployment \
    --region "$AWS_REGION"

echo "✅ Deployment initiated!"
echo ""
echo "Monitor deployment:"
echo "  aws ecs describe-services --cluster ${APP_NAME}-cluster --services ${APP_NAME} --region ${AWS_REGION}"
echo ""
echo "View logs:"
echo "  aws logs tail /billing/app --follow --region ${AWS_REGION}"
