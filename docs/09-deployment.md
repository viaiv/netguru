# Deployment Guide - NetGuru Platform

**Versão:** 1.0  
**Data:** Fevereiro 2026

---

## 🚀 Visão Geral de Deployment

Este documento cobre deployment do NetGuru em:
1. **Development** (Docker Compose local)
2. **Staging** (Docker Compose em VPS)
3. **Production** (AWS/GCP com Kubernetes - futuro)

---

## 🐳 Docker Configuration

### Dockerfile - Backend

**backend/Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run migrations and start server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```

---

### Dockerfile - Frontend

**frontend/Dockerfile:**
```dockerfile
FROM node:20-alpine as build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production image
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

**frontend/nginx.conf:**
```nginx
server {
    listen 80;
    server_name _;
    
    root /usr/share/nginx/html;
    index index.html;
    
    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # API proxy (para evitar CORS em produção)
    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    
    # WebSocket proxy
    location /ws {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

### Docker Compose - Production

**docker-compose.prod.yml:**
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_prod:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
  
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_prod:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
  
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres/${POSTGRES_DB}
      - REDIS_HOST=redis
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - uploads:/uploads
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
  
  celery_worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A app.workers.celery_app worker --loglevel=info -Q pcap,rag,topology
    environment:
      - DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres/${POSTGRES_DB}
      - REDIS_HOST=redis
      - SECRET_KEY=${SECRET_KEY}
    volumes:
      - uploads:/uploads
    depends_on:
      - redis
      - postgres
    restart: unless-stopped
  
  flower:
    build:
      context: ./backend
      dockerfile: Dockerfile
    command: celery -A app.workers.celery_app flower --port=5555
    environment:
      - REDIS_HOST=redis
    ports:
      - "5555:5555"
    depends_on:
      - redis
    restart: unless-stopped
  
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    depends_on:
      - backend
    restart: unless-stopped
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf
      - ./nginx/ssl:/etc/nginx/ssl
      - uploads:/uploads:ro
    depends_on:
      - frontend
      - backend
    restart: unless-stopped

volumes:
  postgres_prod:
  redis_prod:
  uploads:
```

---

## 🔐 Environment Variables

**.env.production:**
```env
# Database
POSTGRES_SERVER=postgres
POSTGRES_USER=netguru_prod
POSTGRES_PASSWORD=<generate-secure-password>
POSTGRES_DB=netguru_prod

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Security
SECRET_KEY=<generate-with-openssl-rand-hex-32>
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# App
PROJECT_NAME=NetGuru
VERSION=1.0.0
API_V1_PREFIX=/api/v1
BACKEND_CORS_ORIGINS=["https://netguru.example.com"]

# File Upload
MAX_UPLOAD_SIZE_MB=100
UPLOAD_DIR=/uploads

# Monitoring (opcional)
SENTRY_DSN=
```

**Gerar SECRET_KEY:**
```bash
openssl rand -hex 32
```

---

## 📦 Deployment em VPS (Staging)

### Pré-requisitos

- VPS com Ubuntu 22.04+ (mínimo 2GB RAM, 2 CPUs)
- Docker e Docker Compose instalados
- Domínio apontando para o VPS

---

### Setup Inicial

```bash
# 1. Conectar ao VPS
ssh root@your-vps-ip

# 2. Atualizar sistema
apt update && apt upgrade -y

# 3. Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 4. Instalar Docker Compose
apt install docker-compose-plugin -y

# 5. Criar usuário deploy
adduser deploy
usermod -aG docker deploy
su - deploy

# 6. Clonar repositório
git clone https://github.com/your-org/netguru.git
cd netguru

# 7. Configurar environment
cp .env.example .env.production
nano .env.production  # Editar com valores de produção

# 8. Build e start
docker compose -f docker-compose.prod.yml up -d --build

# 9. Verificar logs
docker compose -f docker-compose.prod.yml logs -f
```

---

### SSL/TLS com Let's Encrypt

```bash
# 1. Instalar Certbot
apt install certbot python3-certbot-nginx -y

# 2. Obter certificado
certbot certonly --standalone -d netguru.example.com

# 3. Copiar certificados para projeto
mkdir -p nginx/ssl
cp /etc/letsencrypt/live/netguru.example.com/fullchain.pem nginx/ssl/
cp /etc/letsencrypt/live/netguru.example.com/privkey.pem nginx/ssl/

# 4. Atualizar nginx.conf para usar HTTPS
# Ver seção abaixo

# 5. Restart nginx
docker compose -f docker-compose.prod.yml restart nginx

# 6. Configurar renovação automática
crontab -e
# Adicionar linha:
0 3 * * * certbot renew --quiet && docker compose -f /home/deploy/netguru/docker-compose.prod.yml restart nginx
```

---

**nginx/nginx.conf (com HTTPS):**
```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }
    
    upstream frontend {
        server frontend:80;
    }
    
    # HTTP → HTTPS redirect
    server {
        listen 80;
        server_name netguru.example.com;
        return 301 https://$server_name$request_uri;
    }
    
    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name netguru.example.com;
        
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        
        # Security headers
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        
        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # API
        location /api {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # WebSocket
        location /ws {
            proxy_pass http://backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
        
        # File uploads serve
        location /uploads {
            alias /uploads;
            autoindex off;
        }
    }
}
```

