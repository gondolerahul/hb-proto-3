# HireBuddha Platform - Quick Start Guide

## 🚀 Starting All Services

To start all backend and frontend services with a single command:

```bash
./start_services.sh
```

This script will automatically start:
1. **PostgreSQL** (Port 5433) - Database
2. **Redis** (Port 6379) - Cache and task queue
3. **Backend API** (Port 8001) - Main FastAPI application
4. **API Gateway** (Port 8000) - Rate limiting and routing
5. **Arq Worker** - Background task processing
6. **Frontend** (Port 3000) - React application

## 🛑 Stopping All Services

To stop all services:

```bash
./stop_services.sh
```

## 🌐 Access URLs

Once all services are running, you can access:

- **Frontend Application**: http://localhost:3000
- **API Gateway**: http://localhost:8000
- **Backend API**: http://localhost:8001
- **API Documentation (Swagger)**: http://localhost:8001/docs
- **API Documentation (ReDoc)**: http://localhost:8001/redoc

## 📋 Viewing Logs

All service logs are stored in the `logs/` directory:

```bash
# View Backend API logs
tail -f logs/backend_api.log

# View API Gateway logs
tail -f logs/api_gateway.log

# View Arq Worker logs
tail -f logs/arq_worker.log

# View Frontend logs
tail -f logs/frontend.log
```

## 🔍 Checking Service Status

To check if services are running:

```bash
# Check all ports
lsof -i :8001 -i :8000 -i :3000 -i :5433 -i :6379 | grep LISTEN

# Check Docker containers
docker ps

# Check Python processes
ps aux | grep -E "(uvicorn|arq)" | grep -v grep

# Check Frontend
ps aux | grep vite | grep -v grep
```

## ⚙️ Manual Service Management

If you need to start services manually:

### Backend Services

```bash
cd backend

# Start PostgreSQL and Redis
docker compose up -d db redis

# Start Backend API
.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload

# Start API Gateway (in a new terminal)
.venv/bin/python -m uvicorn src.gateway.main:app --host 0.0.0.0 --port 8000 --reload

# Start Arq Worker (in a new terminal)
.venv/bin/python -m arq.cli src.ai.worker.WorkerSettings
```

### Frontend

```bash
cd frontend
npm run dev
```

## 🐛 Troubleshooting

### Port Already in Use

If you get a "port already in use" error:

```bash
# Find process using the port
lsof -i :PORT_NUMBER

# Kill the process
kill -9 PID
```

### Services Not Starting

1. Check the logs in the `logs/` directory
2. Ensure PostgreSQL and Redis are running: `docker ps`
3. Verify virtual environment exists: `ls -la backend/.venv`
4. Check for error messages in the terminal output

### Database Connection Issues

```bash
# Test PostgreSQL connection
docker exec -it hirebuddha-db psql -U postgres -d hirebuddha

# Test Redis connection
docker exec -it hirebuddha-redis redis-cli ping
```

## 📝 Notes

- The startup script is idempotent - you can run it multiple times safely
- Services that are already running will be skipped
- All services run in the background with nohup
- PID files are stored in `logs/` directory for process management
