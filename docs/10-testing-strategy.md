# Testing Strategy - NetGuru Platform

**Versão:** 1.0  
**Data:** Fevereiro 2026

---

## 🎯 Visão Geral de Testes

A estratégia de testes do NetGuru segue a pirâmide de testes:

```
         /\
        /E2E\          ← Poucos, críticos
       /──────\
      /Integration\    ← Moderados
     /────────────\
    /  Unit Tests  \   ← Muitos, rápidos
   /────────────────\
```

**Objetivo:** Coverage >80% com foco em business logic crítica.

---

## 🧪 Backend Testing

### Setup de Testes

**backend/requirements-dev.txt:**
```txt
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
httpx==0.25.2
faker==20.1.0
```

**backend/pytest.ini:**
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

addopts = 
    --cov=app
    --cov-report=html
    --cov-report=term-missing
    --strict-markers
    -v
```

---

### Fixtures (conftest.py)

**tests/conftest.py:**
```python
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient
from app.main import app
from app.db.base import Base
from app.core.config import settings

# Test database URL
TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost/netguru_test"

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    """Create test database engine"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()

@pytest.fixture
async def db_session(engine):
    """Create database session for each test"""
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()

@pytest.fixture
async def client(db_session):
    """Create test HTTP client"""
    # Override get_db dependency
    from app.api.deps import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()

@pytest.fixture
async def test_user(db_session):
    """Create test user"""
    from app.models.user import User
    from app.core.security import get_password_hash
    
    user = User(
        email="test@example.com",
        hashed_password=get_password_hash("testpass123"),
        full_name="Test User",
        plan_tier="solo"
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user

@pytest.fixture
async def auth_headers(test_user, client):
    """Get authenticated headers"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "testpass123"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
```

---

### Unit Tests: Security

**tests/unit/test_security.py:**
```python
import pytest
from app.core.security import (
    create_access_token,
    verify_password,
    get_password_hash,
    decode_token
)

def test_password_hashing():
    password = "mysecretpassword"
    hashed = get_password_hash(password)
    
    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False

def test_create_and_decode_token():
    user_id = "550e8400-e29b-41d4-a716-446655440000"
    token = create_access_token(user_id)
    
    decoded = decode_token(token)
    assert decoded == user_id

def test_invalid_token():
    decoded = decode_token("invalid.token.here")
    assert decoded is None
```

---

### Unit Tests: RAG Service

**tests/unit/test_rag.py:**
```python
import pytest
from app.services.rag.embeddings import EmbeddingService

@pytest.fixture
def embedding_service():
    return EmbeddingService()

def test_encode_text(embedding_service):
    text = "Configure OSPF on Cisco router"
    vector = embedding_service.encode(text)
    
    assert isinstance(vector, list)
    assert len(vector) == 384  # all-MiniLM-L6-v2 dimension
    assert all(isinstance(v, float) for v in vector)

def test_encode_batch(embedding_service):
    texts = [
        "OSPF area 0 configuration",
        "BGP neighbor setup",
        "VLAN configuration"
    ]
    vectors = embedding_service.encode_batch(texts)
    
    assert len(vectors) == 3
    assert all(len(v) == 384 for v in vectors)
```

---

### Integration Tests: Authentication

**tests/integration/test_auth.py:**
```python
import pytest

@pytest.mark.asyncio
async def test_register_user(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePass123",
            "full_name": "New User"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert "id" in data

@pytest.mark.asyncio
async def test_register_duplicate_email(client, test_user):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": test_user.email,
            "password": "AnotherPass123"
        }
    )
    
    assert response.status_code == 409

