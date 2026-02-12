# Security Model - NetGuru Platform

**Versão:** 1.0  
**Data:** Fevereiro 2026

---

## 🔐 Visão Geral de Segurança

O NetGuru implementa segurança em múltiplas camadas seguindo o princípio de **Defense in Depth**:

1. **Network Layer**: HTTPS obrigatório, firewall rules
2. **Authentication Layer**: JWT tokens, bcrypt hashing
3. **Authorization Layer**: RBAC baseado em plan_tier
4. **Data Layer**: Encryption at rest para dados sensíveis
5. **Application Layer**: Input validation, SQL injection prevention
6. **File Upload Layer**: Validação rigorosa, sandboxing

---

## 🔑 Autenticação

### JWT (JSON Web Tokens)

**Estrutura do Token:**
```json
{
  "header": {
    "alg": "HS256",
    "typ": "JWT"
  },
  "payload": {
    "sub": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "plan_tier": "solo",
    "exp": 1709827200,
    "iat": 1709823600,
    "jti": "token-unique-id"
  },
  "signature": "..."
}
```

**Claims:**
- `sub`: User ID (subject)
- `email`: User email (para display, não auth)
- `plan_tier`: Para feature flags e rate limiting
- `exp`: Expiration timestamp
- `iat`: Issued at timestamp
- `jti`: JWT ID (para revogação se necessário)

---

### Implementação (FastAPI)

**security.py:**
```python
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = settings.SECRET_KEY  # 256-bit random key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
```

---

### Password Requirements

**Política de Senha:**
- Mínimo: 8 caracteres
- Recomendado: 12+ caracteres
- Deve conter: letras, números, símbolos (opcional mas encorajado)
- **Não** expiram (anti-pattern moderno)
- **Não** armazenamos histórico (previne reuso)

**Validação (Pydantic):**
```python
from pydantic import BaseModel, Field, validator

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    
    @validator('password')
    def password_strength(cls, v):
        if v.isdigit() or v.isalpha():
            raise ValueError('Senha deve conter letras E números')
        return v
```

---

### Token Refresh Strategy

**Fluxo:**
```
1. Login → {access_token (1h), refresh_token (7d)}
2. Access expira → Client usa refresh_token
3. POST /auth/refresh → {new_access_token}
4. Refresh token é invalidado (one-time use)
5. Se refresh expirar → Novo login obrigatório
```

**Armazenamento Redis (refresh tokens):**
```python
# Salvar ao login
await redis.setex(
    f"refresh_token:{token_id}",
    7 * 24 * 60 * 60,  # 7 dias
    user_id
)

# Validar ao refresh
user_id = await redis.get(f"refresh_token:{token_id}")
if not user_id:
    raise HTTPException(401, "Refresh token inválido ou expirado")

# Invalidar (one-time use)
await redis.delete(f"refresh_token:{token_id}")
```

---

### Dependency Injection (get_current_user)

**deps.py:**
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        
        if user_id is None:
            raise HTTPException(401, "Token inválido")
            
    except JWTError:
        raise HTTPException(401, "Token inválido ou expirado")
    
    user = await db.get(User, user_id)
    
    if user is None or not user.is_active:
        raise HTTPException(401, "Usuário não encontrado ou inativo")
    
    return user
```

**Uso em Endpoints:**
```python
@router.get("/users/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
```

---

## 🛡️ Autorização (RBAC)

### Roles e Permissoes

| Role | Permissoes Principais |
|------|------------------------|
| `owner` | Acesso total, incluindo gestao de roles/status |
| `admin` | Gestao de usuarios (sem promover para `owner`) |
| `member` | Operacoes do proprio perfil (`/users/me`) |
| `viewer` | Leitura do proprio perfil |

**Permissoes implementadas (backend):**
- `users:read_self`
- `users:update_self`
- `api_keys:read_self`
- `api_keys:update_self`
- `users:list`
- `users:read`
- `users:update_role`
- `users:update_status`

### Plan Tiers e Entitlements

| Feature | Solo | Team | Enterprise |
|---------|------|------|------------|
| Chat com IA | ✅ | ✅ | ✅ |
| Upload files | ✅ (10/dia) | ✅ (50/dia) | ✅ (200/dia) |
| PCAP Analysis | ❌ | ✅ | ✅ |
| Topology Visualization | ❌ | ✅ | ✅ |
| RAG Local (user docs) | ❌ | ✅ | ✅ |
| Team Collaboration | ❌ | ✅ | ✅ |
| API Access | ❌ | ❌ | ✅ |
| Self-Hosted | ❌ | ❌ | ✅ |

> `plan_tier` controla acesso a features pagas (entitlements).  
> `role` controla autorizacao de operacoes (RBAC).

---

### Feature Flags

**Decorator para proteção:**
```python
from functools import wraps
from fastapi import HTTPException

def require_plan(min_plan: str):
    """Decorator para endpoints que exigem plano específico"""
    
    plan_hierarchy = {"solo": 0, "team": 1, "enterprise": 2}
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user: User = None, **kwargs):
            user_plan_level = plan_hierarchy.get(current_user.plan_tier, 0)
            required_level = plan_hierarchy.get(min_plan, 0)
            
            if user_plan_level < required_level:
                raise HTTPException(
                    403,
                    f"Feature requer plano {min_plan} ou superior"
                )
            
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator

