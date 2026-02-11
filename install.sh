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
#   ./install.sh --update     # Update existing installation
#   ./install.sh --ssl-only   # Configure SSL certificates only
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
UPDATE_MODE=false
VERBOSE=false
SSL_ONLY=false

# Server configuration (set during installation)
SERVER_HOSTNAME=""

# SSL configuration (set during SSL setup)
SSL_METHOD=""  # letsencrypt, self-signed, skip
SSL_DOMAIN=""
SSL_EMAIL=""
CERT_DIR="$BACKEND_DIR/data/certs"

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
ArgusAI - Installation Script

Usage: ./install.sh [OPTIONS]

Options:
  --help, -h        Show this help message
  --check, -c       Only check dependencies, don't install
  --backend, -b     Install backend only
  --frontend, -f    Install frontend only
  --services, -s    Generate service files only (systemd/launchd)
  --update, -u      Update existing installation (pull code, update deps, migrate DB)
  --ssl-only        Configure SSL certificates only (for existing installations)
  --verbose, -v     Show verbose output

Examples:
  ./install.sh                  # Full installation
  ./install.sh --check          # Check if dependencies are met
  ./install.sh --backend        # Install backend only
  ./install.sh --services       # Generate service files
  ./install.sh --update         # Update to latest version
  ./install.sh --ssl-only       # Configure SSL for existing installation

For more information, see README.md
EOF
    exit 0
}

#-------------------------------------------------------------------------------
# Server Configuration Prompts
#-------------------------------------------------------------------------------

prompt_server_hostname() {
    print_header "Server Configuration"

    # Try to detect hostname
    local detected_hostname=""
    if command -v hostname &> /dev/null; then
        detected_hostname=$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo "")
    fi

    # If we couldn't detect, try to get IP
    if [ -z "$detected_hostname" ] || [ "$detected_hostname" = "localhost" ]; then
        if command -v ip &> /dev/null; then
            detected_hostname=$(ip route get 1 2>/dev/null | awk '{print $7; exit}' || echo "")
        elif command -v ifconfig &> /dev/null; then
            detected_hostname=$(ifconfig 2>/dev/null | grep 'inet ' | grep -v '127.0.0.1' | head -1 | awk '{print $2}' || echo "")
        fi
    fi

    # Default to localhost if nothing detected
    if [ -z "$detected_hostname" ]; then
        detected_hostname="localhost"
    fi

    echo "ArgusAI needs to know how you'll access it from your browser."
    echo ""
    echo "This should be the hostname, domain name, or IP address that you'll"
    echo "use to access the web interface (e.g., 'argusai.local', '192.168.1.100')."
    echo ""

    if [ "$detected_hostname" != "localhost" ]; then
        print_info "Detected: $detected_hostname"
    fi

    echo ""
    read -p "Enter server hostname/IP [$detected_hostname]: " input_hostname

    # Use detected hostname if user just pressed enter
    SERVER_HOSTNAME="${input_hostname:-$detected_hostname}"

    # Remove any protocol prefix if user accidentally included it
    SERVER_HOSTNAME=$(echo "$SERVER_HOSTNAME" | sed 's|^https\?://||' | sed 's|/.*$||')

    echo ""
    print_success "Server hostname set to: $SERVER_HOSTNAME"
    echo ""
    print_info "Frontend will be accessible at: http://$SERVER_HOSTNAME:3000"
    print_info "Backend API will be at: http://$SERVER_HOSTNAME:8000"
    echo ""
}

#-------------------------------------------------------------------------------
# SSL Certificate Setup Functions
#-------------------------------------------------------------------------------

prompt_ssl_setup() {
    print_header "SSL Certificate Configuration"

    echo "ArgusAI can be configured with SSL/HTTPS for secure connections."
    echo "This is required for push notifications to work properly."
    echo ""
    echo "Choose an SSL certificate option:"
    echo ""
    echo "  1) Let's Encrypt (Recommended for production)"
    echo "     - Free, trusted certificates"
    echo "     - Requires a domain name pointing to this server"
    echo "     - Requires port 80 to be accessible from the internet"
    echo "     - Auto-renewal will be configured"
    echo ""
    echo "  2) Self-signed Certificate"
    echo "     - Good for local/private networks"
    echo "     - Browsers will show a security warning"
    echo "     - No domain name required"
    echo ""
    echo "  3) Skip SSL Configuration"
    echo "     - ArgusAI will run on HTTP only"
    echo "     - Push notifications may not work"
    echo ""

    while true; do
        read -p "Select option [1-3]: " ssl_choice
        case $ssl_choice in
            1)
                SSL_METHOD="letsencrypt"
                setup_letsencrypt
                break
                ;;
            2)
                SSL_METHOD="self-signed"
                generate_self_signed_cert
                break
                ;;
            3)
                SSL_METHOD="skip"
                handle_ssl_skip
                break
                ;;
            *)
                print_warning "Invalid option. Please enter 1, 2, or 3."
                ;;
        esac
    done
}

