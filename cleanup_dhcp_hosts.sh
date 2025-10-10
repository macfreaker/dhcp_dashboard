#!/bin/bash

################################################################################
# DHCP Host Cleanup Script
# 
# This script removes ALL dhcp-host entries from dnsmasq.conf
# Use this to start with a completely empty DHCP host list
#
# Usage: sudo bash cleanup_dhcp_hosts.sh
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

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

DNSMASQ_CONF="/etc/dnsmasq.conf"

print_status "DHCP Host Cleanup Script"
echo ""

# Check if dnsmasq.conf exists
if [ ! -f "$DNSMASQ_CONF" ]; then
    print_error "dnsmasq.conf not found at $DNSMASQ_CONF"
    exit 1
fi

# Count current dhcp-host entries
CURRENT_COUNT=$(grep -c "^dhcp-host=" "$DNSMASQ_CONF" || echo "0")
print_status "Current DHCP host entries: $CURRENT_COUNT"

if [ "$CURRENT_COUNT" -eq 0 ]; then
    print_success "No DHCP host entries to remove - already clean!"
    exit 0
fi

# Create backup
BACKUP_FILE="${DNSMASQ_CONF}.backup_$(date +%Y%m%d_%H%M%S)"
cp "$DNSMASQ_CONF" "$BACKUP_FILE"
print_success "Created backup: $BACKUP_FILE"

# Stop dnsmasq
print_status "Stopping dnsmasq service..."
systemctl stop dnsmasq

# Remove all dhcp-host= lines
print_status "Removing all dhcp-host= entries..."
sed -i '/^dhcp-host=/d' "$DNSMASQ_CONF"

# Verify removal
REMAINING=$(grep -c "^dhcp-host=" "$DNSMASQ_CONF" || echo "0")

if [ "$REMAINING" -eq 0 ]; then
    print_success "Successfully removed all $CURRENT_COUNT DHCP host entries"
else
    print_error "Failed to remove all entries. $REMAINING entries remain."
    exit 1
fi

# Restart dnsmasq
print_status "Restarting dnsmasq with empty host list..."
if systemctl restart dnsmasq; then
    print_success "DNSMASQ restarted successfully"
else
    print_error "Failed to restart dnsmasq"
    print_status "You may need to check the configuration manually"
    exit 1
fi

# Restart dashboard if it's running
if systemctl is-active --quiet dhcp-dashboard; then
    print_status "Restarting DHCP Dashboard service..."
    systemctl restart dhcp-dashboard
    sleep 2
    print_success "Dashboard restarted"
fi

echo ""
print_success "=========================================="
print_success "CLEANUP COMPLETED SUCCESSFULLY!"
print_success "=========================================="
echo ""
echo -e "${GREEN}Result:${NC} DHCP host list is now EMPTY"
echo -e "${GREEN}Backup:${NC} $BACKUP_FILE"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "  1. Access dashboard to verify: http://$(hostname -I | awk '{print $1}'):8080"
echo -e "  2. Add new hosts through the web interface"
echo ""