# Uso
@router.post("/analysis/pcap")
@require_plan("team")
async def analyze_pcap(
    file_id: str,
    current_user: User = Depends(get_current_user)
):
    ...
```

---

## 🔒 Proteção de Dados

### API Keys de Clientes (Encryption at Rest)

**NUNCA** armazenar API keys em plaintext. Usar Fernet symmetric encryption:

```python
from cryptography.fernet import Fernet

class APIKeyService:
    def __init__(self):
        # Key derivada de SECRET_KEY (ou AWS KMS)
        self.cipher = Fernet(settings.ENCRYPTION_KEY.encode())
    
    def encrypt_key(self, plaintext_key: str) -> str:
        """Encrypta API key antes de salvar no DB"""
        encrypted = self.cipher.encrypt(plaintext_key.encode())
        return encrypted.decode()
    
    def decrypt_key(self, encrypted_key: str) -> str:
        """Decrypta API key para uso"""
        decrypted = self.cipher.decrypt(encrypted_key.encode())
        return decrypted.decode()
    
    async def validate_key_with_provider(self, provider: str, key: str) -> bool:
        """Testa key antes de salvar"""
        try:
            if provider == "openai":
                import openai
                openai.api_key = key
                await openai.Model.list()  # Test call
                return True
            elif provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=key)
                await client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=10,
                    messages=[{"role": "user", "content": "test"}]
                )
                return True
        except Exception as e:
            logger.error(f"Key validation failed: {e}")
            return False
```

---

### Secrets Management (Produção)

**MVP (Local):**
- Fernet encryption com key em `.env`
- **Limitação**: Se `.env` vazar, todas keys comprometidas

**Produção (Recomendado):**
- **AWS Secrets Manager** ou **HashiCorp Vault**
- Rotação automática de encryption keys
- Auditoria de acesso a secrets

**Exemplo com Vault:**
```python
import hvac

vault_client = hvac.Client(url='http://vault:8200', token=settings.VAULT_TOKEN)

# Salvar
vault_client.secrets.kv.v2.create_or_update_secret(
    path=f"api_keys/{user_id}",
    secret={"openai_key": plaintext_key}
)

# Recuperar
secret = vault_client.secrets.kv.v2.read_secret_version(
    path=f"api_keys/{user_id}"
)
openai_key = secret['data']['data']['openai_key']
```

---

### Database Encryption

**PostgreSQL (pgcrypto extension):**
```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Exemplo (não usado - preferimos app-level encryption)
INSERT INTO api_keys (encrypted_key) 
VALUES (pgp_sym_encrypt('secret-key', 'passphrase'));

SELECT pgp_sym_decrypt(encrypted_key, 'passphrase')::text FROM api_keys;
```

**Nossa abordagem:** Encryption a nível de aplicação (mais flexível).

---

## 📁 File Upload Security

### Validação Multi-Layer

**1. Extension Whitelist:**
```python
ALLOWED_EXTENSIONS = {
    'config': ['.txt', '.conf', '.cfg'],
    'log': ['.log', '.txt'],
    'pcap': ['.pcap', '.pcapng', '.cap'],
    'document': ['.pdf']
}

def validate_extension(filename: str, file_type: str) -> bool:
    ext = os.path.splitext(filename)[1].lower()
    return ext in ALLOWED_EXTENSIONS.get(file_type, [])
```

**2. Magic Bytes Verification:**
```python
import magic

def validate_file_type(file_path: str, expected_type: str) -> bool:
    """Valida tipo real do arquivo (não apenas extensão)"""
    mime = magic.from_file(file_path, mime=True)
    
    type_mapping = {
        'pcap': ['application/vnd.tcpdump.pcap', 'application/x-pcapng'],
        'config': ['text/plain'],
        'pdf': ['application/pdf']
    }
    
    return mime in type_mapping.get(expected_type, [])
```

**3. Size Limits:**
```python
MAX_UPLOAD_SIZE = {
    'solo': 50 * 1024 * 1024,      # 50MB
    'team': 100 * 1024 * 1024,     # 100MB
    'enterprise': 500 * 1024 * 1024 # 500MB
}

