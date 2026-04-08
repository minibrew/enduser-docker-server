# minibrew.ps1 - MiniBrew Session Orchestrator management wrapper
param(
    [string]$Command = "help",
    [string]$Service = "backend"
)

$COMPOSE_FILE = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { "docker-compose.yml" }
$PROJECT = "minibrew"

$RED = "93m"
$GREEN = "32m"
$YELLOW = "33m"
$CYAN = "36m"
$BOLD = "1m"
$NC = "0m"

function Write-CI([string]$color, [string]$label, [string]$message) {
    $esc = [char]27
    Write-Host "${esc}[${color}${label}${esc}[0m  ${message}"
}

function Info    { param([string]$m) Write-CI $CYAN "[info]" $m }
function Success { param([string]$m) Write-CI $GREEN "[ok]" $m }
function Warn    { param([string]$m) Write-CI $YELLOW "[warn]" $m }
function Error   { param([string]$m) Write-CI $RED "[error]" $m }
function Bold    { param([string]$m) Write-Host "${ESC}[${BOLD}${m}${ESC}[${NC}" }

function Header {
    Write-Host ""
    Bold "======================================================"
    Bold "  MiniBrew Session Orchestrator"
    Bold "======================================================"
}

function Get-LocalIP {
    try {
        (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Manual, Dhcp | Where-Object { $_.IPAddress -ne "127.0.0.1" } | Select-Object -First 1).IPAddress
    } catch {
        "localhost"
    }
}

function Report-URL {
    $ip = Get-LocalIP
    Write-Host ""
    Bold "  Dashboard:  ${ESC}[${CYAN}http://${ip}:8080${ESC}[${NC}"
    Bold "  Backend:   ${ESC}[${CYAN}http://${ip}:8000${ESC}[${NC}"
    Bold "  API Docs:  ${ESC}[${CYAN}http://${ip}:8000/docs${ESC}[${NC}"
    Write-Host ""
}

function Test-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Error "Docker is not installed. Install Docker first."
        exit 1
    }
    try {
        docker info 2>$null | Out-Null
    } catch {
        Error "Docker daemon is not running. Start Docker and try again."
        exit 1
    }
}

function Test-Health {
    param([string]$Url = "http://localhost:8080/health")
    try {
        $null = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
        return $true
    } catch {
        return $false
    }
}