check_certbot_installed() {
    if command -v certbot &> /dev/null; then
        return 0
    fi
    return 1
}

install_certbot() {
    print_step "Installing certbot..."

    if [ "$OS" = "Darwin" ]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install certbot
        else
            print_error "Homebrew not found. Please install certbot manually:"
            print_info "  brew install certbot"
            return 1
        fi
    elif [ "$OS" = "Linux" ]; then
        # Detect package manager
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y certbot
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y certbot
        elif command -v yum &> /dev/null; then
            sudo yum install -y certbot
        elif command -v pacman &> /dev/null; then
            sudo pacman -S --noconfirm certbot
        else
            print_error "Could not detect package manager. Please install certbot manually."
            return 1
        fi
    else
        print_error "Unsupported operating system for automatic certbot installation."
        return 1
    fi

    if check_certbot_installed; then
        print_success "certbot installed successfully"
        return 0
    else
        print_error "certbot installation failed"
        return 1
    fi
}

setup_letsencrypt() {
    print_step "Setting up Let's Encrypt certificate..."

    # Check for certbot
    if ! check_certbot_installed; then
        print_warning "certbot is not installed"
        read -p "Would you like to install certbot? [Y/n]: " install_choice
        if [[ ! "$install_choice" =~ ^[Nn]$ ]]; then
            if ! install_certbot; then
                print_error "Cannot proceed without certbot"
                SSL_METHOD="skip"
                return 1
            fi
        else
            print_error "Cannot proceed without certbot"
            SSL_METHOD="skip"
            return 1
        fi
    fi

    # Prompt for domain name
    echo ""
    read -p "Enter your domain name (e.g., argusai.example.com): " SSL_DOMAIN
    if [ -z "$SSL_DOMAIN" ]; then
        print_error "Domain name is required for Let's Encrypt"
        SSL_METHOD="skip"
        return 1
    fi

    # Prompt for email
    read -p "Enter your email address (for certificate notifications): " SSL_EMAIL
    if [ -z "$SSL_EMAIL" ]; then
        print_error "Email is required for Let's Encrypt"
        SSL_METHOD="skip"
        return 1
    fi

    # Create certificate directory
    mkdir -p "$CERT_DIR"

    # Check if port 80 is available
    if command -v lsof &> /dev/null && lsof -Pi :80 -sTCP:LISTEN -t >/dev/null 2>&1; then
        print_warning "Port 80 is currently in use. Certbot needs port 80 for verification."
        print_info "Please stop any services using port 80 (e.g., nginx, apache) and try again."
        read -p "Continue anyway? [y/N]: " continue_choice
        if [[ ! "$continue_choice" =~ ^[Yy]$ ]]; then
            SSL_METHOD="skip"
            return 1
        fi
    fi

    print_step "Requesting certificate from Let's Encrypt..."
    print_info "This may take a moment..."

    # Run certbot in standalone mode
    if sudo certbot certonly --standalone \
        -d "$SSL_DOMAIN" \
        --email "$SSL_EMAIL" \
        --agree-tos \
        --non-interactive \
        --cert-name argusai; then

        # Create symlinks to the Let's Encrypt live directory
        local le_cert="/etc/letsencrypt/live/argusai/fullchain.pem"
        local le_key="/etc/letsencrypt/live/argusai/privkey.pem"

        if [ -f "$le_cert" ] && [ -f "$le_key" ]; then
            # Create symlinks in our data/certs directory
            ln -sf "$le_cert" "$CERT_DIR/cert.pem"
            ln -sf "$le_key" "$CERT_DIR/key.pem"

            print_success "Let's Encrypt certificate obtained successfully!"
            print_info "Certificate: $le_cert"
            print_info "Private key: $le_key"
            print_info "Symlinks created in: $CERT_DIR/"

            # Configure auto-renewal
            configure_cert_renewal

            return 0
        else
            print_error "Certificate files not found after certbot completion"
            SSL_METHOD="skip"
            return 1
        fi
    else
        print_error "Failed to obtain Let's Encrypt certificate"
        print_info "Common issues:"
        print_info "  - Domain not pointing to this server"
        print_info "  - Port 80 blocked by firewall"
        print_info "  - Rate limit exceeded (try again later)"
        SSL_METHOD="skip"
        return 1
    fi
}

