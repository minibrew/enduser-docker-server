#!/usr/bin/env bash
# minibrew.sh — MiniBrew Session Orchestrator management wrapper
#
# Usage:
#   ./minibrew.sh build       Build and start the stack
#   ./minibrew.sh up          Start the stack (keep containers)
#   ./minibrew.sh down        Stop and remove containers
#   ./minibrew.sh restart     Restart the stack
#   ./minibrew.sh rebuild     Rebuild from scratch (down + build + up)
#   ./minibrew.sh backend     Restart backend container only
#   ./minibrew.sh frontend    Restart frontend container only
#   ./minibrew.sh status      Show container status
#   ./minibrew.sh logs [svc] Tail logs (default: backend)
#   ./minibrew.sh clean       Remove containers + images + volumes

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PROJECT="minibrew"

# Colours
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${CYAN}[info]${NC}  $*"; }
success() { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $*"; }
error()   { echo -e "${RED}[error]${NC} $*"; }
bold()    { echo -e "${BOLD}$*${NC}"; }

header() {
  echo ""
  bold "═══════════════════════════════════════════════"
  bold "  MiniBrew Session Orchestrator"
  bold "═══════════════════════════════════════════════"
}

report_url() {
  local ip
  ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
  echo ""
  bold "  Dashboard:  ${CYAN}http://${ip}:8080${NC}"
  bold "  Backend:   ${CYAN}http://${ip}:8000${NC}"
  bold "  API Docs:  ${CYAN}http://${ip}:8000/docs${NC}"
  echo ""
}

check_docker() {
  if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Install Docker first."
    exit 1
  fi
  if ! docker info &>/dev/null; then
    error "Docker daemon is not running. Start Docker and try again."
    exit 1
  fi
}

health_check() {
  local url="${1:-http://localhost:8080/health}"
  local timeout=10
  local elapsed=0

  while [[ $elapsed -lt $timeout ]]; do
    if curl -sf "$url" &>/dev/null; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  return 1
}

wait_healthy() {
  local container="${1:-minibrew-backend}"
  local timeout=30
  local elapsed=0

  info "Waiting for ${container} to become healthy..."

  while [[ $elapsed -lt $timeout ]]; do
    local status
    status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "no-healthcheck")

    if [[ "$status" == "healthy" ]]; then
      success "${container} is healthy"
      return 0
    elif [[ "$status" == "no-healthcheck" ]]; then
      # Fall back to process check
      if docker ps --filter "name=${container}" --filter "status=running" --format "{{.Names}}" | grep -q "^${container}$"; then
        success "${container} is running"
        return 0
      fi
    fi

    sleep 2
    elapsed=$((elapsed + 2))
  done

  warn "${container} did not become healthy within ${timeout}s"
  return 1
}

do_status() {
  header
  echo ""

  local containers="minibrew-backend minibrew-frontend"
  local any_running=0

  for svc in $containers; do
    local state ip port
    state=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "missing")
    ip=$(docker inspect --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$svc" 2>/dev/null || echo "—")

    if [[ "$state" == "running" ]]; then
      local health
      health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$svc" 2>/dev/null || echo "missing")
      local health_str=""
      if [[ "$health" == "healthy" ]]; then
        health_str=" ${GREEN}✓ healthy${NC}"
      elif [[ "$health" == "unhealthy" ]]; then
        health_str=" ${RED}✗ unhealthy${NC}"
      fi
      echo -e "  ${GREEN}●${NC} ${svc}: ${BOLD}${state}${NC}${health_str}"
      ((any_running++))

      # Show exposed port
      port=$(docker inspect --format='{{range $k,$v := .NetworkSettings.Ports}}{{range $v}}{{index $v "HostPort"}} {{end}}{{end}}' "$svc" 2>/dev/null || echo "")
      if [[ -n "$port" ]]; then
        echo -e "    Port: ${port}"
      fi
    elif [[ "$state" == "exited" ]]; then
      echo -e "  ${YELLOW}○${NC} ${svc}: ${state}"
    else
      echo -e "  ${RED}✗${NC} ${svc}: ${state}"
    fi
  done

  echo ""

  if [[ $any_running -eq 2 ]]; then
    if health_check "http://localhost:8080/health"; then
      success "Backend health check passed"
    else
      warn "Backend health check failed — may still be starting"
    fi
    report_url
  else
    warn "Not all containers are running"
    echo ""
    info "Run './minibrew.sh up' to start the stack"
  fi
}

