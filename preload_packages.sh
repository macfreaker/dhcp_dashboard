#!/bin/bash

################################################################################
# DHCP Dashboard - Package Pre-loader for Offline Installation
#
# This script downloads and caches all required packages for offline installation
# of the DHCP Dashboard on Raspberry Pi systems without internet access.
#
# Usage: sudo bash preload_packages.sh
################################################################################

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

echo "=========================================="
echo "DHCP Dashboard - Package Pre-loader"
echo "=========================================="
echo ""

# Create cache directory
CACHE_DIR="/var/cache/dhcp-dashboard-packages"
mkdir -p "$CACHE_DIR"

print_status "Creating package cache directory: $CACHE_DIR"

################################################################################
# System Package Pre-loading
################################################################################

print_status "Downloading system packages..."

# Update package lists
print_status "Updating package lists..."
apt-get update -qq

# Download required packages
PACKAGES="dnsmasq hostapd python3-pip"

for package in $PACKAGES; do
    if ! dpkg -l | grep -q "^ii  $package "; then
        print_status "Downloading $package..."
        if apt-get download $package 2>/dev/null; then
            print_success "$package downloaded"
        else
            print_warning "Failed to download $package - may already be cached"
        fi
    else
        print_success "$package already installed"
    fi
done

# Download dependencies for the packages
print_status "Downloading package dependencies..."
apt-get --download-only install -y dnsmasq hostapd python3-pip 2>/dev/null || true

print_success "System packages cached"

################################################################################
# Python Package Pre-loading
################################################################################

print_status "Checking for requirements.txt..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

if [ -f "$REQUIREMENTS_FILE" ]; then
    print_status "Downloading Python packages from requirements.txt..."

    # Create Python package cache directory
    PYTHON_CACHE="$CACHE_DIR/python-packages"
    mkdir -p "$PYTHON_CACHE"

    # Download packages to cache
    pip3 download -r "$REQUIREMENTS_FILE" -d "$PYTHON_CACHE" --break-system-packages 2>/dev/null || {
        print_warning "Some Python packages may not have been cached"
        print_warning "They will need to be installed manually offline"
    }

    print_success "Python packages cached"
else
    print_warning "requirements.txt not found - downloading Flask manually..."
    pip3 download flask -d "$CACHE_DIR/python-packages" --break-system-packages 2>/dev/null || {
        print_warning "Flask download failed"
    }
fi

################################################################################
# Create Offline Installation Instructions
################################################################################

INSTRUCTIONS_FILE="$CACHE_DIR/OFFLINE_INSTALL_README.txt"

cat > "$INSTRUCTIONS_FILE" << 'EOF'
DHCP Dashboard - Offline Installation Instructions
=================================================

This directory contains pre-downloaded packages for offline installation
of the DHCP Dashboard on Raspberry Pi systems without internet access.

Installation Steps:
==================

1. Copy this entire cache directory to your offline Raspberry Pi:
   scp -r /var/cache/dhcp-dashboard-packages user@offline-pi:/tmp/

2. On the offline Raspberry Pi, install system packages:
   cd /tmp/dhcp-dashboard-packages
   sudo dpkg -i *.deb
   sudo apt-get install -f -y  # Fix any dependency issues

3. Install Python packages (if cached):
   sudo pip3 install --no-index --find-links=/tmp/dhcp-dashboard-packages/python-packages -r requirements.txt --break-system-packages

4. Run the setup script in offline mode:
   sudo bash setup_pi.sh --offline

Required Packages:
==================
EOF

# List downloaded packages
echo "Downloaded .deb packages:" >> "$INSTRUCTIONS_FILE"
ls -la *.deb 2>/dev/null >> "$INSTRUCTIONS_FILE" || echo "No .deb packages found" >> "$INSTRUCTIONS_FILE"

echo "" >> "$INSTRUCTIONS_FILE"
echo "Python packages:" >> "$INSTRUCTIONS_FILE"
if [ -d "$CACHE_DIR/python-packages" ]; then
    ls -la "$CACHE_DIR/python-packages/" >> "$INSTRUCTIONS_FILE" 2>/dev/null || echo "No Python packages cached" >> "$INSTRUCTIONS_FILE"
else
    echo "No Python packages cached" >> "$INSTRUCTIONS_FILE"
fi

print_success "Offline installation instructions created: $INSTRUCTIONS_FILE"

################################################################################
# Summary
################################################################################

echo ""
print_success "=========================================="
print_success "Package Pre-loading Complete!"
print_success "=========================================="
echo ""
print_status "Cache directory: $CACHE_DIR"
print_status "Instructions: $INSTRUCTIONS_FILE"
echo ""
print_status "To install on offline systems:"
echo "  1. Copy $CACHE_DIR to offline Raspberry Pi"
echo "  2. Follow instructions in OFFLINE_INSTALL_README.txt"
echo "  3. Run: sudo bash setup_pi.sh --offline"
echo ""
print_success "Ready for offline installation!"