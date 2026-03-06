#!/bin/bash
# Deploy script for EC2

set -e

APP_DIR="/home/ec2-user/sre.test.billing"
IMAGE_NAME="billing-extractor"

echo "📦 Pulling latest code..."
cd $APP_DIR
git pull origin main

echo "🐳 Building Docker image..."
docker build -t $IMAGE_NAME .

echo "🔄 Restarting container..."
docker stop billing-app 2>/dev/null || true
docker rm billing-app 2>/dev/null || true
docker run -d \
    --restart=always \
    -p 80:80 \
    --name billing-app \
    $IMAGE_NAME

echo "✅ Deployment complete!"
echo "🔍 Checking health..."
sleep 5
curl -s http://localhost/health | python3 -m json.tool