async def validate_size(file: UploadFile, user: User):
    file.file.seek(0, 2)  # Seek to end
    size = file.file.tell()
    file.file.seek(0)     # Reset
    
    max_size = MAX_UPLOAD_SIZE[user.plan_tier]
    if size > max_size:
        raise HTTPException(413, f"Arquivo excede {max_size / 1024 / 1024}MB")
```

---

### Filename Sanitization

```python
import uuid
import re

def sanitize_filename(original_filename: str) -> tuple[str, str]:
    """
    Retorna (safe_filename, generated_filename)
    """
    # Remove caracteres perigosos
    safe_name = re.sub(r'[^\w\s.-]', '', original_filename)
    safe_name = safe_name.strip().replace(' ', '_')
    
    # Gera nome único (UUID)
    ext = os.path.splitext(safe_name)[1]
    generated = f"{uuid.uuid4()}{ext}"
    
    return safe_name, generated
```

**Nunca** usar filename original como path no filesystem:
```python
# ❌ ERRADO (path traversal vulnerability)
file_path = f"/uploads/{original_filename}"

# ✅ CORRETO
original, generated = sanitize_filename(uploaded_file.filename)
file_path = f"/uploads/{user_id}/{generated}"
```

---

### Antivirus Scanning (ClamAV)

**Opcional para MVP, obrigatório para produção.**

```python
import clamd

async def scan_file(file_path: str) -> bool:
    """Retorna True se arquivo é limpo"""
    try:
        cd = clamd.ClamdUnixSocket()
        scan_result = cd.scan(file_path)
        
        # scan_result = {'/path/file.txt': ('OK', None)} se limpo
        # scan_result = {'/path/file.txt': ('FOUND', 'Trojan.Generic')} se infectado
        
        status = scan_result[file_path][0]
        return status == 'OK'
    except Exception as e:
        logger.error(f"ClamAV scan failed: {e}")
        # Fail-safe: bloquear upload se scan falhar
        return False

# Uso no upload
file_path = await save_uploaded_file(file)
if not await scan_file(file_path):
    os.remove(file_path)
    raise HTTPException(400, "Arquivo rejeitado por segurança")
```

---

### PCAP-Specific Security

**Risco:** PCAP pode conter dados sensíveis (passwords em plaintext, IPs internos).

**Mitigações:**
1. **Sandboxing**: Processar PCAP em container isolado
2. **Timeout**: Limitar tempo de processamento (evitar DoS via PCAP gigante)
3. **Packet Limit**: Processar apenas N primeiros pacotes

```python
from scapy.all import rdpcap, PcapReader

MAX_PACKETS = 100_000
PROCESSING_TIMEOUT = 300  # 5 minutos

@celery_app.task(time_limit=PROCESSING_TIMEOUT)
def analyze_pcap_safe(file_path: str):
    """Análise segura com limits"""
    try:
        packet_count = 0
        with PcapReader(file_path) as pcap:
            for packet in pcap:
                packet_count += 1
                if packet_count > MAX_PACKETS:
                    logger.warning(f"PCAP truncado em {MAX_PACKETS} packets")
                    break
                
                # Análise...
                
    except Exception as e:
        logger.error(f"PCAP analysis failed: {e}")
        raise
```

---

## 🚨 Rate Limiting

### Implementação (Redis + slowapi)

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}"
)

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Por IP
@router.post("/auth/login")
@limiter.limit("5/minute")
async def login(request: Request, credentials: LoginRequest):
    ...

# Por usuário autenticado (custom key_func)
def get_user_id(request: Request) -> str:
    try:
        token = request.headers.get("Authorization").split()[1]
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except:
        return get_remote_address(request)

@router.post("/chat/messages")
@limiter.limit("100/minute", key_func=get_user_id)
async def send_message(...):
    ...
```

---

### Rate Limits por Plano

```python
RATE_LIMITS = {
    "solo": {
        "chat": "100/minute",
        "upload": "10/hour",
        "analysis": "5/hour"
    },
    "team": {
        "chat": "500/minute",
        "upload": "50/hour",
        "analysis": "20/hour"
    },
    "enterprise": {
        "chat": "2000/minute",
        "upload": "200/hour",
        "analysis": "100/hour"
    }
}

def get_rate_limit(user: User, endpoint: str) -> str:
    return RATE_LIMITS[user.plan_tier][endpoint]
```

---

## 🛑 Input Validation

### SQL Injection Prevention

**SEMPRE** usar parametrized queries (SQLAlchemy protege automaticamente):

```python
# ✅ CORRETO (SQLAlchemy ORM)
user = await db.execute(
    select(User).where(User.email == email)
)

# ✅ CORRETO (Raw SQL com params)
result = await db.execute(
    text("SELECT * FROM users WHERE email = :email"),
    {"email": email}
)

# ❌ ERRADO (SQL injection vulnerability)
query = f"SELECT * FROM users WHERE email = '{email}'"
result = await db.execute(query)
```