@pytest.mark.asyncio
async def test_login_success(client, test_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "testpass123"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data

@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "wrongpassword"
        }
    )
    
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_get_current_user(client, auth_headers):
    response = await client.get(
        "/api/v1/users/me",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
```

---

### Integration Tests: Chat

**tests/integration/test_chat.py:**
```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_create_conversation(client, auth_headers):
    response = await client.post(
        "/api/v1/chat/conversations",
        headers=auth_headers,
        json={"title": "Test Conversation"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Conversation"
    assert "id" in data

@pytest.mark.asyncio
async def test_list_conversations(client, auth_headers, db_session, test_user):
    # Create conversations
    from app.models.conversation import Conversation
    
    conv1 = Conversation(user_id=test_user.id, title="Conv 1")
    conv2 = Conversation(user_id=test_user.id, title="Conv 2")
    db_session.add_all([conv1, conv2])
    await db_session.commit()
    
    response = await client.get(
        "/api/v1/chat/conversations",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["conversations"]) == 2

@pytest.mark.asyncio
async def test_send_message_no_llm_key(client, auth_headers, db_session, test_user):
    # Create conversation
    from app.models.conversation import Conversation
    
    conv = Conversation(user_id=test_user.id, title="Test")
    db_session.add(conv)
    await db_session.commit()
    
    # Tentar enviar mensagem sem API key configurada
    response = await client.post(
        f"/api/v1/chat/conversations/{conv.id}/messages",
        headers=auth_headers,
        json={"content": "Hello"}
    )
    
    assert response.status_code == 400
    assert "api key" in response.json()["detail"].lower()
```

---

### Integration Tests: File Upload

**tests/integration/test_files.py:**
```python
import pytest
from io import BytesIO

@pytest.mark.asyncio
async def test_upload_config_file(client, auth_headers):
    file_content = b"""
    hostname Router1
    interface GigabitEthernet0/0
     ip address 10.0.0.1 255.255.255.0
    !
    """
    
    files = {"file": ("router_config.txt", BytesIO(file_content), "text/plain")}
    data = {"file_type": "config"}
    
    response = await client.post(
        "/api/v1/files/upload",
        headers=auth_headers,
        files=files,
        data=data
    )
    
    assert response.status_code == 201
    result = response.json()
    assert result["filename"] == "router_config.txt"
    assert result["file_type"] == "config"
    assert result["status"] == "uploaded"

@pytest.mark.asyncio
async def test_upload_invalid_extension(client, auth_headers):
    file_content = b"malicious content"
    files = {"file": ("malware.exe", BytesIO(file_content), "application/x-exe")}
    data = {"file_type": "config"}
    
    response = await client.post(
        "/api/v1/files/upload",
        headers=auth_headers,
        files=files,
        data=data
    )
    
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_list_files(client, auth_headers, db_session, test_user):
    from app.models.document import Document
    
    doc = Document(
        user_id=test_user.id,
        filename="test.txt",
        original_filename="test.txt",
        file_type="config",
        file_size_bytes=1024,
        storage_path="/uploads/test.txt",
        status="completed"
    )
    db_session.add(doc)
    await db_session.commit()
    
    response = await client.get(
        "/api/v1/files",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["files"]) == 1
    assert data["files"][0]["filename"] == "test.txt"
```

---

### Unit Tests: PCAP Analyzer

**tests/unit/test_pcap_analyzer.py:**
```python
import pytest
from app.services.pcap_analyzer import PCAPAnalyzer
from scapy.all import IP, TCP, wrpcap
import tempfile
import os

@pytest.fixture
def sample_pcap():
    """Create sample PCAP file"""
    packets = [
        IP(src="10.0.0.1", dst="10.0.0.2")/TCP(sport=1234, dport=80, seq=1000),
        IP(src="10.0.0.2", dst="10.0.0.1")/TCP(sport=80, dport=1234, seq=2000),
        IP(src="10.0.0.1", dst="10.0.0.2")/TCP(sport=1234, dport=80, seq=1001),
    ]
    
    with tempfile.NamedTemporaryFile(suffix=".pcap", delete=False) as f:
        wrpcap(f.name, packets)
        yield f.name
    
    os.unlink(f.name)

def test_analyze_pcap(sample_pcap):
    analyzer = PCAPAnalyzer()
    result = analyzer.analyze(sample_pcap)
    
    assert result["total_packets"] == 3
    assert "TCP" in result["protocols"]
    assert result["protocols"]["TCP"] == 3

def test_analyze_top_talkers(sample_pcap):
    analyzer = PCAPAnalyzer()
    result = analyzer.analyze(sample_pcap)
    
    talkers = result["top_talkers"]
    assert len(talkers) > 0
    assert talkers[0]["ip"] in ["10.0.0.1", "10.0.0.2"]

def test_analyze_nonexistent_file():
    analyzer = PCAPAnalyzer()
    
    with pytest.raises(FileNotFoundError):
        analyzer.analyze("/nonexistent/file.pcap")
```

---

## 🖥️ Frontend Testing

### Setup

**frontend/package.json (adicionar):**
```json
{
  "devDependencies": {
    "vitest": "^1.0.4",
    "@testing-library/react": "^14.1.2",
    "@testing-library/jest-dom": "^6.1.5",
    "@testing-library/user-event": "^14.5.1",
    "jsdom": "^23.0.1"
  },
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage"
  }
}
```

**frontend/vitest.config.ts:**
```typescript
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      exclude: ['node_modules/', 'src/test/']
    }
  }
});
```

---

### Component Tests

**src/components/__tests__/Button.test.tsx:**
```typescript
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import Button from '../Button';

describe('Button Component', () => {
  it('renders with text', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });
  
  it('calls onClick when clicked', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);
    
    fireEvent.click(screen.getByText('Click me'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });
  
  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>);
    const button = screen.getByText('Disabled');
    expect(button).toBeDisabled();
  });
});
```

---

### Store Tests

**src/stores/__tests__/authStore.test.ts:**
```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from '../authStore';
import api from '../../services/api';

vi.mock('../../services/api');

