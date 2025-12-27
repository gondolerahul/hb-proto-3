#!/bin/bash
# HireBuddha Platform v2.0 - Hierarchical AI Refactor
# This script starts all backend services and the frontend

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Log file directory
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  HireBuddha Hierarchical Platform v0.2${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to check if a port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to wait for a service to be ready
wait_for_service() {
    local name=$1
    local port=$2
    local max_attempts=30
    local attempt=0
    
    echo -e "${YELLOW}Waiting for $name to be ready on port $port...${NC}"
    
    while [ $attempt -lt $max_attempts ]; do
        if check_port $port; then
            echo -e "${GREEN}✓ $name is ready!${NC}"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    
    echo -e "${RED}✗ $name failed to start within expected time${NC}"
    return 1
}

# Step 1: Start Docker services (PostgreSQL and Redis)
echo -e "${BLUE}[1/6] Starting Docker services (PostgreSQL & Redis)...${NC}"
cd "$BACKEND_DIR"

if docker compose ps db --status running | grep -q "db" && docker compose ps redis --status running | grep -q "redis"; then
    echo -e "${YELLOW}Database and Redis are already running${NC}"
else
    docker compose up -d db redis
    echo -e "${GREEN}✓ Docker services started${NC}"
fi

# Wait for PostgreSQL and Redis
sleep 3
echo -e "${GREEN}✓ Database and Redis should be ready${NC}"

# Step 2: Start Main Backend API
echo -e "${BLUE}[2/6] Starting Main Backend API (Port 8001)...${NC}"

if check_port 8001; then
    echo -e "${YELLOW}Port 8001 already in use. Skipping Backend API startup.${NC}"
else
    cd "$BACKEND_DIR"
    nohup "$BACKEND_DIR/.venv/bin/python" -m uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload > "$LOG_DIR/backend_api.log" 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > "$LOG_DIR/backend_api.pid"
    echo -e "${GREEN}✓ Backend API started (PID: $BACKEND_PID)${NC}"
    wait_for_service "Backend API" 8001
fi

# Step 3: Start API Gateway
echo -e "${BLUE}[3/6] Starting API Gateway (Port 8000)...${NC}"

if check_port 8000; then
    echo -e "${YELLOW}Port 8000 already in use. Skipping API Gateway startup.${NC}"
else
    cd "$BACKEND_DIR"
    nohup "$BACKEND_DIR/.venv/bin/python" -m uvicorn src.gateway.main:app --host 0.0.0.0 --port 8000 --reload > "$LOG_DIR/api_gateway.log" 2>&1 &
    GATEWAY_PID=$!
    echo $GATEWAY_PID > "$LOG_DIR/api_gateway.pid"
    echo -e "${GREEN}✓ API Gateway started (PID: $GATEWAY_PID)${NC}"
    wait_for_service "API Gateway" 8000
fi

# Step 4: Start Arq Worker
echo -e "${BLUE}[4/6] Starting Arq Worker (Background Tasks)...${NC}"

# Check if arq worker is already running
if pgrep -f "arq src.ai.worker.WorkerSettings" > /dev/null; then
    echo -e "${YELLOW}Arq worker already running. Skipping.${NC}"
else
    cd "$BACKEND_DIR"
    nohup "$BACKEND_DIR/.venv/bin/python" -m arq.cli src.ai.worker.WorkerSettings > "$LOG_DIR/arq_worker.log" 2>&1 &
    ARQ_PID=$!
    echo $ARQ_PID > "$LOG_DIR/arq_worker.pid"
    echo -e "${GREEN}✓ Arq Worker started (PID: $ARQ_PID)${NC}"
    sleep 2
fi

# Step 5: Start Frontend
echo -e "${BLUE}[5/6] Starting Frontend (Port 3000)...${NC}"

if check_port 3000; then
    echo -e "${YELLOW}Port 3000 already in use. Skipping Frontend startup.${NC}"
else
    cd "$FRONTEND_DIR"
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$LOG_DIR/frontend.pid"
    echo -e "${GREEN}✓ Frontend started (PID: $FRONTEND_PID)${NC}"
    wait_for_service "Frontend" 3000
fi

# Step 6: Summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ All services started successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${BLUE}Service Status:${NC}"
echo -e "  • PostgreSQL:    ${GREEN}Running${NC} (Port 5433)"
echo -e "  • Redis:         ${GREEN}Running${NC} (Port 6379)"
echo -e "  • Backend API:   ${GREEN}Running${NC} (Port 8001)"
echo -e "  • API Gateway:   ${GREEN}Running${NC} (Port 8000)"
echo -e "  • Arq Worker:    ${GREEN}Running${NC}"
echo -e "  • Frontend:      ${GREEN}Running${NC} (Port 3000)"
echo ""
echo -e "${BLUE}Access URLs:${NC}"
echo -e "  • Frontend:      ${GREEN}http://localhost:3000${NC}"
echo -e "  • API Gateway:   ${GREEN}http://localhost:8000${NC}"
echo -e "  • Backend API:   ${GREEN}http://localhost:8001${NC}"
echo -e "  • API Docs:      ${GREEN}http://localhost:8001/docs${NC}"
echo ""
echo -e "${BLUE}Logs Location:${NC}"
echo -e "  • All logs:      ${YELLOW}$LOG_DIR/${NC}"
echo ""
echo -e "${YELLOW}To stop all services, run:${NC}"
echo -e "  ${GREEN}./stop_services.sh${NC}"
echo ""
echo -e "${YELLOW}To view logs:${NC}"
echo -e "  ${GREEN}tail -f $LOG_DIR/backend_api.log${NC}"
echo -e "  ${GREEN}tail -f $LOG_DIR/api_gateway.log${NC}"
echo -e "  ${GREEN}tail -f $LOG_DIR/arq_worker.log${NC}"
echo -e "  ${GREEN}tail -f $LOG_DIR/frontend.log${NC}"
echo ""
