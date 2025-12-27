#!/bin/bash
# HireBuddha Platform v2.0 - Hierarchical AI Refactor
# This script stops all backend services and the frontend

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
LOG_DIR="$SCRIPT_DIR/logs"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  HireBuddha Hierarchical Shutdown v0.2${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to stop a service by PID file
stop_service() {
    local name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            echo -e "${YELLOW}Stopping $name (PID: $pid)...${NC}"
            kill $pid 2>/dev/null || kill -9 $pid 2>/dev/null
            rm "$pid_file"
            echo -e "${GREEN}✓ $name stopped${NC}"
        else
            echo -e "${YELLOW}$name not running (stale PID file)${NC}"
            rm "$pid_file"
        fi
    else
        echo -e "${YELLOW}$name PID file not found${NC}"
    fi
}

# Stop Frontend
echo -e "${BLUE}[1/5] Stopping Frontend...${NC}"
stop_service "Frontend" "$LOG_DIR/frontend.pid"

# Also kill any remaining npm/vite processes
pkill -f "vite" 2>/dev/null && echo -e "${GREEN}✓ Killed remaining Vite processes${NC}"

# Stop Arq Worker
echo -e "${BLUE}[2/5] Stopping Arq Worker...${NC}"
stop_service "Arq Worker" "$LOG_DIR/arq_worker.pid"

# Also kill any remaining arq processes
pkill -f "arq src.ai.worker.WorkerSettings" 2>/dev/null && echo -e "${GREEN}✓ Killed remaining Arq processes${NC}"

# Stop API Gateway
echo -e "${BLUE}[3/5] Stopping API Gateway...${NC}"
stop_service "API Gateway" "$LOG_DIR/api_gateway.pid"

# Stop Backend API
echo -e "${BLUE}[4/5] Stopping Backend API...${NC}"
stop_service "Backend API" "$LOG_DIR/backend_api.pid"

# Kill any remaining uvicorn processes
pkill -f "uvicorn" 2>/dev/null && echo -e "${GREEN}✓ Killed remaining Uvicorn processes${NC}"

# Stop Docker services
echo -e "${BLUE}[5/5] Stopping Docker services...${NC}"
cd "$BACKEND_DIR"
docker compose down
echo -e "${GREEN}✓ Docker services stopped${NC}"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ All services stopped successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Note: Logs are preserved in $LOG_DIR/${NC}"
echo -e "${YELLOW}To start services again, run:${NC}"
echo -e "  ${GREEN}./start_services.sh${NC}"
echo ""