do_build() {
  header
  info "Building and starting the stack..."
  docker-compose -f "$COMPOSE_FILE" up --build -d
  wait_healthy minibrew-backend
  wait_healthy minibrew-frontend
  success "Stack built and started"
  report_url
}

do_up() {
  header
  info "Starting the stack..."
  docker-compose -f "$COMPOSE_FILE" up -d
  wait_healthy minibrew-backend
  wait_healthy minibrew-frontend
  success "Stack started"
  report_url
}

do_down() {
  header
  info "Stopping and removing containers..."
  docker-compose -f "$COMPOSE_FILE" down
  success "Stack stopped and removed"
}

do_restart() {
  header
  info "Restarting the stack..."
  docker-compose -f "$COMPOSE_FILE" restart
  wait_healthy minibrew-backend
  wait_healthy minibrew-frontend
  success "Stack restarted"
  report_url
}

do_rebuild() {
  header
  info "Stopping stack..."
  docker-compose -f "$COMPOSE_FILE" down
  info "Building and starting..."
  docker-compose -f "$COMPOSE_FILE" up --build -d
  wait_healthy minibrew-backend
  wait_healthy minibrew-frontend
  success "Stack rebuilt and started"
  report_url
}

do_backend() {
  header
  info "Rebuilding and restarting backend..."
  docker-compose -f "$COMPOSE_FILE" up --build -d backend
  wait_healthy minibrew-backend
  success "Backend restarted"
  report_url
}

do_frontend() {
  header
  info "Rebuilding and restarting frontend..."
  docker-compose -f "$COMPOSE_FILE" up --build -d frontend
  wait_healthy minibrew-frontend
  success "Frontend restarted"
  report_url
}

do_logs() {
  local service="${1:-backend}"
  docker-compose -f "$COMPOSE_FILE" logs -f --tail=100 "$service"
}

do_clean() {
  header
  warn "This will remove ALL MiniBrew containers, images, and volumes!"
  read -rp "  Are you sure? [y/N] " confirm
  if [[ "${confirm,,}" != "y" ]]; then
    info "Cancelled"
    return
  fi

  info "Removing containers..."
  docker-compose -f "$COMPOSE_FILE" down -v --remove-orphans

  info "Removing project images..."
  docker images --filter="reference=minibrew-*" --format "{{.Repository}}:{{.Tag}}" | xargs -r docker rmi -f 2>/dev/null || true

  success "Clean complete — all containers, volumes, and project images removed"
}

show_help() {
  header
  echo ""
  bold "  Usage:  ./minibrew.sh <command>"
  echo ""
  bold "  Commands:"
  echo "    build       Build Docker images and start the stack"
  echo "    up          Start the stack (keep existing images)"
  echo "    down        Stop and remove containers"
  echo "    restart     Restart the running stack"
  echo "    rebuild     Down + build + up (full rebuild)"
  echo "    backend     Rebuild and restart backend only"
  echo "    frontend    Rebuild and restart frontend only"
  echo "    status      Show container status and health"
  echo "    logs [svc]  Tail logs (default: backend)"
  echo "    clean       Remove containers + images + volumes"
  echo ""
  bold "  Environment:"
  echo "    COMPOSE_FILE=...   Path to docker-compose file (default: docker-compose.yml)"
  echo ""
  report_url
}

# ── Main ──────────────────────────────────────────────────────────────

check_docker

case "${1:-help}" in
  build)   do_build ;;
  up)      do_up ;;
  down)    do_down ;;
  restart) do_restart ;;
  rebuild) do_rebuild ;;
  backend) do_backend ;;
  frontend) do_frontend ;;
  status)  do_status ;;
  logs)    do_logs "${2:-backend}" ;;
  clean)   do_clean ;;
  help|--help|-h) show_help ;;
  *)       error "Unknown command: $1" ;;
esac
