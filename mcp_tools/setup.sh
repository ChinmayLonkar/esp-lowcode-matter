#!/bin/bash
set -e

# MCP Tools Setup Script
# Automatically detects environment, installs dependencies, and configures Cursor MCP integration

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SETUP_DIR="${SCRIPT_DIR}/setup"
CONFIG_DIR="${SCRIPT_DIR}/config"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "MACOS"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "LINUX"
    else
        echo "UNKNOWN"
    fi
}

# Check Python version
check_python() {
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    REQUIRED_VERSION="3.8"
    
    # Convert versions to comparable format (e.g., 3.12 -> 312, 3.8 -> 38)
    PYTHON_VERSION_NUM=$(python3 -c "v='$PYTHON_VERSION'; print(int(v.replace('.', '')))")
    REQUIRED_VERSION_NUM=$(python3 -c "v='$REQUIRED_VERSION'; print(int(v.replace('.', '')))")
    
    if (( PYTHON_VERSION_NUM < REQUIRED_VERSION_NUM )); then
        print_error "Python $REQUIRED_VERSION or higher is required (found $PYTHON_VERSION)"
        exit 1
    fi
    
    print_success "Python $PYTHON_VERSION found"
}

# Install pip if needed
ensure_pip() {
    if ! python3 -m pip --version &> /dev/null; then
        print_info "Installing pip..."
        python3 -m ensurepip --default-pip
        print_success "pip installed"
    fi
}

# Main setup flow
main() {
    print_header "Firmware Development MCP Tools Setup"

    OS=$(detect_os)
    if [ "$OS" = "unknown" ]; then
        print_error "Unsupported operating system"
        exit 1
    fi
    print_success "Detected OS: $OS"

    check_python
    ensure_pip

    print_header "Step 1: Environment Detection"
    python3 "${CONFIG_DIR}/environment_detector.py" || {
        print_error "Environment detection failed"
        exit 1
    }

    print_header "Step 2: Creating Server Environments"
    python3 "${SETUP_DIR}/create_server_venvs.py" || {
        print_error "Server environment creation failed"
        exit 1
    }

    print_header "Step 3: Generating Configuration"
    python3 "${CONFIG_DIR}/generate_config.py" || {
        print_error "Configuration generation failed"
        exit 1
    }

    print_header "Step 4: Validating Setup"
    python3 "${SETUP_DIR}/validate_setup.py" || {
        print_error "Validation failed"
        exit 1
    }

    print_header "Setup Complete!"
    print_success "MCP tools configuration generated"
    echo -e "\n${GREEN}Next steps:${NC}"
    echo "1. Use this MCP configuration json file in your MCP settings:"
    echo "   ${CONFIG_DIR}/mcp.json"
    echo -e "\n${YELLOW}Documentation:${NC} See SETUP_GUIDE.md for detailed information\n"
}

main "$@"
