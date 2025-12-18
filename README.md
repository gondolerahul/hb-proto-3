# HireBuddha Platform v2.0

## 📋 Project Overview

HireBuddha Platform v2.0 is a multi-tenant SaaS platform for building and executing AI agents with a "No-Code" builder interface. The platform features a sophisticated billing system, role-based access control, and a beautiful "Liquid Glass" UI design.

### Key Features

- 🔐 **Multi-tenant Architecture** - Partner → Tenant → User hierarchy
- 🤖 **AI Agent Builder** - No-code interface for creating AI agents and workflows
- 💰 **Financial Engine** - Usage-based billing with ledger tracking
- 🎨 **Liquid Glass UI** - Modern glassmorphism design with rose gold accents
- ⚡ **Async Execution** - Background task processing with Arq and Redis
- 🔒 **RBAC** - Role-based access control (App Admin, Partner Admin, Tenant Admin, User)

### Architecture

```
┌─────────────────┐
│   API Gateway   │ (Port 8000) - Rate limiting & request routing
└────────┬────────┘
         │
┌────────▼────────┐
│  Backend API    │ (Port 8001) - FastAPI application
│  ┌───────────┐  │
│  │   Auth    │  │ - Authentication & IAM
│  │  Tenant   │  │ - Partner & Tenant management
│  │    AI     │  │ - Agent builder & execution
│  │  Billing  │  │ - Rates, ledger, invoicing
│  │  Config   │  │ - System configuration
│  └───────────┘  │
└────────┬────────┘
         │
    ┌────┴────┬──────────┐
    │         │          │
┌───▼───┐ ┌──▼──┐  ┌────▼────┐
│ Redis │ │ DB  │  │ Frontend│ (Port 5173)
│       │ │     │  │  React  │
└───────┘ └─────┘  └─────────┘
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+** with Poetry
- **Node.js 18+** with npm
- **PostgreSQL 15+**
- **Redis 7+**
- **Docker & Docker Compose** (optional, for containerized setup)

### Installation

#### Option 1: Local Development Setup

1. **Clone the repository**
   ```bash
   cd /home/rahul/workspace/dev-hb-codebase/hb-proto-3
   ```

2. **Set up environment variables**
   ```bash
   # .env file already exists in backend/ with:
   # DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/hirebuddha
   # REDIS_URL=redis://localhost:6379
   # SECRET_KEY=dev_secret_key_change_in_production
   # ALGORITHM=HS256
   # ACCESS_TOKEN_EXPIRE_MINUTES=30
   ```

3. **Install backend dependencies**
   ```bash
   cd backend
   poetry install
   cd ..
   ```

4. **Install frontend dependencies**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

#### Option 2: Docker Compose Setup

```bash
cd backend
docker-compose up -d
```

This will start:
- PostgreSQL on port 5433
- Redis on port 6379
- Backend API on port 8001
- API Gateway on port 8000

## 🎯 Starting the Application

### Backend Services

You need to start **3 separate backend processes**:

#### 1. Start PostgreSQL and Redis

If using Docker:
```bash
cd backend
docker-compose up -d db redis
```

If using local installations:
```bash
# PostgreSQL should be running on port 5433
# Redis should be running on port 6379
```

#### 2. Start the Main Backend API

```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
poetry shell

# Run the main FastAPI application
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

**Backend API will be available at:** `http://localhost:8001`

#### 3. Start the API Gateway

Open a new terminal:

```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
poetry shell

# Run the API Gateway
uvicorn src.gateway.main:app --host 0.0.0.0 --port 8000 --reload
```

**API Gateway will be available at:** `http://localhost:8000`

#### 4. Start the Arq Worker (Background Tasks)

Open another new terminal:

```bash
# Navigate to backend directory
cd backend

# Activate virtual environment
poetry shell

# Run the Arq worker for async task processing
arq src.ai.worker.WorkerSettings
```

**Worker Status:** Check terminal for "Worker started" message

### Frontend

Open a new terminal:

```bash
cd frontend
npm run dev
```

**Frontend will be available at:** `http://localhost:5173`

## 🛑 Stopping the Application

### Stop Backend Services

1. **Stop the Main Backend API**: Press `Ctrl+C` in the terminal running `uvicorn src.main:app`
2. **Stop the API Gateway**: Press `Ctrl+C` in the terminal running `uvicorn src.gateway.main:app`
3. **Stop the Arq Worker**: Press `Ctrl+C` in the terminal running `arq`

### Stop Frontend

Press `Ctrl+C` in the terminal running `npm run dev`

### Stop Docker Services

```bash
cd backend
docker-compose down
```

To stop and remove volumes (⚠️ this will delete all data):
```bash
cd backend
docker-compose down -v
```

## 👥 Test User Credentials

### Default Test Users

The platform uses a hierarchical multi-tenant structure. Here are the test credentials:

#### 1. App Admin (Platform Administrator)
- **Email:** `admin@hb.com`
- **Password:** `adminpass`
- **Role:** `app_admin`
- **Permissions:** Full platform access, can create partners

#### 2. Partner Admin (Reseller)
- **Email:** `partner@tech.com`
- **Password:** `partnerpass`
- **Role:** `partner_admin`
- **Permissions:** Can create and manage tenants, view partner earnings

#### 3. Tenant Admin (Client Organization)
- **Email:** `client@corp.com`
- **Password:** `clientpass`
- **Role:** `tenant_admin`
- **Permissions:** Can manage users within tenant, create agents and workflows

### Creating Test Users

