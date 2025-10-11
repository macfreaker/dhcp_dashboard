#!/bin/bash

################################################################################
# Access Point Setup Diagnostic Script
# 
# This script checks all components needed for AP setup and identifies issues
################################################################################

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
echo "Access Point Setup Diagnostic"
echo "=========================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "This script should be run as root (use sudo)"
    exit 1
fi

# 1. Check required packages
print_status "Checking required packages..."
MISSING_PACKAGES=""

if ! command -v hostapd &> /dev/null; then
    print_error "hostapd not installed"
    MISSING_PACKAGES="$MISSING_PACKAGES hostapd"
else
    print_success "hostapd is installed"
fi

if ! command -v dnsmasq &> /dev/null; then
    print_error "dnsmasq not installed"
    MISSING_PACKAGES="$MISSING_PACKAGES dnsmasq"
else
    print_success "dnsmasq is installed"
fi

if [ ! -z "$MISSING_PACKAGES" ]; then
    print_warning "Missing packages. Install with:"
    echo "sudo apt-get update && sudo apt-get install$MISSING_PACKAGES"
fi

echo ""

# 2. Check wireless interfaces
print_status "Checking wireless interfaces..."
if iwconfig 2>/dev/null | grep -q "wlan0"; then
    print_success "wlan0 interface found"
    iwconfig wlan0 2>/dev/null | head -5
else
    print_error "wlan0 interface not found"
fi

if iwconfig 2>/dev/null | grep -q "wlan1"; then
    print_success "wlan1 interface found (good for dual Wi-Fi setup)"
    iwconfig wlan1 2>/dev/null | head -5
else
    print_warning "wlan1 interface not found (USB Wi-Fi adapter not connected?)"
fi

echo ""

# 3. Check configuration files
print_status "Checking configuration files..."

# Check hostapd.conf
if [ -f "/etc/hostapd/hostapd.conf" ]; then
    print_success "hostapd.conf exists"
    echo "Content:"
    cat "/etc/hostapd/hostapd.conf" | head -20
else
    print_warning "hostapd.conf not found"
fi

echo ""

# Check dhcpcd.conf
if [ -f "/etc/dhcpcd.conf" ]; then
    print_success "dhcpcd.conf exists"
    echo "Last 20 lines:"
    tail -20 "/etc/dhcpcd.conf"
else
    print_error "dhcpcd.conf not found"
fi

echo ""

# 4. Check service status
print_status "Checking service status..."

echo "hostapd service:"
systemctl status hostapd --no-pager -l || echo "Service not found"

echo ""
echo "dnsmasq service:"
systemctl status dnsmasq --no-pager -l || echo "Service not found"

echo ""
echo "dhcpcd service:"
systemctl status dhcpcd --no-pager -l || echo "Service not found"

echo ""

# 5. Check for conflicting processes
print_status "Checking for conflicting processes..."

if systemctl is-active --quiet NetworkManager; then
    print_warning "NetworkManager is running - this may conflict with hostapd"
    echo "Consider disabling: sudo systemctl disable NetworkManager"
fi

if systemctl is-active --quiet wpa_supplicant; then
    print_warning "wpa_supplicant is running on all interfaces"
    echo "You may need to configure it to avoid wlan0"
fi

echo ""

# 6. Check current network configuration
print_status "Current network configuration..."
echo "IP addresses:"
ip addr show | grep -E "(wlan|eth)" -A 2

echo ""
echo "Routing table:"
ip route

echo ""

# 7. Check for rfkill blocks
print_status "Checking for RF blocks..."
if command -v rfkill &> /dev/null; then
    rfkill list
else
    print_warning "rfkill not available"
fi

echo ""

# 8. Test hostapd configuration
print_status "Testing hostapd configuration..."
if [ -f "/etc/hostapd/hostapd.conf" ]; then
    echo "Testing hostapd config syntax..."
    hostapd -dd /etc/hostapd/hostapd.conf -t 2>&1 | head -10
else
    print_error "No hostapd.conf to test"
fi

echo ""
print_status "Diagnostic complete!"
print_warning "Look for any ERROR messages above to identify the issue."