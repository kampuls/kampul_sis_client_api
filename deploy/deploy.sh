#!/bin/bash

# Production Deployment Script for Kampul SIS Client API

set -e

echo "🚀 Starting Kampul SIS Client API Production Deployment"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Certificate push image must be in Git (app/static/push), not only uploads/
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PUSH_IMAGE="$API_ROOT/app/static/push/notification_certificate.jpg"

# Check if .env file exists
if [ ! -f "config/.env" ] && [ ! -f ".env.production" ]; then
    print_warning "Production .env file not found, will use environment variables"
fi

# Create SSL certificates directory if it doesn't exist
mkdir -p certs

# Build Docker image
print_status "Building Docker image..."
docker build -t kampul-sis-client-api:latest .

# Stop existing containers
print_status "Stopping existing containers..."
docker-compose down || true

# Start services
print_status "Starting services..."
docker-compose up -d

# Wait for services to be ready
print_status "Waiting for services to be ready..."
sleep 15

# Health check
print_status "Performing health check..."
if curl -f http://localhost:8000/health > /dev/null 2>&1; then
    print_status "✅ API is healthy and running!"
else
    print_error "❌ API health check failed!"
    print_status "Checking logs..."
    docker-compose logs api
    exit 1
fi

# Show running services
print_status "Running services:"
docker-compose ps

# Show useful information
echo ""
print_status "🎉 Deployment completed successfully!"
echo ""
print_status "API Endpoints:"
echo "  - Health Check: http://localhost:8000/health"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - Metrics: http://localhost:8000/metrics"
echo ""
print_status "Docker Commands:"
echo "  - View logs: docker-compose logs -f api"
echo "  - Stop services: docker-compose down"
echo "  - Restart: docker-compose restart api"
echo ""
print_warning "Remember to:"
echo "  1. Update CORS_ORIGINS in .env for your frontend domains"
echo "  2. Change SECRET_KEY to a secure random value"
echo "  3. Configure SSL certificates if using HTTPS"
echo "  4. Set up monitoring and logging"
