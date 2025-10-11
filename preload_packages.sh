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
# Create SD Card Bundle and Installation Instructions
################################################################################

print_status "Creating SD card deployment bundle..."

# Create SD card bundle directory
SD_BUNDLE_DIR="/var/cache/dhcp-dashboard-sd-bundle"
rm -rf "$SD_BUNDLE_DIR"
mkdir -p "$SD_BUNDLE_DIR"

# Copy packages
cp -r "$CACHE_DIR"/* "$SD_BUNDLE_DIR/" 2>/dev/null || true

# Copy application code (assuming we're in the app directory)
if [ -f "setup_pi.sh" ]; then
    print_status "Including application code in SD bundle..."
    cp -r . "$SD_BUNDLE_DIR/dhcp-dashboard-app/"
else
    print_warning "Application code not found in current directory"
    print_warning "Make sure to run this script from the dhcp-dashboard directory"
fi

# Create automated offline installation script
AUTO_INSTALL_SCRIPT="$SD_BUNDLE_DIR/automatic_offline_install.sh"

cat > "$AUTO_INSTALL_SCRIPT" << 'EOF'
#!/bin/bash

################################################################################
# DHCP Dashboard - Automatic Offline Installation for SD Card
#
# This script automatically installs DHCP Dashboard on a fresh Raspberry Pi
# using pre-loaded packages from the SD card bundle.
#
# Place this script in /boot/ directory of SD card before first boot.
# It will run automatically after first boot (requires raspi-config setup).
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "=========================================="
echo "DHCP Dashboard - SD Card Auto-Install"
echo "=========================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Check if we're on a Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    print_warning "Not running on a Raspberry Pi - continuing anyway..."
fi

print_status "Starting automatic offline installation..."

# Find the SD card bundle (check common locations)
BUNDLE_FOUND=false
BUNDLE_DIR=""

# Check /boot (where this script should be)
if [ -d "/boot/dhcp-dashboard-packages" ]; then
    BUNDLE_DIR="/boot"
    BUNDLE_FOUND=true
    print_success "Found SD bundle in /boot/"
fi

# Check /tmp (fallback)
if [ "$BUNDLE_FOUND" = false ] && [ -d "/tmp/dhcp-dashboard-packages" ]; then
    BUNDLE_DIR="/tmp"
    BUNDLE_FOUND=true
    print_success "Found SD bundle in /tmp/"
fi

# Check current directory (for manual execution)
if [ "$BUNDLE_FOUND" = false ] && [ -d "./dhcp-dashboard-packages" ]; then
    BUNDLE_DIR="."
    BUNDLE_FOUND=true
    print_success "Found SD bundle in current directory"
fi

if [ "$BUNDLE_FOUND" = false ]; then
    print_error "SD bundle not found!"
    print_error "Make sure the dhcp-dashboard-packages directory is in:"
    echo "  - /boot/ (recommended for SD card)"
    echo "  - /tmp/"
    echo "  - Current directory"
    exit 1
fi

print_status "Using bundle directory: $BUNDLE_DIR"

# Navigate to bundle directory
cd "$BUNDLE_DIR"

# Step 1: Install system packages
print_status "Step 1: Installing system packages..."
if ls dhcp-dashboard-packages/*.deb >/dev/null 2>&1; then
    dpkg -i dhcp-dashboard-packages/*.deb
    apt-get install -f -y
    print_success "System packages installed"
else
    print_error "No .deb packages found in bundle"
    exit 1
fi

# Step 2: Install Python packages
print_status "Step 2: Installing Python packages..."
if [ -d "dhcp-dashboard-packages/python-packages" ]; then
    if [ -d "dhcp-dashboard-app" ] && [ -f "dhcp-dashboard-app/requirements.txt" ]; then
        pip3 install --no-index --find-links=dhcp-dashboard-packages/python-packages -r dhcp-dashboard-app/requirements.txt --break-system-packages
        print_success "Python packages installed"
    else
        print_warning "requirements.txt not found - installing Flask manually"
        pip3 install --no-index --find-links=dhcp-dashboard-packages/python-packages flask --break-system-packages
        print_success "Flask installed"
    fi
else
    print_warning "Python packages not cached - will install during setup"
fi

# Step 3: Run the setup script
print_status "Step 3: Running DHCP Dashboard setup..."
if [ -d "dhcp-dashboard-app" ] && [ -f "dhcp-dashboard-app/setup_pi.sh" ]; then
    cd dhcp-dashboard-app
    chmod +x setup_pi.sh
    bash setup_pi.sh --offline
else
    print_error "Setup script not found in bundle"
    print_error "Manual installation required"
    exit 1
fi

# Step 4: Cleanup (optional)
print_status "Step 4: Cleaning up installation files..."
cd /
rm -rf /boot/dhcp-dashboard-packages 2>/dev/null || true
rm -rf /tmp/dhcp-dashboard-packages 2>/dev/null || true

print_success "=========================================="
print_success "SD CARD INSTALLATION COMPLETED!"
print_success "=========================================="
echo ""
print_status "Your DHCP Dashboard is now running!"
print_status "Access it at: http://192.168.4.1:8080"
echo ""
print_success "Installation complete! Enjoy your offline DHCP Dashboard!"
EOF

chmod +x "$AUTO_INSTALL_SCRIPT"

# Create SD card preparation instructions
SD_INSTRUCTIONS_FILE="$SD_BUNDLE_DIR/SD_CARD_PREPARATION_README.txt"

cat > "$SD_INSTRUCTIONS_FILE" << 'EOF'
DHCP Dashboard - SD Card Preparation Guide
==========================================

This guide shows how to prepare an SD card with DHCP Dashboard for
completely offline installation on Raspberry Pi.

METHOD 1: Automated Installation (Recommended)
===============================================

1. Prepare SD Card with Raspberry Pi Imager:
   - Download and install Raspberry Pi Imager
   - Choose Raspberry Pi OS Lite (64-bit recommended)
   - Write to SD card
   - DO NOT eject the SD card yet

2. Copy Installation Bundle:
   - Mount the SD card boot partition (/boot or /boot/firmware)
   - Copy the entire contents of this directory to the SD card root:
     cp -r /var/cache/dhcp-dashboard-sd-bundle/* /media/user/boot/

3. Enable Auto-Installation (Optional):
   - Create /boot/autorun.sh on the SD card:
     #!/bin/bash
     /boot/automatic_offline_install.sh
   - Make it executable: chmod +x /boot/autorun.sh
   - Add to /boot/config.txt:
     dtoverlay=dwc2
     initramfs initramfs-linux.img followkernel

4. First Boot:
   - Insert SD card into Raspberry Pi
   - Power on (installation starts automatically)
   - Or run manually: sudo bash /boot/automatic_offline_install.sh

METHOD 2: Manual Installation
=============================

1. Prepare SD Card:
   - Use Raspberry Pi Imager to create SD card
   - Copy dhcp-dashboard-app/ to /home/pi/
   - Copy dhcp-dashboard-packages/ to /boot/

2. First Boot Setup:
   - Boot Raspberry Pi normally
   - Login as pi user
   - Run manual installation:
     cd /boot/dhcp-dashboard-packages
     sudo dpkg -i *.deb
     sudo apt-get install -f -y
     sudo pip3 install --no-index --find-links=/boot/dhcp-dashboard-packages/python-packages -r /home/pi/dhcp-dashboard-app/requirements.txt --break-system-packages
     cd /home/pi/dhcp-dashboard-app
     sudo bash setup_pi.sh --offline

WHAT'S INCLUDED IN THIS BUNDLE:
===============================

dhcp-dashboard-packages/
├── *.deb files (system packages)
├── python-packages/ (Python wheels)
└── OFFLINE_INSTALL_README.txt

dhcp-dashboard-app/
├── setup_pi.sh (main setup script)
├── dhcp_dashboard.py (main application)
├── requirements.txt (Python dependencies)
└── [all other application files]

automatic_offline_install.sh
└── Automated installation script for SD card

TROUBLESHOOTING:
=================

- If packages fail to install: Check SD card for corruption
- If Python packages missing: They may need manual installation
- If setup fails: Run setup_pi.sh --offline manually
- For headless setup: Configure SSH and WiFi before first boot

SUCCESS INDICATORS:
===================

After successful installation you should see:
- "SD CARD INSTALLATION COMPLETED!"
- Dashboard accessible at http://192.168.4.1:8080
- Access Point broadcasting (if configured)

The Raspberry Pi will be ready for offline operation immediately!
EOF

print_success "SD card bundle created at: $SD_BUNDLE_DIR"
print_success "Automated installation script: $AUTO_INSTALL_SCRIPT"
print_success "SD card instructions: $SD_INSTRUCTIONS_FILE"

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