---

### XSS Prevention

**Backend:**
- Sempre retornar `Content-Type: application/json`
- Nunca renderizar HTML no backend (SPA frontend faz isso)

**Frontend:**
- React escapa automaticamente
- Usar `dangerouslySetInnerHTML` APENAS para Markdown sanitizado

```typescript
import DOMPurify from 'dompurify';
import { marked } from 'marked';

function MessageBubble({ content }: { content: string }) {
  const html = marked(content);
  const sanitized = DOMPurify.sanitize(html);
  
  return <div dangerouslySetInnerHTML={{ __html: sanitized }} />;
}
```

---

### Prompt Injection (LLM)

**Risco:** User pode tentar injetar instruções maliciosas no prompt.

**Mitigações:**
1. **System Prompt Fixo**: Não permitir user modificar system message
2. **Input Sanitization**: Remover caracteres de controle
3. **Output Validation**: Verificar se resposta contém comandos suspeitos

```python
FORBIDDEN_PATTERNS = [
    r"ignore previous instructions",
    r"disregard.*system",
    r"you are now",
    r"sudo",
    r"rm -rf"
]

def sanitize_user_input(text: str) -> str:
    # Remove controle characters
    cleaned = ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')
    
    # Detectar patterns suspeitos
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, cleaned, re.IGNORECASE):
            logger.warning(f"Prompt injection attempt detected: {pattern}")
            raise HTTPException(400, "Input contém padrões não permitidos")
    
    return cleaned
```

---

## 🔐 HTTPS e TLS

### Certificados (Let's Encrypt)

**Produção (Nginx + Certbot):**
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Obter certificado
sudo certbot --nginx -d netguru.example.com

# Auto-renewal (cron)
0 3 * * * certbot renew --quiet
```

**Nginx Configuration:**
```nginx
server {
    listen 443 ssl http2;
    server_name netguru.example.com;
    
    ssl_certificate /etc/letsencrypt/live/netguru.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/netguru.example.com/privkey.pem;
    
    # Modern SSL config
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name netguru.example.com;
    return 301 https://$server_name$request_uri;
}
```

---

## 🔍 Logging e Auditoria

### Security Events para Logar

```python
import structlog

logger = structlog.get_logger()

# Login attempts
logger.info("login_attempt", user_email=email, success=True, ip=request.client.host)
logger.warning("login_failed", user_email=email, reason="invalid_password", ip=ip)

# API key operations
logger.info("api_key_created", user_id=user.id, provider="openai")
logger.warning("api_key_validation_failed", user_id=user.id, provider="openai")

# File operations
logger.info("file_uploaded", user_id=user.id, file_type="pcap", size_mb=file_size/1024/1024)
logger.warning("file_rejected", user_id=user.id, reason="virus_detected")

# Rate limiting
logger.warning("rate_limit_exceeded", user_id=user.id, endpoint="/chat/messages")

# Authorization failures
logger.warning("unauthorized_access", user_id=user.id, endpoint="/analysis/pcap", plan="solo")
```

---

### Sensitive Data Masking

```python
def mask_api_key(key: str) -> str:
    """Mostra apenas primeiros/últimos chars"""
    if len(key) < 10:
        return "***"
    return f"{key[:4]}...{key[-4:]}"

# Logging
logger.info("api_key_validated", masked_key=mask_api_key(api_key))
```

---

## 🧪 Security Testing

### Checklist (Pré-Prod)

- [ ] HTTPS obrigatório em produção
- [ ] Todos endpoints protegidos por autenticação (exceto login/register)
- [ ] Rate limiting configurado
- [ ] API keys encryptadas no DB
- [ ] File upload validação (extension + magic bytes + size)
- [ ] ClamAV integrado
- [ ] SQL injection tests passando (sqlmap)
- [ ] XSS tests passando
- [ ] CORS configurado corretamente (whitelist de origins)
- [ ] Secrets não commitados no Git (.env no .gitignore)
- [ ] Password policy enforced
- [ ] Tokens expirando corretamente
- [ ] Logs não expondo dados sensíveis

---

### Ferramentas de Teste

**OWASP ZAP:**
```bash
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t https://netguru.example.com
```

**sqlmap (SQL Injection):**
```bash
sqlmap -u "http://localhost:8000/api/v1/users?email=test" \
  --cookie="Authorization=Bearer ..." --batch
```

---

## 🗺️ Próximos Passos

1. Revise [05-rag-implementation.md](05-rag-implementation.md) para segurança em RAG
2. Implemente com [06-phase1-foundation.md](06-phase1-foundation.md)
3. Configure monitoring em [09-deployment.md](09-deployment.md)

---

**Princípio:** **Security by Design, não by Addition.**  
Toda feature nova deve incluir threat modeling desde o início.
