# PAMA API - Production Deployment Guide

## 🚀 Production Features

### Security

- ✅ SSL/TLS support with certificate verification
- ✅ Rate limiting (1000 requests/minute per IP)
- ✅ Security headers (HSTS, XSS protection, etc.)
- ✅ Trusted host middleware
- ✅ Password complexity requirements
- ✅ JWT token expiration and refresh
- ✅ CORS configuration for specific origins

### Performance

- ✅ Database connection pooling (20 connections)
- ✅ Gzip compression
- ✅ Multi-worker process support
- ✅ Connection pre-ping for reliability
- ✅ Optimized SQLAlchemy configuration

### Monitoring

- ✅ Health check endpoint (`/health`)
- ✅ Metrics endpoint (`/metrics`)
- ✅ Structured logging (JSON format)
- ✅ Database connection monitoring
- ✅ Request/response logging

### Scalability

- ✅ Docker containerization
- ✅ Docker Compose orchestration
- ✅ Nginx reverse proxy with SSL termination
- ✅ Horizontal scaling support
- ✅ Load balancing ready

## 📋 Pre-Deployment Checklist

### 1. Environment Configuration

- [ ] Create `.env` file with production settings
- [ ] Set `ENVIRONMENT=production`
- [ ] Configure database credentials
- [ ] Set strong `SECRET_KEY`
- [ ] Configure CORS origins for your frontend
- [ ] Set SSL mode if required

### 2. SSL Certificates

- [ ] Download `ca.pem` from Aiven dashboard
- [ ] Place in `ssl_certs/` directory
- [ ] Set `DB_SSL_MODE=REQUIRED` in `.env`
- [ ] Test SSL connection

### 3. Certificate push notification image

- [ ] Commit `app/static/push/notification_certificate.jpg` to Git (see `app/static/push/README.md`)
- [ ] Set `PUBLIC_API_BASE_URL=https://your-lightnode-domain` in production `.env`
- [ ] After deploy, open `{PUBLIC_API_BASE_URL}/uploads/push/notification_certificate.jpg` in a browser

`uploads/` is gitignored; Lightnode gets the image from **`app/static/push/`** in the repo. On startup and on parent notify, the API copies/uploads it to `uploads/push/`.

### 4. Security

- [ ] Change default `SECRET_KEY`
- [ ] Update `CORS_ORIGINS` to your domains
- [ ] Set strong database password
- [ ] Configure firewall rules
- [ ] Enable HTTPS in production

## 🐳 Docker Deployment

### Quick Start

```bash
# 1. Create .env file with production settings
cp .env.example .env
# Edit .env with your production values

# 2. Deploy with Docker Compose
./deploy.sh
```

### Manual Deployment

```bash
# Build image
docker build -t pama-api:latest .

# Run with Docker Compose
docker-compose up -d

# Check status
docker-compose ps
docker-compose logs -f pama-api
```

## 🔧 Configuration

### Environment Variables

#### Required

```env
ENVIRONMENT=production
DB_HOST=your-database-host
DB_PORT=14796
DB_USER=your-username
DB_PASSWORD=your-password
DB_NAME=your-database
SECRET_KEY=your-super-secret-key
```

#### Optional (with defaults)

```env
# Database Pool
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=30
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600

# SSL
DB_SSL_MODE=PREFERRED
DB_SSL_CA=./ssl_certs/ca.pem

# Security
PASSWORD_MIN_LENGTH=12
RATE_LIMIT_REQUESTS=1000
RATE_LIMIT_WINDOW=60

# CORS (configure for your domains)
CORS_ORIGINS=["https://yourdomain.com"]

# Server
HOST=0.0.0.0
PORT=8000
WORKERS=4
LOG_LEVEL=INFO
```

## 📊 Monitoring

### Health Checks

```bash
# Basic health check
curl http://localhost:8000/health

# Detailed metrics
curl http://localhost:8000/metrics
```

### Logs

```bash
# View application logs
docker-compose logs -f pama-api

# View nginx logs
docker-compose logs -f nginx
```

### Database Monitoring

```bash
# Check connection pool status
curl http://localhost:8000/metrics | grep connections
```

## 🔒 Security Best Practices

### 1. SSL/TLS

- Always use HTTPS in production
- Download and configure `ca.pem` for database SSL
- Use strong SSL ciphers in nginx configuration

### 2. Authentication

- Use strong, unique `SECRET_KEY`
- Implement proper password policies
- Use short-lived access tokens (15 minutes)
- Implement refresh token rotation

### 3. Network Security

- Configure firewall rules
- Use private networks for database
- Implement IP whitelisting if needed
- Monitor for suspicious activity

### 4. Data Protection

- Encrypt sensitive data at rest
- Use secure database connections
- Implement proper backup strategies
- Regular security audits

## 🚨 Troubleshooting

### Common Issues

#### 1. SSL Connection Failed

```bash
# Check SSL certificate
openssl x509 -in ssl_certs/ca.pem -text -noout

# Test SSL connection
python test_ssl_connection.py
```

#### 2. Database Connection Issues

```bash
# Check database connectivity
docker-compose exec pama-api python -c "
from app.database import engine
with engine.connect() as conn:
    print('Database connected successfully')
"
```

#### 3. Rate Limiting Issues

- Check `RATE_LIMIT_REQUESTS` and `RATE_LIMIT_WINDOW` settings
- Monitor `/metrics` endpoint for rate limit data
- Adjust limits based on your traffic patterns

#### 4. Performance Issues

- Monitor database connection pool usage
- Check worker process count
- Review nginx configuration
- Monitor memory and CPU usage

### Log Analysis

```bash
# Search for errors
docker-compose logs pama-api | grep ERROR

# Monitor real-time logs
docker-compose logs -f pama-api | grep -E "(ERROR|WARNING|INFO)"
```

## 📈 Scaling

### Horizontal Scaling

```yaml
# docker-compose.yml
services:
  pama-api:
    deploy:
      replicas: 3
    # ... other config
```

### Load Balancer Configuration

```nginx
upstream pama_api {
    server pama-api-1:8000;
    server pama-api-2:8000;
    server pama-api-3:8000;
}
```

### Database Scaling

- Use read replicas for read-heavy workloads
- Implement database connection pooling
- Monitor connection usage and adjust pool sizes

## 🔄 Updates & Maintenance

### Rolling Updates

```bash
# Build new image
docker build -t pama-api:v1.1.0 .

# Update docker-compose.yml
# Run rolling update
docker-compose up -d --no-deps pama-api
```

### Backup Strategy

```bash
# Database backup
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME > backup.sql

# Application backup
tar -czf pama-api-backup.tar.gz app/ alembic/ requirements.txt
```

## 📞 Support

For production support:

1. Check logs first: `docker-compose logs pama-api`
2. Verify configuration: `curl http://localhost:8000/health`
3. Monitor metrics: `curl http://localhost:8000/metrics`
4. Review this documentation for common issues

---

**Remember**: Always test in staging environment before deploying to production!