describe('Auth Store', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false
    });
  });
  
  it('logs in successfully', async () => {
    vi.mocked(api.post).mockResolvedValueOnce({
      data: {
        access_token: 'fake-token',
        refresh_token: 'fake-refresh'
      }
    });
    
    vi.mocked(api.get).mockResolvedValueOnce({
      data: {
        id: '123',
        email: 'test@example.com',
        plan_tier: 'solo'
      }
    });
    
    await useAuthStore.getState().login('test@example.com', 'password');
    
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user).not.toBeNull();
    expect(state.user?.email).toBe('test@example.com');
  });
  
  it('logs out', () => {
    useAuthStore.setState({
      user: { id: '123', email: 'test@example.com' },
      isAuthenticated: true
    });
    
    useAuthStore.getState().logout();
    
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
  });
});
```

---

## 🧬 E2E Testing (Playwright)

### Setup

```bash
npm install -D @playwright/test
npx playwright install
```

**playwright.config.ts:**
```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
  },
});
```

---

### E2E Tests

**e2e/auth.spec.ts:**
```typescript
import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test('should register new user', async ({ page }) => {
    await page.goto('/register');
    
    await page.fill('input[name="email"]', 'newuser@example.com');
    await page.fill('input[name="password"]', 'SecurePass123');
    await page.fill('input[name="fullName"]', 'New User');
    await page.click('button[type="submit"]');
    
    await expect(page).toHaveURL('/dashboard');
  });
  
  test('should login existing user', async ({ page }) => {
    await page.goto('/login');
    
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'testpass123');
    await page.click('button[type="submit"]');
    
    await expect(page).toHaveURL('/dashboard');
    await expect(page.locator('text=test@example.com')).toBeVisible();
  });
  
  test('should show error on invalid credentials', async ({ page }) => {
    await page.goto('/login');
    
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    
    await expect(page.locator('text=incorrect')).toBeVisible();
  });
});
```

**e2e/chat.spec.ts:**
```typescript
import { test, expect } from '@playwright/test';

test.describe('Chat Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="password"]', 'testpass123');
    await page.click('button[type="submit"]');
    await page.waitForURL('/dashboard');
  });
  
  test('should send message and receive response', async ({ page }) => {
    await page.goto('/chat');
    
    // Enviar mensagem
    await page.fill('input[placeholder*="pergunta"]', 'Como configurar OSPF?');
    await page.click('button:has-text("Enviar")');
    
    // Verificar mensagem do usuário
    await expect(page.locator('text=Como configurar OSPF?')).toBeVisible();
    
    // Aguardar resposta (simulated - depende de mock)
    await page.waitForTimeout(3000);
    
    // Verificar resposta da IA
    await expect(page.locator('.message-bubble').last()).toContainText('OSPF');
  });
  
  test('should create new conversation', async ({ page }) => {
    await page.goto('/chat');
    
    await page.click('button:has-text("Nova Conversa")');
    
    await expect(page.locator('text=Nova Conversa')).toBeVisible();
  });
});
```

---

## 📊 Coverage Reports

### Generate Coverage

**Backend:**
```bash
cd backend
pytest --cov=app --cov-report=html --cov-report=term
# Abrir htmlcov/index.html no navegador
```

**Frontend:**
```bash
cd frontend
npm run test:coverage
# Abrir coverage/index.html no navegador
```

---

## 🔄 CI/CD Testing

**.github/workflows/test.yml:**
```yaml
name: Tests

on: [push, pull_request]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: netguru_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
      
      redis:
        image: redis:7
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt -r requirements-dev.txt
      
      - name: Run tests
        run: |
          cd backend
          pytest --cov=app --cov-report=xml
        env:
          DATABASE_URL: postgresql+asyncpg://test:test@localhost/netguru_test
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./backend/coverage.xml
  
  frontend-tests:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Node
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Run tests
        run: |
          cd frontend
          npm run test:coverage
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./frontend/coverage/coverage-final.json
```

---

## ✅ Testing Checklist

### Unit Tests
- [ ] Security functions (hashing, JWT)
- [ ] RAG embedding generation
- [ ] Config parser
- [ ] PCAP analyzer
- [ ] Utility functions

### Integration Tests
- [ ] Authentication endpoints
- [ ] User CRUD
- [ ] Chat endpoints
- [ ] File upload/download
- [ ] Analysis endpoints

### E2E Tests
- [ ] User registration flow
- [ ] Login/logout flow
- [ ] Complete chat conversation
- [ ] File upload → Analysis → Result
- [ ] Topology generation

### Performance Tests (Opcional)
- [ ] Load testing (Locust)
- [ ] Stress testing
- [ ] Spike testing

---

## 🗺️ Próximos Passos

1. Executar todos os testes: `pytest && npm run test`
2. Revisar coverage reports
3. Adicionar testes para features novas
4. Configurar CI/CD para executar testes automaticamente

---

**Testing completo! ✅**