You can create these users by running the test script:

```bash
cd backend
poetry shell
python tests/verify_tenant.py
```

This script will:
1. Reset the database
2. Create the App Admin user
3. Create a Partner
4. Create a Tenant under the Partner

### Manual Registration

You can also register new users via the frontend at `http://localhost:5173/register`

## 📁 Project Structure

```
hb-proto-3/
├── backend/
│   ├── src/
│   │   ├── auth/          # Authentication & IAM service
│   │   ├── tenant/        # Partner & Tenant management
│   │   ├── ai/            # AI Agent builder & execution engine
│   │   ├── billing/       # Rates, ledger, invoicing
│   │   ├── config/        # System configuration
│   │   ├── gateway/       # API Gateway with rate limiting
│   │   ├── common/        # Shared utilities, database, middleware
│   │   └── main.py        # Main FastAPI application
│   ├── tests/             # Test scripts
│   ├── migrations/        # Database migrations
│   ├── docker-compose.yml # Docker setup
│   ├── pyproject.toml     # Python dependencies
│   └── .env               # Environment variables
├── frontend/
│   ├── src/
│   │   ├── components/  # Reusable UI components
│   │   ├── pages/       # Page components
│   │   ├── services/    # API service layer
│   │   └── styles/      # CSS design system
│   └── package.json
├── docs/              # Documentation
└── README.md          # This file
```

## 🔧 Technology Stack

### Backend
- **FastAPI** - Modern Python web framework
- **SQLAlchemy** - ORM with async support
- **PostgreSQL** - Primary database
- **Redis** - Caching and task queue
- **Arq** - Async task processing
- **Pydantic** - Data validation
- **JWT** - Authentication tokens

### Frontend
- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool
- **React Router** - Routing
- **Axios** - HTTP client
- **Framer Motion** - Animations
- **React Hook Form** - Form handling

## 🧪 Running Tests

```bash
# Navigate to backend directory
cd backend

# Run all tests
poetry shell
pytest

# Run specific test files
python tests/verify_tenant.py
python tests/verify_iam.py
python tests/test_phase3.py
python tests/test_phase4.py
```

## 📊 API Documentation

Once the backend is running, access the interactive API documentation:

- **Swagger UI:** `http://localhost:8001/docs`
- **ReDoc:** `http://localhost:8001/redoc`

## 🔑 Key API Endpoints

### Authentication
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login and get JWT token
- `GET /api/v1/auth/me` - Get current user info

### Partners (App Admin only)
- `POST /api/v1/partners` - Create partner
- `GET /api/v1/partners` - List partners

### Tenants
- `POST /api/v1/partners/{partner_id}/tenants` - Create tenant
- `GET /api/v1/tenants` - List tenants
- `PUT /api/v1/tenants/{tenant_id}` - Update tenant (suspend/activate)

### AI Agents
- `POST /api/v1/agents` - Create agent
- `GET /api/v1/agents` - List agents
- `POST /api/v1/agents/{agent_id}/execute` - Execute agent

### Workflows
- `POST /api/v1/workflows` - Create workflow
- `GET /api/v1/workflows` - List workflows
- `POST /api/v1/workflows/{workflow_id}/execute` - Execute workflow

### Billing
- `GET /api/v1/billing/rates` - Get system rates
- `GET /api/v1/billing/ledger` - Get ledger entries
- `GET /api/v1/billing/partner-earnings` - Get partner earnings

## 🐛 Troubleshooting

### Database Connection Issues
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check connection
psql -h localhost -p 5433 -U postgres -d hirebuddha
```

### Redis Connection Issues
```bash
# Check if Redis is running
docker ps | grep redis

# Test connection
redis-cli -h localhost -p 6379 ping
```

### Port Already in Use
```bash
# Find process using port 8000/8001/5173
lsof -i :8000
lsof -i :8001
lsof -i :5173

# Kill the process
kill -9 <PID>
```

### Frontend Build Issues
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

## 📝 Development Notes

### Current Implementation Status

According to the Gap Analysis Report, the platform is approximately **60-70% complete**:

- ✅ **Fully Implemented:** Core authentication, multi-tenant hierarchy, agent/workflow management, billing infrastructure, glassmorphism UI
- ⚠️ **Partially Implemented:** OAuth social login, RAG/Knowledge base, streaming responses, API key encryption
- ❌ **Not Implemented:** Refresh tokens, email verification, real LLM integration (currently using mocks)

### Known Limitations

1. **Mock LLM Execution** - AI agent execution currently returns mock responses (2-second delay)
2. **No Email Service** - Email verification not implemented
3. **No OAuth Backend** - Social login buttons exist in frontend but backend endpoints missing
4. **No Streaming** - Execution responses are not streamed in real-time
5. **No RAG** - Knowledge base/document upload feature not implemented

## 🤝 Contributing

This is a development prototype. For production deployment, please address the critical gaps identified in the Implementation Gap Analysis document.

## 📄 License

Proprietary - HireBuddha Platform v2.0

## 📞 Support

For issues or questions, please refer to the documentation in the `docs/` directory:
- [Functional Specification](docs/Hirebuddha%20Functional%20Specification%20Document.md)
- [Technical Architecture](docs/hire_buddha_technical_architecture_document.md)
- [Implementation Gap Analysis](docs/Implementation_Gap_Analysis.md)
- [Gap Analysis Report 2](docs/Gap%20Analysis%20Report%202.md)

---

**Version:** 0.1.0  
**Last Updated:** November 2025
