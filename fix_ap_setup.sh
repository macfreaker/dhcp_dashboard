#!/bin/bash

################################################################################
# Access Point Setup Fix Script
# 
# This script fixes the identified AP setup issues
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

echo "=========================================="
echo "Access Point Setup Fix Script"
echo "=========================================="

print_status "Step 1: Unmask and enable hostapd service..."
systemctl unmask hostapd
systemctl enable hostapd
print_success "hostapd unmasked and enabled"

echo ""
print_status "Step 2: Stop conflicting services..."
systemctl stop NetworkManager
systemctl disable NetworkManager
print_success "NetworkManager stopped and disabled"

# Stop wpa_supplicant on wlan0 specifically
systemctl stop wpa_supplicant@wlan0 2>/dev/null || true
systemctl disable wpa_supplicant@wlan0 2>/dev/null || true
print_success "wpa_supplicant stopped on wlan0"

echo ""
print_status "Step 3: Configure wpa_supplicant to avoid wlan0..."

# Create wpa_supplicant config that excludes wlan0
WPA_SERVICE_FILE="/etc/systemd/system/wpa_supplicant.service.d/override.conf"
mkdir -p "$(dirname "$WPA_SERVICE_FILE")"

cat > "$WPA_SERVICE_FILE" << 'EOF'
[Service]
ExecStart=
ExecStart=/sbin/wpa_supplicant -u -s -c /etc/wpa_supplicant/wpa_supplicant.conf -i wlan1
EOF

print_success "wpa_supplicant configured to use only wlan1"

echo ""
print_status "Step 4: Update hostapd default configuration..."
HOSTAPD_DEFAULT="/etc/default/hostapd"
if [ -f "$HOSTAPD_DEFAULT" ]; then
    # Update or add DAEMON_CONF line
    if grep -q "^DAEMON_CONF=" "$HOSTAPD_DEFAULT"; then
        sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' "$HOSTAPD_DEFAULT"
    else
        echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >> "$HOSTAPD_DEFAULT"
    fi
else
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > "$HOSTAPD_DEFAULT"
fi
print_success "hostapd default configuration updated"

echo ""
print_status "Step 5: Configure dnsmasq for AP..."

# Backup dnsmasq.conf
cp /etc/dnsmasq.conf /etc/dnsmasq.conf.backup_$(date +%Y%m%d_%H%M%S)

# Add AP-specific configuration to dnsmasq
if ! grep -q "interface=wlan0" /etc/dnsmasq.conf; then
    cat >> /etc/dnsmasq.conf << 'EOF'

# Access Point Configuration
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,24h
bind-interfaces
server=8.8.8.8
domain-needed
bogus-priv
EOF
    print_success "dnsmasq configured for AP"
else
    print_success "dnsmasq already configured for AP"
fi

echo ""
print_status "Step 6: Set up IP forwarding and routing..."

# Enable IP forwarding
echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
sysctl -p

# Configure iptables for NAT (if eth0 has internet)
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT

# Save iptables rules
sh -c "iptables-save > /etc/iptables.ipv4.nat"

# Add iptables restore to rc.local
if ! grep -q "iptables-restore" /etc/rc.local; then
    sed -i 's|^exit 0|iptables-restore < /etc/iptables.ipv4.nat\nexit 0|' /etc/rc.local
fi

print_success "IP forwarding and NAT configured"

echo ""
print_status "Step 7: Fix network interface configuration..."

# Ensure correct dhcpcd configuration
if ! grep -q "interface wlan0" /etc/dhcpcd.conf; then
    cat >> /etc/dhcpcd.conf << 'EOF'

# Static IP for Access Point
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF
    print_success "dhcpcd configured for wlan0"
else
    print_success "dhcpcd already configured"
fi

echo ""
print_status "Step 8: Restart services in correct order..."

# Restart networking
systemctl daemon-reload

# Start dhcpcd (or systemd-networkd)
if systemctl list-unit-files | grep -q dhcpcd; then
    systemctl restart dhcpcd
else
    systemctl restart systemd-networkd
fi

sleep 2

# Start dnsmasq
systemctl restart dnsmasq
sleep 2

# Start hostapd
systemctl restart hostapd
sleep 3

echo ""
print_status "Step 9: Checking final status..."

echo "hostapd status:"
if systemctl is-active --quiet hostapd; then
    print_success "hostapd is running"
else
    print_error "hostapd failed to start"
    systemctl status hostapd --no-pager -l
fi

echo ""
echo "dnsmasq status:"
if systemctl is-active --quiet dnsmasq; then
    print_success "dnsmasq is running"
else
    print_error "dnsmasq failed to start"
fi

echo ""
echo "wlan0 interface status:"
ip addr show wlan0

echo ""
print_success "=========================================="
print_success "Access Point Setup Fix Complete!"
print_success "=========================================="
echo ""
echo "Your AP should now be broadcasting: KraakMij"
echo "Password: Goose1966@"
echo "AP IP: 192.168.4.1"
echo ""
print_warning "If still having issues, reboot the Pi and try again:"
print_warning "sudo reboot"