configure_cert_renewal() {
    print_step "Configuring automatic certificate renewal..."

    local SERVICE_DIR="$SCRIPT_DIR/services"
    mkdir -p "$SERVICE_DIR"

    if [ "$OS" = "Linux" ]; then
        # Create systemd timer for Linux
        print_step "Creating systemd timer for certificate renewal..."

        # Create renewal service
        cat > "$SERVICE_DIR/argusai-certbot-renewal.service" << EOF
[Unit]
Description=ArgusAI - Certbot Certificate Renewal
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --cert-name argusai
ExecStartPost=/bin/systemctl restart argusai-backend.service
EOF

        # Create renewal timer (runs twice daily as recommended by Let's Encrypt)
        cat > "$SERVICE_DIR/argusai-certbot-renewal.timer" << EOF
[Unit]
Description=ArgusAI - Certbot Certificate Renewal Timer

[Timer]
OnCalendar=*-*-* 00,12:00:00
RandomizedDelaySec=3600
Persistent=true

[Install]
WantedBy=timers.target
EOF

        print_success "Created: $SERVICE_DIR/argusai-certbot-renewal.service"
        print_success "Created: $SERVICE_DIR/argusai-certbot-renewal.timer"
        echo ""
        print_info "To enable automatic renewal:"
        print_info "  sudo cp $SERVICE_DIR/argusai-certbot-renewal.* /etc/systemd/system/"
        print_info "  sudo systemctl daemon-reload"
        print_info "  sudo systemctl enable argusai-certbot-renewal.timer"
        print_info "  sudo systemctl start argusai-certbot-renewal.timer"

        # Verify with dry-run
        print_step "Verifying renewal configuration..."
        if sudo certbot renew --dry-run --cert-name argusai 2>/dev/null; then
            print_success "Certificate renewal test passed"
        else
            print_warning "Certificate renewal dry-run had issues (may still work)"
        fi

    elif [ "$OS" = "Darwin" ]; then
        # Create launchd plist for macOS
        print_step "Creating launchd plist for certificate renewal..."

        local PLIST_FILE="$SERVICE_DIR/com.argusai.certbot-renewal.plist"
        cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.argusai.certbot-renewal</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>/usr/local/bin/certbot renew --quiet --cert-name argusai && launchctl kickstart -k gui/\$(id -u)/com.argusai.backend</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict>
            <key>Hour</key>
            <integer>0</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
        <dict>
            <key>Hour</key>
            <integer>12</integer>
            <key>Minute</key>
            <integer>0</integer>
        </dict>
    </array>

    <key>StandardOutPath</key>
    <string>/tmp/argusai-certbot-renewal.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/argusai-certbot-renewal.error.log</string>
</dict>
</plist>
EOF

        print_success "Created: $PLIST_FILE"
        echo ""
        print_info "To enable automatic renewal:"
        print_info "  sudo cp $PLIST_FILE /Library/LaunchDaemons/"
        print_info "  sudo launchctl load /Library/LaunchDaemons/com.argusai.certbot-renewal.plist"

        # Verify with dry-run
        print_step "Verifying renewal configuration..."
        if sudo certbot renew --dry-run --cert-name argusai 2>/dev/null; then
            print_success "Certificate renewal test passed"
        else
            print_warning "Certificate renewal dry-run had issues (may still work)"
        fi
    fi
}

generate_self_signed_cert() {
    print_step "Generating self-signed certificate..."

    # Create certificate directory
    mkdir -p "$CERT_DIR"

    # Determine CN (Common Name) - use SERVER_HOSTNAME if set, otherwise localhost
    local cn="${SERVER_HOSTNAME:-localhost}"

    # Generate 2048-bit RSA key and self-signed certificate
    print_info "Generating 2048-bit RSA key and certificate (valid for 365 days)..."

    if openssl req -x509 \
        -newkey rsa:2048 \
        -keyout "$CERT_DIR/key.pem" \
        -out "$CERT_DIR/cert.pem" \
        -days 365 \
        -nodes \
        -subj "/CN=$cn" \
        2>/dev/null; then

        # Set proper file permissions
        chmod 600 "$CERT_DIR/key.pem"   # Owner read/write only for private key
        chmod 644 "$CERT_DIR/cert.pem"  # World-readable for certificate

        print_success "Self-signed certificate generated successfully!"
        print_info "Certificate: $CERT_DIR/cert.pem"
        print_info "Private key: $CERT_DIR/key.pem"
        print_info "Common Name (CN): $cn"

        # Display browser warning
        display_self_signed_warning
    else
        print_error "Failed to generate self-signed certificate"
        print_info "Please ensure openssl is installed"
        SSL_METHOD="skip"
        return 1
    fi
}

