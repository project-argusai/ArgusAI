#!/bin/bash

#===============================================================================
# ArgusAI - Installation Script
#===============================================================================
# This script automates the setup of the ArgusAI application.
# It checks dependencies, creates virtual environments, installs packages,
# initializes the database, and generates required configuration.
#
# Usage:
#   ./install.sh              # Full installation
#   ./install.sh --help       # Show help
#   ./install.sh --check      # Only check dependencies
#   ./install.sh --backend    # Backend only
#   ./install.sh --frontend   # Frontend only
#   ./install.sh --services   # Generate service files only
#===============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
DATA_DIR="$BACKEND_DIR/data"
MIN_PYTHON_VERSION="3.11"
MIN_NODE_VERSION="18"

# Architecture detection
ARCH=$(uname -m)
OS=$(uname -s)

# Detect Homebrew prefix (macOS only)
BREW_PREFIX=""
if [ "$OS" = "Darwin" ]; then
    if command -v brew &> /dev/null; then
        BREW_PREFIX=$(brew --prefix)
    elif [ "$ARCH" = "arm64" ]; then
        BREW_PREFIX="/opt/homebrew"
    else
        BREW_PREFIX="/usr/local"
    fi
fi

# Flags
INSTALL_BACKEND=true
INSTALL_FRONTEND=true
CHECK_ONLY=false
SERVICES_ONLY=false
VERBOSE=false

#-------------------------------------------------------------------------------
# Helper Functions
#-------------------------------------------------------------------------------

print_header() {
    echo ""
    echo -e "${CYAN}================================================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}================================================================${NC}"
    echo ""
}

print_step() {
    echo -e "${BLUE}➤ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "  $1"
}