---

## 🔄 CI/CD com GitHub Actions

**.github/workflows/deploy.yml:**
```yaml
name: Deploy to VPS

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Deploy to VPS
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd /home/deploy/netguru
            git pull origin main
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d --build
            docker compose -f docker-compose.prod.yml exec -T backend alembic upgrade head
            docker system prune -f
```

**Secrets no GitHub:**
- `VPS_HOST`: IP do VPS
- `VPS_USER`: Usuário (deploy)
- `VPS_SSH_KEY`: Chave SSH privada

---

## 📊 Monitoring & Logging

### Prometheus + Grafana (Opcional)

**docker-compose.monitoring.yml:**
```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
    ports:
      - "9090:9090"
    restart: unless-stopped
  
  grafana:
    image: grafana/grafana:latest
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

**prometheus.yml:**
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'netguru-backend'
    static_configs:
      - targets: ['backend:8000']
  
  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
  
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']
```

---

### Structured Logging

**app/core/logging.py:**
```python
import structlog
import logging

def setup_logging():
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
    )

# Em app/main.py
from app.core.logging import setup_logging
setup_logging()
```

---

## 💾 Backup Strategy

### PostgreSQL Backups

**scripts/backup_db.sh:**
```bash
#!/bin/bash

BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER="netguru-postgres-1"

mkdir -p $BACKUP_DIR

# Backup
docker exec $CONTAINER pg_dump -U netguru_prod netguru_prod > $BACKUP_DIR/backup_$DATE.sql

# Compress
gzip $BACKUP_DIR/backup_$DATE.sql

# Cleanup old backups (keep last 7 days)
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete

echo "Backup completed: backup_$DATE.sql.gz"
```

**Cron job (daily at 3am):**
```bash
0 3 * * * /home/deploy/netguru/scripts/backup_db.sh >> /var/log/netguru_backup.log 2>&1
```

---

### Redis Backups

Redis já faz snapshots automáticos (RDB). Para backups adicionais:

```bash
# Trigger manual save
docker exec netguru-redis-1 redis-cli SAVE

# Copy dump.rdb
docker cp netguru-redis-1:/data/dump.rdb /backups/redis/dump_$(date +%Y%m%d).rdb
```

---

## 🔍 Health Checks

**app/api/v1/endpoints/health.py:**
```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
from app.db.session import get_db
from app.db.redis import get_redis

router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION
    }

@router.get("/health/detailed")
async def detailed_health(
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis)
):
    checks = {}
    
    # PostgreSQL
    try:
        await db.execute("SELECT 1")
        checks["postgres"] = "healthy"
    except Exception as e:
        checks["postgres"] = f"unhealthy: {str(e)}"
    
    # Redis
    try:
        await redis.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"
    
    overall_status = "healthy" if all(v == "healthy" for v in checks.values()) else "degraded"
    
    return {
        "status": overall_status,
        "checks": checks,
        "version": settings.VERSION
    }
```

---

## 🚨 Troubleshooting

### Logs Úteis

```bash
# Backend logs
docker compose logs -f backend

# Celery logs
docker compose logs -f celery_worker

# PostgreSQL logs
docker compose logs -f postgres

# Todos os serviços
docker compose logs -f

# Últimas 100 linhas
docker compose logs --tail=100
```

---

### Comandos Comuns

```bash
# Restart serviços
docker compose restart backend
docker compose restart celery_worker

# Rebuild após mudanças
docker compose up -d --build backend

# Executar migrations
docker compose exec backend alembic upgrade head

# Entrar no container
docker compose exec backend bash
docker compose exec postgres psql -U netguru_prod

# Ver recursos
docker stats

# Limpar espaço
docker system prune -a --volumes
```

---

## 📋 Checklist de Deployment

### Antes do Deploy

- [ ] Testes passando localmente
- [ ] Environment variables configuradas
- [ ] SECRET_KEY gerado e seguro
- [ ] Domínio configurado e apontando para VPS
- [ ] Backups configurados
- [ ] SSL certificado obtido

### Durante o Deploy

- [ ] `docker compose up -d --build`
- [ ] Migrations aplicadas
- [ ] Health checks passando
- [ ] Logs sem erros críticos

### Após o Deploy

- [ ] Testar login/register
- [ ] Testar chat funcionando
- [ ] Testar upload de arquivos
- [ ] Verificar HTTPS funcionando
- [ ] Monitoring configurado
- [ ] Backups testados (restore)

---

## 🗺️ Próximos Passos

1. Consulte [10-testing-strategy.md](10-testing-strategy.md) para testes E2E
2. Configure monitoring (Grafana dashboards)
3. Documente runbooks para incidentes
4. Planeje estratégia de scaling (Kubernetes futuro)

---

**Deployment completo! 🎉**