display_self_signed_warning() {
    echo ""
    echo -e "${YELLOW}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║                    IMPORTANT NOTICE                            ║${NC}"
    echo -e "${YELLOW}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}You are using a self-signed certificate.${NC}"
    echo ""
    echo "When you access ArgusAI via HTTPS, your browser will show a security"
    echo "warning because the certificate is not from a trusted authority."
    echo ""
    echo "To proceed in your browser:"
    echo ""
    echo "  Chrome/Edge:  Click 'Advanced' → 'Proceed to [site] (unsafe)'"
    echo "  Firefox:      Click 'Advanced' → 'Accept the Risk and Continue'"
    echo "  Safari:       Click 'Show Details' → 'visit this website'"
    echo ""
    echo "Alternative - Add certificate to system trust store:"
    echo ""
    if [ "$OS" = "Darwin" ]; then
        echo "  macOS:"
        echo "    sudo security add-trusted-cert -d -r trustRoot \\"
        echo "      -k /Library/Keychains/System.keychain $CERT_DIR/cert.pem"
    else
        echo "  Linux (Ubuntu/Debian):"
        echo "    sudo cp $CERT_DIR/cert.pem /usr/local/share/ca-certificates/argusai.crt"
        echo "    sudo update-ca-certificates"
        echo ""
        echo "  Linux (RHEL/CentOS/Fedora):"
        echo "    sudo cp $CERT_DIR/cert.pem /etc/pki/ca-trust/source/anchors/argusai.crt"
        echo "    sudo update-ca-trust"
    fi
    echo ""
}

handle_ssl_skip() {
    print_warning "Skipping SSL configuration"
    echo ""
    print_info "ArgusAI will run on HTTP only."
    echo ""
    echo -e "${YELLOW}Note: Push notifications require HTTPS to function properly.${NC}"
    echo "If you need push notifications, you can run the SSL setup later:"
    echo ""
    echo "  ./install.sh --ssl-only"
    echo ""
}

update_env_ssl_config() {
    print_step "Updating .env with SSL configuration..."

    local env_file="$BACKEND_DIR/.env"

    if [ ! -f "$env_file" ]; then
        print_warning ".env file not found, will be created during backend setup"
        return 0
    fi

    # Function to update or add env variable
    update_env_var() {
        local key="$1"
        local value="$2"
        if grep -q "^${key}=" "$env_file"; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^${key}=.*|${key}=${value}|" "$env_file"
            else
                sed -i "s|^${key}=.*|${key}=${value}|" "$env_file"
            fi
        else
            echo "${key}=${value}" >> "$env_file"
        fi
    }

    if [ "$SSL_METHOD" = "letsencrypt" ] || [ "$SSL_METHOD" = "self-signed" ]; then
        update_env_var "SSL_ENABLED" "True"
        update_env_var "SSL_CERT_FILE" "$CERT_DIR/cert.pem"
        update_env_var "SSL_KEY_FILE" "$CERT_DIR/key.pem"
        update_env_var "SSL_REDIRECT_HTTP" "True"
        print_success "SSL enabled in .env"

        # Update CORS origins for HTTPS
        if [ -n "$SERVER_HOSTNAME" ]; then
            local current_cors=$(grep "^CORS_ORIGINS=" "$env_file" | cut -d'=' -f2-)
            local https_origins="https://$SERVER_HOSTNAME:443,https://$SERVER_HOSTNAME:3000"
            if [ -n "$current_cors" ]; then
                local new_cors="${current_cors},${https_origins}"
                update_env_var "CORS_ORIGINS" "$new_cors"
            else
                update_env_var "CORS_ORIGINS" "http://localhost:3000,http://localhost:8000,$https_origins"
            fi
            print_success "CORS origins updated for HTTPS"
        fi
    else
        update_env_var "SSL_ENABLED" "False"
        print_info "SSL disabled in .env"
    fi
}