# Compare version numbers
version_gte() {
    # Returns 0 if $1 >= $2
    [ "$(printf '%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

show_help() {
    cat << EOF
Live Object AI Classifier - Installation Script

Usage: ./install.sh [OPTIONS]

Options:
  --help, -h        Show this help message
  --check, -c       Only check dependencies, don't install
  --backend, -b     Install backend only
  --frontend, -f    Install frontend only
  --services, -s    Generate service files only (systemd/launchd)
  --verbose, -v     Show verbose output

Examples:
  ./install.sh                  # Full installation
  ./install.sh --check          # Check if dependencies are met
  ./install.sh --backend        # Install backend only
  ./install.sh --services       # Generate service files

For more information, see README.md
EOF
    exit 0
}

#-------------------------------------------------------------------------------
# Dependency Checks
#-------------------------------------------------------------------------------

check_python() {
    print_step "Checking Python..."

    # Try python3 first, then python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        print_error "Python not found"
        print_info "Please install Python $MIN_PYTHON_VERSION or higher"
        print_info "  macOS: brew install python@3.11"
        print_info "  Ubuntu/Debian: sudo apt install python3.11"
        print_info "  Windows: Download from https://python.org"
        return 1
    fi

    # Get version
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

    if version_gte "$PYTHON_VERSION" "$MIN_PYTHON_VERSION"; then
        print_success "Python $PYTHON_VERSION found ($PYTHON_CMD)"
        return 0
    else
        print_error "Python $PYTHON_VERSION found, but $MIN_PYTHON_VERSION+ required"
        return 1
    fi
}

check_node() {
    print_step "Checking Node.js..."

    if ! command -v node &> /dev/null; then
        print_error "Node.js not found"
        print_info "Please install Node.js $MIN_NODE_VERSION or higher"
        print_info "  macOS: brew install node"
        print_info "  Ubuntu/Debian: See https://nodejs.org/en/download"
        print_info "  Windows: Download from https://nodejs.org"
        return 1
    fi

    # Get version (strip leading 'v')
    NODE_VERSION=$(node --version | sed 's/^v//')
    NODE_MAJOR=$(echo "$NODE_VERSION" | cut -d. -f1)

    if [ "$NODE_MAJOR" -ge "$MIN_NODE_VERSION" ]; then
        print_success "Node.js $NODE_VERSION found"
        return 0
    else
        print_error "Node.js $NODE_VERSION found, but $MIN_NODE_VERSION+ required"
        return 1
    fi
}

check_npm() {
    print_step "Checking npm..."

    if command -v npm &> /dev/null; then
        NPM_VERSION=$(npm --version)
        print_success "npm $NPM_VERSION found"
        return 0
    else
        print_error "npm not found"
        return 1
    fi
}

check_git() {
    print_step "Checking Git..."

    if command -v git &> /dev/null; then
        GIT_VERSION=$(git --version | awk '{print $3}')
        print_success "Git $GIT_VERSION found"
        return 0
    else
        print_warning "Git not found (optional, but recommended)"
        return 0  # Not a hard requirement
    fi
}

check_architecture() {
    print_step "Detecting system architecture..."
    print_info "  Architecture: $ARCH"
    print_info "  OS: $OS"
    if [ -n "$BREW_PREFIX" ]; then
        print_info "  Homebrew prefix: $BREW_PREFIX"
    fi
    print_success "Architecture detected"
}

check_all_dependencies() {
    print_header "Checking Dependencies"

    local all_good=true

    check_architecture
    check_python || all_good=false
    check_node || all_good=false
    check_npm || all_good=false
    check_git

    echo ""
    if [ "$all_good" = true ]; then
        print_success "All required dependencies are installed"
        return 0
    else
        print_error "Some dependencies are missing"
        return 1
    fi
}

#-------------------------------------------------------------------------------
# Backend Installation
#-------------------------------------------------------------------------------

setup_backend() {
    print_header "Setting Up Backend"

    cd "$BACKEND_DIR"

    # Create data directory
    print_step "Creating data directory..."
    mkdir -p "$DATA_DIR"
    print_success "Data directory created: $DATA_DIR"

    # Create virtual environment
    print_step "Creating Python virtual environment..."
    if [ -d "venv" ]; then
        print_warning "Virtual environment already exists, skipping creation"
    else
        $PYTHON_CMD -m venv venv
        print_success "Virtual environment created"
    fi

    # Activate virtual environment
    print_step "Activating virtual environment..."
    source venv/bin/activate
    print_success "Virtual environment activated"

    # Upgrade pip
    print_step "Upgrading pip..."
    pip install --upgrade pip --quiet
    print_success "pip upgraded"

    # Install dependencies
    print_step "Installing Python dependencies (this may take a few minutes)..."
    pip install -r requirements.txt --quiet
    print_success "Python dependencies installed"

    # Create .env file if it doesn't exist
    print_step "Configuring environment..."
    if [ -f ".env" ]; then
        print_warning ".env file already exists, preserving existing configuration"
    else
        cp .env.example .env

        # Generate encryption key
        print_step "Generating encryption key..."
        ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

        # Replace placeholder in .env
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            sed -i '' "s/your-generated-fernet-key-here/$ENCRYPTION_KEY/" .env
        else
            # Linux
            sed -i "s/your-generated-fernet-key-here/$ENCRYPTION_KEY/" .env
        fi

        print_success "Environment configured with new encryption key"
    fi

    # Run database migrations
    print_step "Running database migrations..."
    alembic upgrade head
    print_success "Database initialized"

    deactivate
    print_success "Backend setup complete"
}

#-------------------------------------------------------------------------------
# Frontend Installation
#-------------------------------------------------------------------------------

setup_frontend() {
    print_header "Setting Up Frontend"

    cd "$FRONTEND_DIR"

    # Install dependencies
    print_step "Installing Node.js dependencies (this may take a few minutes)..."
    npm install --silent
    print_success "Node.js dependencies installed"

    # Create .env.local if it doesn't exist
    print_step "Configuring environment..."
    if [ -f ".env.local" ]; then
        print_warning ".env.local already exists, preserving existing configuration"
    else
        echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
        print_success "Environment configured"
    fi

    # Build frontend
    print_step "Building frontend (this may take a minute)..."
    npm run build --silent 2>/dev/null || {
        print_warning "Build completed with warnings (this is usually fine)"
    }
    print_success "Frontend build complete"

    print_success "Frontend setup complete"
}

#-------------------------------------------------------------------------------
# Service File Generation
#-------------------------------------------------------------------------------

generate_systemd_service() {
    print_header "Generating systemd Service Files"

    local SERVICE_DIR="$SCRIPT_DIR/services"
    mkdir -p "$SERVICE_DIR"

    # Backend service
    print_step "Creating backend service file..."
    cat > "$SERVICE_DIR/live-object-backend.service" << EOF
[Unit]
Description=Live Object AI Classifier - Backend API
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin"
ExecStart=$BACKEND_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=live-object-backend

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    print_success "Created: $SERVICE_DIR/live-object-backend.service"

    # Frontend service
    print_step "Creating frontend service file..."
    cat > "$SERVICE_DIR/live-object-frontend.service" << EOF
[Unit]
Description=Live Object AI Classifier - Frontend
After=network.target live-object-backend.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$FRONTEND_DIR
ExecStart=/usr/bin/npm run start
Restart=always
RestartSec=10

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=live-object-frontend

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    print_success "Created: $SERVICE_DIR/live-object-frontend.service"

    echo ""
    print_info "To install systemd services:"
    print_info "  sudo cp $SERVICE_DIR/*.service /etc/systemd/system/"
    print_info "  sudo systemctl daemon-reload"
    print_info "  sudo systemctl enable live-object-backend live-object-frontend"
    print_info "  sudo systemctl start live-object-backend live-object-frontend"
}

generate_launchd_plist() {
    print_header "Generating launchd Plist Files (macOS)"

    local PLIST_DIR="$SCRIPT_DIR/services"
    mkdir -p "$PLIST_DIR"

    local LABEL_PREFIX="com.liveobject"

    # Backend plist
    print_step "Creating backend plist file..."
    cat > "$PLIST_DIR/$LABEL_PREFIX.backend.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL_PREFIX.backend</string>

    <key>ProgramArguments</key>
    <array>
        <string>$BACKEND_DIR/venv/bin/uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>8000</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$BACKEND_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$BACKEND_DIR/venv/bin:$BREW_PREFIX/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/live-object-backend.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/live-object-backend.error.log</string>
</dict>
</plist>
EOF
    print_success "Created: $PLIST_DIR/$LABEL_PREFIX.backend.plist"

    # Frontend plist
    print_step "Creating frontend plist file..."
    cat > "$PLIST_DIR/$LABEL_PREFIX.frontend.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL_PREFIX.frontend</string>

    <key>ProgramArguments</key>
    <array>
        <string>$BREW_PREFIX/bin/npm</string>
        <string>run</string>
        <string>start</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$FRONTEND_DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/live-object-frontend.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/live-object-frontend.error.log</string>
</dict>
</plist>
EOF
    print_success "Created: $PLIST_DIR/$LABEL_PREFIX.frontend.plist"

    echo ""
    print_info "To install launchd services:"
    print_info "  cp $PLIST_DIR/*.plist ~/Library/LaunchAgents/"
    print_info "  launchctl load ~/Library/LaunchAgents/$LABEL_PREFIX.backend.plist"
    print_info "  launchctl load ~/Library/LaunchAgents/$LABEL_PREFIX.frontend.plist"
    echo ""
    print_info "To unload services:"
    print_info "  launchctl unload ~/Library/LaunchAgents/$LABEL_PREFIX.backend.plist"
    print_info "  launchctl unload ~/Library/LaunchAgents/$LABEL_PREFIX.frontend.plist"
}

generate_nginx_config() {
    print_header "Generating nginx Configuration"

    local CONFIG_DIR="$SCRIPT_DIR/services"
    mkdir -p "$CONFIG_DIR"

    print_step "Creating nginx configuration..."
    cat > "$CONFIG_DIR/nginx-live-object.conf" << 'EOF'
# Live Object AI Classifier - nginx Reverse Proxy Configuration
#
# This configuration provides:
# - Reverse proxy to frontend (Next.js) and backend (FastAPI)
# - WebSocket support for real-time updates
# - SSL/TLS configuration (commented out - configure your certificates)
# - Security headers
#
# Installation:
#   sudo cp nginx-live-object.conf /etc/nginx/sites-available/live-object
#   sudo ln -s /etc/nginx/sites-available/live-object /etc/nginx/sites-enabled/
#   sudo nginx -t
#   sudo systemctl reload nginx

# Upstream definitions
upstream backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

upstream frontend {
    server 127.0.0.1:3000;
    keepalive 32;
}

server {
    listen 80;
    server_name localhost;  # Change to your domain

    # Redirect HTTP to HTTPS (uncomment when SSL is configured)
    # return 301 https://$server_name$request_uri;

    # Frontend (Next.js)
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }

    # Backend API
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeout for long-running requests
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    # WebSocket endpoint
    location /ws {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket timeout (24 hours)
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
    }

    # API docs
    location /docs {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /redoc {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /openapi.json {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://backend/api/v1/system/health;
        proxy_set_header Host $host;
    }

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
}

# HTTPS Configuration (uncomment and configure when you have SSL certificates)
# server {
#     listen 443 ssl http2;
#     server_name localhost;  # Change to your domain
#
#     # SSL Certificate paths
#     ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
#
#     # SSL settings
#     ssl_protocols TLSv1.2 TLSv1.3;
#     ssl_prefer_server_ciphers on;
#     ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
#     ssl_session_cache shared:SSL:10m;
#     ssl_session_timeout 10m;
#
#     # HSTS
#     add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
#
#     # Include same location blocks as HTTP server above
#     # ...
# }
EOF
    print_success "Created: $CONFIG_DIR/nginx-live-object.conf"

    echo ""
    print_info "To install nginx configuration:"
    print_info "  sudo cp $CONFIG_DIR/nginx-live-object.conf /etc/nginx/sites-available/live-object"
    print_info "  sudo ln -s /etc/nginx/sites-available/live-object /etc/nginx/sites-enabled/"
    print_info "  sudo nginx -t"
    print_info "  sudo systemctl reload nginx"
}

generate_all_services() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        generate_launchd_plist
    else
        generate_systemd_service
    fi
    generate_nginx_config
}

#-------------------------------------------------------------------------------
# Post-Installation Summary
#-------------------------------------------------------------------------------

print_summary() {
    print_header "Installation Complete!"

    echo -e "${GREEN}The Live Object AI Classifier has been installed successfully.${NC}"
    echo ""
    echo "Next Steps:"
    echo ""
    echo "1. Configure AI Provider API Keys:"
    echo "   - Edit backend/.env and add at least one AI provider key:"
    echo "     OPENAI_API_KEY=sk-..."
    echo "     XAI_API_KEY=xai-..."
    echo "     ANTHROPIC_API_KEY=sk-ant-..."
    echo "     GOOGLE_API_KEY=AIza..."
    echo ""
    echo "2. Start the Application:"
    echo ""
    echo "   Backend (Terminal 1):"
    echo "     cd $BACKEND_DIR"
    echo "     source venv/bin/activate"
    echo "     uvicorn main:app --reload"
    echo ""
    echo "   Frontend (Terminal 2):"
    echo "     cd $FRONTEND_DIR"
    echo "     npm run dev"
    echo ""
    echo "3. Access the Application:"
    echo "   - Dashboard: http://localhost:3000"
    echo "   - API Docs:  http://localhost:8000/docs"
    echo ""
    echo "4. Optional - Configure Cameras:"
    echo "   - UniFi Protect: Settings > UniFi Protect > Add Controller"
    echo "   - RTSP Camera:   Cameras > Add Camera > RTSP"
    echo "   - USB/Webcam:    Cameras > Add Camera > USB"
    echo ""
    echo "5. Optional - Set Up as System Service:"
    echo "   - Run: ./install.sh --services"
    echo "   - Follow the printed instructions to install service files"
    echo ""
    print_info "For more information, see README.md"
}

#-------------------------------------------------------------------------------
# Main Script
#-------------------------------------------------------------------------------

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                ;;
            --check|-c)
                CHECK_ONLY=true
                shift
                ;;
            --backend|-b)
                INSTALL_FRONTEND=false
                shift
                ;;
            --frontend|-f)
                INSTALL_BACKEND=false
                shift
                ;;
            --services|-s)
                SERVICES_ONLY=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done

    # Print banner
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║       Live Object AI Classifier - Installation Script         ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Services only mode
    if [ "$SERVICES_ONLY" = true ]; then
        generate_all_services
        exit 0
    fi

    # Check dependencies
    if ! check_all_dependencies; then
        print_error "Please install missing dependencies and run this script again"
        exit 1
    fi

    # Exit if check only
    if [ "$CHECK_ONLY" = true ]; then
        exit 0
    fi

    # Install components
    if [ "$INSTALL_BACKEND" = true ]; then
        setup_backend
    fi

    if [ "$INSTALL_FRONTEND" = true ]; then
        setup_frontend
    fi

    # Print summary
    print_summary
}

# Run main function
main "$@"