function Wait-Healthy {
    param([string]$Container = "minibrew-backend", [int]$Timeout = 30)
    Info "Waiting for ${Container} to become healthy..."
    $elapsed = 0
    while ($elapsed -lt $Timeout) {
        $status = docker inspect --format='{{.State.Health.Status}}' $Container 2>$null
        if (-not $status) { $status = "no-healthcheck" }
        if ($status -eq "healthy") {
            Success "${Container} is healthy"
            return
        }
        if ($status -eq "no-healthcheck") {
            $running = docker ps --filter "name=$Container" --filter "status=running" --format "{{.Names}}" 2>$null
            if ($running -eq $Container) {
                Success "${Container} is running"
                return
            }
        }
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
    Warn "${Container} did not become healthy within ${Timeout}s"
}

function Get-ContainerStatus {
    param([string]$Name)
    $state = docker inspect --format='{{.State.Status}}' $Name 2>$null
    if (-not $state) { return "missing" }
    return $state
}

function Do-Status {
    Header
    Write-Host ""
    $containers = @("minibrew-backend", "minibrew-frontend")
    $running = 0
    foreach ($svc in $containers) {
        $state = Get-ContainerStatus $svc
        if ($state -eq "running") {
            $health = docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' $svc 2>$null
            $healthStr = ""
            if ($health -eq "healthy") { $healthStr = " ${GREEN}healthy${NC}" }
            elseif ($health -eq "unhealthy") { $healthStr = " ${RED}unhealthy${NC}" }
            Write-CI $GREEN "●" "${svc}: ${state}${healthStr}"
            $port = docker inspect --format='{{range $k,$v := .NetworkSettings.Ports}}{{range $v}}{{index $v "HostPort"}} {{end}}{{end}}' $svc 2>$null
            if ($port) { Write-Host "    Port: $port" }
            $running++
        } elseif ($state -eq "exited") {
            Write-CI $YELLOW "○" "${svc}: ${state}"
        } else {
            Write-CI $RED "✗" "${svc}: ${state}"
        }
    }
    Write-Host ""
    if ($running -eq 2) {
        if (Test-Health) {
            Success "Backend health check passed"
        } else {
            Warn "Backend health check failed - may still be starting"
        }
        Report-URL
    } else {
        Warn "Not all containers are running"
        Write-Host ""
        Info "Run './minibrew.ps1 up' to start the stack"
    }
}

function Do-Up {
    Header
    Info "Starting the stack..."
    docker-compose -f $COMPOSE_FILE up -d
    Wait-Healthy "minibrew-backend"
    Wait-Healthy "minibrew-frontend"
    Success "Stack started"
    Report-URL
}

function Do-Down {
    Header
    Info "Stopping and removing containers..."
    docker-compose -f $COMPOSE_FILE down
    Success "Stack stopped and removed"
}

function Do-Restart {
    Header
    Info "Restarting the stack..."
    docker-compose -f $COMPOSE_FILE restart
    Wait-Healthy "minibrew-backend"
    Wait-Healthy "minibrew-frontend"
    Success "Stack restarted"
    Report-URL
}

function Do-Rebuild {
    Header
    Info "Stopping stack..."
    docker-compose -f $COMPOSE_FILE down
    Info "Building and starting..."
    docker-compose -f $COMPOSE_FILE up --build -d
    Wait-Healthy "minibrew-backend"
    Wait-Healthy "minibrew-frontend"
    Success "Stack rebuilt and started"
    Report-URL
}

function Do-Backend {
    Header
    Info "Rebuilding and restarting backend..."
    docker-compose -f $COMPOSE_FILE up --build -d backend
    Wait-Healthy "minibrew-backend"
    Success "Backend restarted"
    Report-URL
}

function Do-Frontend {
    Header
    Info "Rebuilding and restarting frontend..."
    docker-compose -f $COMPOSE_FILE up --build -d frontend
    Wait-Healthy "minibrew-frontend"
    Success "Frontend restarted"
    Report-URL
}

function Do-Logs {
    docker-compose -f $COMPOSE_FILE logs -f --tail=100 $Service
}

function Do-Clean {
    Header
    Warn "This will remove ALL MiniBrew containers, images, and volumes!"
    $confirm = Read-Host "  Are you sure? [y/N]"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Info "Cancelled"
        return
    }
    Info "Removing containers..."
    docker-compose -f $COMPOSE_FILE down -v --remove-orphans
    Info "Removing project images..."
    docker images --filter="reference=minibrew-*" --format "{{.Repository}}:{{.Tag}}" | ForEach-Object { docker rmi -f $_ 2>$null }
    Success "Clean complete - all containers, volumes, and project images removed"
}

function Show-Help {
    Header
    Write-Host ""
    Bold "  Usage:  ./minibrew.ps1 <command>"
    Write-Host ""
    Bold "  Commands:"
    Write-Host "    build       Build Docker images and start the stack"
    Write-Host "    up          Start the stack (keep existing images)"
    Write-Host "    down        Stop and remove containers"
    Write-Host "    restart     Restart the running stack"
    Write-Host "    rebuild     Down + build + up (full rebuild)"
    Write-Host "    backend     Rebuild and restart backend only"
    Write-Host "    frontend    Rebuild and restart frontend only"
    Write-Host "    status      Show container status and health"
    Write-Host "    logs [svc]  Tail logs (default: backend)"
    Write-Host "    clean       Remove containers + images + volumes"
    Write-Host ""
    Bold "  Environment:"
    Write-Host "    COMPOSE_FILE=...   Path to docker-compose file (default: docker-compose.yml)"
    Write-Host ""
    Report-URL
}

$ESC = [char]27
Test-Docker

switch ($Command) {
    "build"   { Do-Up }
    "up"      { Do-Up }
    "down"    { Do-Down }
    "restart" { Do-Restart }
    "rebuild" { Do-Rebuild }
    "backend" { Do-Backend }
    "frontend"{ Do-Frontend }
    "status"  { Do-Status }
    "logs"    { Do-Logs }
    "clean"   { Do-Clean }
    "help"    { Show-Help }
    default   { Error "Unknown command: $Command"; Show-Help; exit 1 }
}