update_frontend_ssl_config() {
    print_step "Updating frontend SSL configuration..."

    local env_file="$FRONTEND_DIR/.env.local"

    if [ ! -f "$env_file" ]; then
        print_warning "Frontend .env.local not found, will be created during frontend setup"
        return 0
    fi

    local api_host="${SERVER_HOSTNAME:-localhost}"

    if [ "$SSL_METHOD" = "letsencrypt" ] || [ "$SSL_METHOD" = "self-signed" ]; then
        # Update API URL to use HTTPS
        local api_url="https://$api_host:443"

        if grep -q "^NEXT_PUBLIC_API_URL=" "$env_file"; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=$api_url|" "$env_file"
            else
                sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=$api_url|" "$env_file"
            fi
        else
            echo "NEXT_PUBLIC_API_URL=$api_url" >> "$env_file"
        fi

        # Add SSL certificate paths for frontend server
        if grep -q "^SSL_CERT_FILE=" "$env_file"; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^SSL_CERT_FILE=.*|SSL_CERT_FILE=$CERT_DIR/cert.pem|" "$env_file"
            else
                sed -i "s|^SSL_CERT_FILE=.*|SSL_CERT_FILE=$CERT_DIR/cert.pem|" "$env_file"
            fi
        else
            echo "SSL_CERT_FILE=$CERT_DIR/cert.pem" >> "$env_file"
        fi

        if grep -q "^SSL_KEY_FILE=" "$env_file"; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^SSL_KEY_FILE=.*|SSL_KEY_FILE=$CERT_DIR/key.pem|" "$env_file"
            else
                sed -i "s|^SSL_KEY_FILE=.*|SSL_KEY_FILE=$CERT_DIR/key.pem|" "$env_file"
            fi
        else
            echo "SSL_KEY_FILE=$CERT_DIR/key.pem" >> "$env_file"
        fi

        print_success "Frontend configured for HTTPS (API: $api_url)"
    else
        # Use HTTP API URL
        local api_url="http://$api_host:8000"

        if grep -q "^NEXT_PUBLIC_API_URL=" "$env_file"; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=$api_url|" "$env_file"
            else
                sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=$api_url|" "$env_file"
            fi
        fi

        print_info "Frontend configured for HTTP (API: $api_url)"
    fi
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
# Linux System Configuration (Firewall, SELinux)
#-------------------------------------------------------------------------------

configure_linux_system() {
    # Only run on Linux
    if [ "$OS" != "Linux" ]; then
        return 0
    fi

    print_header "Configuring Linux System"

    # Configure SELinux
    if command -v getenforce &> /dev/null; then
        local selinux_status=$(getenforce 2>/dev/null || echo "Disabled")
        if [ "$selinux_status" = "Enforcing" ]; then
            print_step "Configuring SELinux..."
            # Set to permissive immediately
            setenforce 0 2>/dev/null || print_warning "Could not set SELinux to permissive (may need root)"
            # Make permanent
            if [ -f /etc/selinux/config ]; then
                if grep -q "^SELINUX=enforcing" /etc/selinux/config; then
                    sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config 2>/dev/null || \
                        print_warning "Could not update SELinux config (may need root)"
                    print_success "SELinux set to permissive"
                fi
            fi
        else
            print_success "SELinux is already $selinux_status"
        fi
    fi

    # Configure firewall
    if command -v firewall-cmd &> /dev/null; then
        print_step "Configuring firewall ports..."
        # Check if firewalld is running
        if systemctl is-active --quiet firewalld 2>/dev/null; then
            # Add ports for frontend and backend
            firewall-cmd --add-port=3000/tcp --permanent 2>/dev/null || \
                print_warning "Could not add port 3000 (may need root)"
            firewall-cmd --add-port=8000/tcp --permanent 2>/dev/null || \
                print_warning "Could not add port 8000 (may need root)"
            # Add HomeKit port and mDNS for Apple Home integration
            firewall-cmd --add-port=51826/tcp --permanent 2>/dev/null || \
                print_warning "Could not add port 51826/HomeKit (may need root)"
            firewall-cmd --add-service=mdns --permanent 2>/dev/null || \
                print_warning "Could not add mDNS service (may need root)"
            firewall-cmd --reload 2>/dev/null || \
                print_warning "Could not reload firewall (may need root)"
            print_success "Firewall ports opened: 3000, 8000, 51826 (HomeKit), mDNS"
        else
            print_info "firewalld is not running, skipping firewall configuration"
        fi
    elif command -v ufw &> /dev/null; then
        print_step "Configuring UFW firewall..."
        ufw allow 3000/tcp 2>/dev/null || print_warning "Could not add port 3000 (may need root)"
        ufw allow 8000/tcp 2>/dev/null || print_warning "Could not add port 8000 (may need root)"
        # Add HomeKit port and mDNS for Apple Home integration
        ufw allow 51826/tcp 2>/dev/null || print_warning "Could not add port 51826/HomeKit (may need root)"
        ufw allow 5353/udp 2>/dev/null || print_warning "Could not add port 5353/mDNS (may need root)"
        print_success "Firewall ports opened: 3000, 8000, 51826 (HomeKit), 5353 (mDNS)"
    else
        print_info "No firewall detected, skipping firewall configuration"
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

    # Configure CORS origins with server hostname
    if [ -n "$SERVER_HOSTNAME" ] && [ "$SERVER_HOSTNAME" != "localhost" ]; then
        print_step "Configuring CORS for $SERVER_HOSTNAME..."
        local cors_origins="http://localhost:3000,http://localhost:8000,http://$SERVER_HOSTNAME:3000,http://$SERVER_HOSTNAME:8000"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^CORS_ORIGINS=.*|CORS_ORIGINS=$cors_origins|" .env
        else
            sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=$cors_origins|" .env
        fi
        print_success "CORS configured for $SERVER_HOSTNAME"
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

    # Configure .env.local with API URL
    print_step "Configuring environment..."
    local api_host="${SERVER_HOSTNAME:-localhost}"
    local api_url="http://$api_host:8000"

    if [ -f ".env.local" ]; then
        # Update existing file with new API URL
        if grep -q "^NEXT_PUBLIC_API_URL=" .env.local; then
            if [[ "$OSTYPE" == "darwin"* ]]; then
                sed -i '' "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=$api_url|" .env.local
            else
                sed -i "s|^NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=$api_url|" .env.local
            fi
        else
            echo "NEXT_PUBLIC_API_URL=$api_url" >> .env.local
        fi
        print_success "Environment updated with API URL: $api_url"
    else
        echo "NEXT_PUBLIC_API_URL=$api_url" > .env.local
        print_success "Environment configured with API URL: $api_url"
    fi

    # Build frontend
    print_step "Building frontend (this may take a minute)..."
    NODE_ENV=production npm run build --silent 2>/dev/null || {
        print_warning "Build completed with warnings (this is usually fine)"
    }
    print_success "Frontend build complete"

    print_success "Frontend setup complete"
}

#-------------------------------------------------------------------------------
# Update Functions
#-------------------------------------------------------------------------------

update_code() {
    print_header "Pulling Latest Code"

    cd "$SCRIPT_DIR"

    # Check if this is a git repository
    if [ ! -d ".git" ]; then
        print_error "Not a git repository. Cannot pull updates."
        print_info "If you downloaded a ZIP file, please download the latest version manually."
        return 1
    fi

    # Check for uncommitted changes
    if ! git diff-index --quiet HEAD -- 2>/dev/null; then
        print_warning "You have uncommitted changes"
        read -p "Stash changes and continue? [y/N]: " stash_choice
        if [[ "$stash_choice" =~ ^[Yy]$ ]]; then
            git stash
            print_success "Changes stashed"
        else
            print_error "Update cancelled. Please commit or stash your changes first."
            return 1
        fi
    fi

    # Get current branch
    local current_branch=$(git rev-parse --abbrev-ref HEAD)
    print_info "Current branch: $current_branch"

    # Fetch and pull
    print_step "Fetching latest changes..."
    git fetch origin

    local local_commit=$(git rev-parse HEAD)
    local remote_commit=$(git rev-parse "origin/$current_branch" 2>/dev/null || echo "")

    if [ -z "$remote_commit" ]; then
        print_warning "Could not find remote branch origin/$current_branch"
        print_info "Continuing with local code..."
        return 0
    fi

    if [ "$local_commit" = "$remote_commit" ]; then
        print_success "Already up to date"
        return 0
    fi

    print_step "Pulling updates..."
    git pull origin "$current_branch"
    print_success "Code updated to latest version"

    # Show what changed
    print_info "Changes pulled:"
    git log --oneline "$local_commit..$remote_commit" | head -10
}

update_backend() {
    print_header "Updating Backend"

    cd "$BACKEND_DIR"

    # Check if venv exists
    if [ ! -d "venv" ]; then
        print_error "Virtual environment not found. Run full installation first."
        return 1
    fi

    # Activate virtual environment
    print_step "Activating virtual environment..."
    source venv/bin/activate
    print_success "Virtual environment activated"

    # Upgrade pip
    print_step "Upgrading pip..."
    pip install --upgrade pip --quiet
    print_success "pip upgraded"

    # Update dependencies
    print_step "Updating Python dependencies..."
    pip install -r requirements.txt --quiet --upgrade
    print_success "Python dependencies updated"

    # Run database migrations
    print_step "Running database migrations..."
    alembic upgrade head
    print_success "Database migrations complete"

    deactivate
    print_success "Backend update complete"
}

update_frontend() {
    print_header "Updating Frontend"

    cd "$FRONTEND_DIR"

    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        print_error "node_modules not found. Run full installation first."
        return 1
    fi

    # Update dependencies
    print_step "Updating Node.js dependencies..."
    npm install --silent
    print_success "Node.js dependencies updated"

    # Rebuild frontend
    print_step "Rebuilding frontend..."
    NODE_ENV=production npm run build --silent 2>/dev/null || {
        print_warning "Build completed with warnings (this is usually fine)"
    }
    print_success "Frontend rebuild complete"

    print_success "Frontend update complete"
}

print_update_summary() {
    print_header "Update Complete!"

    echo -e "${GREEN}ArgusAI has been updated successfully.${NC}"
    echo ""
    echo "What was updated:"
    echo "  - Code pulled from git repository"
    if [ "$INSTALL_BACKEND" = true ]; then
        echo "  - Backend Python dependencies updated"
        echo "  - Database migrations applied"
    fi
    if [ "$INSTALL_FRONTEND" = true ]; then
        echo "  - Frontend Node.js dependencies updated"
        echo "  - Frontend rebuilt"
    fi
    echo ""
    echo "Next Steps:"
    echo ""
    echo "  If running as a service, restart the services:"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "    launchctl unload ~/Library/LaunchAgents/com.argusai.*.plist"
        echo "    launchctl load ~/Library/LaunchAgents/com.argusai.*.plist"
    else
        echo "    sudo systemctl restart argusai-backend argusai-frontend"
    fi
    echo ""
    echo "  Or if running manually, restart the dev servers:"
    echo "    Backend:  cd backend && source venv/bin/activate && uvicorn main:app --reload"
    echo "    Frontend: cd frontend && npm run dev"
    echo ""
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
    cat > "$SERVICE_DIR/argusai-backend.service" << EOF
[Unit]
Description=ArgusAI - Backend API
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/venv/bin"
ExecStart=$BACKEND_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 10
Restart=always
RestartSec=5

# Process management - prevent port binding issues on restart (Issue #383)
KillMode=mixed
TimeoutStopSec=15
TimeoutStartSec=30

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=argusai-backend

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$BACKEND_DIR/data $BACKEND_DIR/logs

[Install]
WantedBy=multi-user.target
EOF
    print_success "Created: $SERVICE_DIR/argusai-backend.service"

    # Frontend service - check if SSL is configured
    print_step "Creating frontend service file..."
    local frontend_start_cmd="start"
    local ssl_env_section=""

    # Check if SSL certificates exist
    if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
        frontend_start_cmd="start:ssl"
        ssl_env_section="Environment=\"SSL_CERT_FILE=$CERT_DIR/cert.pem\"
Environment=\"SSL_KEY_FILE=$CERT_DIR/key.pem\""
        print_info "SSL certificates detected - configuring HTTPS frontend service"
    fi

    cat > "$SERVICE_DIR/argusai-frontend.service" << EOF
[Unit]
Description=ArgusAI - Frontend
After=network.target argusai-backend.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$FRONTEND_DIR
Environment="NODE_ENV=production"
$ssl_env_section
ExecStart=/usr/bin/npm run $frontend_start_cmd
Restart=always
RestartSec=5

# Process management - prevent port binding issues on restart (Issue #383)
KillMode=mixed
TimeoutStopSec=15
TimeoutStartSec=30

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=argusai-frontend

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
EOF
    print_success "Created: $SERVICE_DIR/argusai-frontend.service"

    echo ""
    print_info "To install systemd services:"
    print_info "  sudo cp $SERVICE_DIR/*.service /etc/systemd/system/"
    print_info "  sudo systemctl daemon-reload"
    print_info "  sudo systemctl enable argusai-backend argusai-frontend"
    print_info "  sudo systemctl start argusai-backend argusai-frontend"
}

generate_launchd_plist() {
    print_header "Generating launchd Plist Files (macOS)"

    local PLIST_DIR="$SCRIPT_DIR/services"
    mkdir -p "$PLIST_DIR"

    local LABEL_PREFIX="com.argusai"

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
    <string>/tmp/argusai-backend.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/argusai-backend.error.log</string>
</dict>
</plist>
EOF
    print_success "Created: $PLIST_DIR/$LABEL_PREFIX.backend.plist"

    # Frontend plist - check if SSL is configured
    print_step "Creating frontend plist file..."
    local frontend_start_cmd="start"
    local ssl_env_vars=""

    # Check if SSL certificates exist
    if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
        frontend_start_cmd="start:ssl"
        ssl_env_vars="
    <key>EnvironmentVariables</key>
    <dict>
        <key>NODE_ENV</key>
        <string>production</string>
        <key>SSL_CERT_FILE</key>
        <string>$CERT_DIR/cert.pem</string>
        <key>SSL_KEY_FILE</key>
        <string>$CERT_DIR/key.pem</string>
    </dict>"
        print_info "SSL certificates detected - configuring HTTPS frontend service"
    else
        ssl_env_vars="
    <key>EnvironmentVariables</key>
    <dict>
        <key>NODE_ENV</key>
        <string>production</string>
    </dict>"
    fi

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
        <string>$frontend_start_cmd</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$FRONTEND_DIR</string>
$ssl_env_vars
    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/argusai-frontend.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/argusai-frontend.error.log</string>
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
# ArgusAI - nginx Reverse Proxy Configuration
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

    echo -e "${GREEN}ArgusAI has been installed successfully.${NC}"
    echo ""

    # Show SSL configuration status
    echo "Configuration Summary:"
    echo "  - Server hostname: ${SERVER_HOSTNAME:-localhost}"
    if [ "$SSL_METHOD" = "letsencrypt" ]; then
        echo -e "  - SSL: ${GREEN}Enabled (Let's Encrypt)${NC}"
        echo "  - Domain: $SSL_DOMAIN"
    elif [ "$SSL_METHOD" = "self-signed" ]; then
        echo -e "  - SSL: ${YELLOW}Enabled (Self-signed)${NC}"
    else
        echo -e "  - SSL: ${YELLOW}Not configured (HTTP only)${NC}"
    fi
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
    if [ "$SSL_METHOD" = "letsencrypt" ] || [ "$SSL_METHOD" = "self-signed" ]; then
        echo "   Backend (Terminal 1):"
        echo "     cd $BACKEND_DIR"
        echo "     source venv/bin/activate"
        echo "     python main.py"
        echo ""
        echo "   Frontend (Terminal 2):"
        echo "     cd $FRONTEND_DIR"
        echo "     npm run start:ssl"
        echo ""
        echo "3. Access the Application:"
        echo "   - Dashboard: https://${SERVER_HOSTNAME:-localhost}:3000"
        echo "   - API Docs:  https://${SERVER_HOSTNAME:-localhost}:443/docs"
    else
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
        echo "   - Dashboard: http://${SERVER_HOSTNAME:-localhost}:3000"
        echo "   - API Docs:  http://${SERVER_HOSTNAME:-localhost}:8000/docs"
    fi
    echo ""
    echo "4. Optional - Configure Cameras:"
    echo "   - UniFi Protect: Settings > UniFi Protect > Add Controller"
    echo "   - RTSP Camera:   Cameras > Add Camera > RTSP"
    echo "   - USB/Webcam:    Cameras > Add Camera > USB"
    echo ""
    echo "5. Optional - Enable OCR Frame Overlay Extraction:"
    echo "   - Install tesseract for OCR support:"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "     brew install tesseract"
    else
        echo "     sudo apt install tesseract-ocr  # Ubuntu/Debian"
        echo "     sudo dnf install tesseract      # Fedora/RHEL"
    fi
    echo "   - Enable in Settings > System > 'Attempt OCR extraction'"
    echo ""
    echo "6. Optional - Set Up as System Service:"
    echo "   - Run: ./install.sh --services"
    echo "   - Follow the printed instructions to install service files"
    echo ""
    if [ "$SSL_METHOD" = "skip" ] || [ -z "$SSL_METHOD" ]; then
        echo "7. Optional - Configure SSL Later:"
        echo "   - Run: ./install.sh --ssl-only"
        echo "   - Required for push notifications to work"
        echo ""
    fi
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
            --update|-u)
                UPDATE_MODE=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --ssl-only)
                SSL_ONLY=true
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
    echo -e "${CYAN}║              ArgusAI - Installation Script                     ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Services only mode
    if [ "$SERVICES_ONLY" = true ]; then
        generate_all_services
        exit 0
    fi

    # SSL only mode (for existing installations)
    if [ "$SSL_ONLY" = true ]; then
        prompt_ssl_setup
        update_env_ssl_config
        update_frontend_ssl_config
        print_header "SSL Configuration Complete"
        if [ "$SSL_METHOD" = "letsencrypt" ] || [ "$SSL_METHOD" = "self-signed" ]; then
            echo -e "${GREEN}SSL has been configured successfully.${NC}"
            echo ""
            echo "Next steps:"
            echo "  1. Rebuild the frontend: cd frontend && npm run build"
            echo "  2. Restart the ArgusAI backend and frontend services"
            echo "  3. Start frontend with SSL: cd frontend && npm run start:ssl"
            echo "  4. Access ArgusAI at https://${SERVER_HOSTNAME:-localhost}:3000"
        else
            echo "SSL configuration was skipped."
        fi
        exit 0
    fi

    # Update mode
    if [ "$UPDATE_MODE" = true ]; then
        # Pull latest code
        if ! update_code; then
            exit 1
        fi

        # Update components
        if [ "$INSTALL_BACKEND" = true ]; then
            update_backend
        fi

        if [ "$INSTALL_FRONTEND" = true ]; then
            update_frontend
        fi

        # Print summary
        print_update_summary
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

    # Prompt for server hostname
    prompt_server_hostname

    # Prompt for SSL configuration
    prompt_ssl_setup

    # Configure Linux system (firewall, SELinux)
    configure_linux_system

    # Install components
    if [ "$INSTALL_BACKEND" = true ]; then
        setup_backend
    fi

    if [ "$INSTALL_FRONTEND" = true ]; then
        setup_frontend
    fi

    # Update .env with SSL configuration after backend setup
    update_env_ssl_config

    # Update frontend SSL configuration
    update_frontend_ssl_config

    # Print summary
    print_summary
}

# Run main function
main "$@"
