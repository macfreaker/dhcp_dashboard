#!/bin/bash

################################################################################
# DHCP Host Diagnostic Script
# 
# This script investigates where DHCP hosts are actually stored
# and shows all potential host-related entries
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

DNSMASQ_CONF="/etc/dnsmasq.conf"

print_status "DHCP Host Diagnostic Script"
echo "=========================================="

# Check if dnsmasq.conf exists
if [ ! -f "$DNSMASQ_CONF" ]; then
    print_error "dnsmasq.conf not found at $DNSMASQ_CONF"
    exit 1
fi

print_status "File exists: $DNSMASQ_CONF"
print_status "File size: $(wc -c < "$DNSMASQ_CONF") bytes"
print_status "File lines: $(wc -l < "$DNSMASQ_CONF") lines"
echo ""

# Look for standard dhcp-host entries
print_status "Looking for standard dhcp-host= entries:"
grep -n "^dhcp-host=" "$DNSMASQ_CONF" 2>/dev/null || echo "  (none found)"
echo ""

# Look for any line containing dhcp-host
print_status "Looking for ANY line containing 'dhcp-host':"
grep -n "dhcp-host" "$DNSMASQ_CONF" 2>/dev/null || echo "  (none found)"
echo ""

# Look for any line containing MAC-like patterns
print_status "Looking for MAC address patterns (xx:xx:xx:xx:xx:xx):"
grep -n -E "[0-9a-fA-F]{1,2}:[0-9a-fA-F]{1,2}:[0-9a-fA-F]{1,2}:[0-9a-fA-F]{1,2}:[0-9a-fA-F]{1,2}:[0-9a-fA-F]{1,2}" "$DNSMASQ_CONF" 2>/dev/null || echo "  (none found)"
echo ""

# Look for any line containing common hostnames from your dashboard
print_status "Looking for specific hostnames seen in dashboard (fred, ignore, etc.):"
grep -n -E "(fred|ignore|bert|marjorie)" "$DNSMASQ_CONF" 2>/dev/null || echo "  (none found)"
echo ""

# Show the entire file if it's small enough
FILE_LINES=$(wc -l < "$DNSMASQ_CONF")
if [ "$FILE_LINES" -le 100 ]; then
    print_status "Full dnsmasq.conf content (file is small enough):"
    echo "----------------------------------------"
    cat -n "$DNSMASQ_CONF"
    echo "----------------------------------------"
else
    print_warning "File has $FILE_LINES lines - showing first 50 and last 50 lines:"
    echo "--- FIRST 50 LINES ---"
    head -50 "$DNSMASQ_CONF" | cat -n
    echo ""
    echo "--- LAST 50 LINES ---"
    tail -50 "$DNSMASQ_CONF" | cat -n
    echo "--- END OF FILE ---"
fi

echo ""
print_status "Diagnostic complete!"
print_warning "If no dhcp-host entries were found but dashboard shows hosts,"
print_warning "the hosts might be stored in a different file or database."