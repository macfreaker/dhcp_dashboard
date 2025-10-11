#!/bin/bash

################################################################################
# DHCP Dashboard - Raspberry Pi Setup Script
#
# This script performs complete installation and configuration of the DHCP
# Dashboard application with automatic startup on boot.
#
# USAGE MODES:
#   🌐 Online (default):    sudo bash setup_pi.sh
#                         - Downloads all packages automatically
#                         - Requires internet connection
#                         - Fully automated setup
#
#   📦 Offline:            sudo bash setup_pi.sh --offline
#                         - Uses pre-installed packages
#                         - No internet required
#                         - Requires package pre-loading (see README.md)
#
# For detailed instructions, see README.md Installation section.
################################################################################

set -e  # Exit on any error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
APP_FILE="dhcp_dashboard.py"
SERVICE_NAME="dhcp-dashboard"

################################################################################
# Helper Functions
################################################################################

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

################################################################################
# Installation Mode Selection and Prerequisites
################################################################################

echo "=========================================="
echo "DHCP Dashboard - Raspberry Pi Setup"
echo "=========================================="
echo ""

# Check for offline mode flag
OFFLINE_MODE=false
if [ "$1" = "--offline" ] || [ "$1" = "-o" ]; then
    OFFLINE_MODE=true
    echo -e "${YELLOW}📦 OFFLINE INSTALLATION MODE${NC}"
    echo -e "${BLUE}This mode assumes packages are pre-installed.${NC}"
    echo -e "${BLUE}Use 'sudo bash preload_packages.sh' on a connected system first.${NC}"
    echo ""
else
    echo -e "${GREEN}🌐 ONLINE INSTALLATION MODE${NC}"
    echo -e "${BLUE}This mode will download and install all required packages.${NC}"
    echo -e "${BLUE}Internet connection required.${NC}"
    echo ""
fi

print_status "Starting DHCP Dashboard installation..."
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

print_success "Prerequisites check passed"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3 first."
    exit 1
fi

print_success "Prerequisites check passed"
echo ""

################################################################################
# System Update and Upgrade (Skip in offline mode)
################################################################################

if [ "$OFFLINE_MODE" = false ]; then
    print_status "Updating package lists..."
    if apt-get update -qq; then
        print_success "Package lists updated"
    else
        print_warning "Failed to update package lists - continuing anyway"
    fi
    echo ""

    print_status "Upgrading installed packages (this may take a few minutes)..."
    if apt-get upgrade -y; then
        print_success "System packages upgraded"
    else
        print_warning "Failed to upgrade packages - continuing anyway"
    fi
    echo ""
else
    print_status "Skipping system updates (offline mode)"
    echo ""
fi

################################################################################
# Install Required Packages
################################################################################

if [ "$OFFLINE_MODE" = true ]; then
    print_status "🔍 OFFLINE MODE: Checking for pre-installed packages..."
else
    print_status "📦 ONLINE MODE: Installing required packages (dnsmasq, hostapd)..."
fi

# Install dnsmasq (DHCP/DNS server)
if ! dpkg -l | grep -q "^ii  dnsmasq "; then
    if [ "$OFFLINE_MODE" = true ]; then
        print_error "❌ dnsmasq not found!"
        print_error "OFFLINE MODE: Please pre-install dnsmasq:"
        echo "  On connected system: sudo apt-get update && sudo apt-get install -y dnsmasq"
        echo "  Then transfer packages using: sudo bash preload_packages.sh"
        exit 1
    else
        print_status "⬇️  Downloading and installing dnsmasq..."
        if apt-get install -y dnsmasq; then
            print_success "✅ dnsmasq installed successfully"
        else
            print_error "❌ Failed to install dnsmasq"
            exit 1
        fi
    fi
else
    print_success "✅ dnsmasq already installed"
fi

# Install hostapd (Access Point software)
if ! dpkg -l | grep -q "^ii  hostapd "; then
    if [ "$OFFLINE_MODE" = true ]; then
        print_error "❌ hostapd not found!"
        print_error "OFFLINE MODE: Please pre-install hostapd:"
        echo "  On connected system: sudo apt-get update && sudo apt-get install -y hostapd"
        echo "  Then transfer packages using: sudo bash preload_packages.sh"
        exit 1
    else
        print_status "⬇️  Downloading and installing hostapd..."
        if apt-get install -y hostapd; then
            print_success "✅ hostapd installed successfully"
        else
            print_error "❌ Failed to install hostapd"
            exit 1
        fi
    fi
else
    print_success "✅ hostapd already installed"
fi

# Install Python pip if not present
if ! command -v pip3 &> /dev/null; then
    if [ "$OFFLINE_MODE" = true ]; then
        print_error "❌ python3-pip not found!"
        print_error "OFFLINE MODE: Please pre-install python3-pip:"
        echo "  On connected system: sudo apt-get update && sudo apt-get install -y python3-pip"
        echo "  Then transfer packages using: sudo bash preload_packages.sh"
        exit 1
    else
        print_status "⬇️  Downloading and installing python3-pip..."
        if apt-get install -y python3-pip; then
            print_success "✅ python3-pip installed successfully"
        else
            print_error "❌ Failed to install python3-pip"
            exit 1
        fi
    fi
else
    print_success "✅ python3-pip already installed"
fi

echo ""

################################################################################
# Install Python Dependencies
################################################################################

if [ "$OFFLINE_MODE" = true ]; then
    print_status "🔍 OFFLINE MODE: Checking for pre-installed Python dependencies..."
else
    print_status "🐍 Installing Python dependencies..."
fi

cd "$APP_DIR"

if [ -f "requirements.txt" ]; then
    # Check if Flask is already installed (main dependency)
    if python3 -c "import flask" 2>/dev/null; then
        print_success "✅ Python dependencies already installed"
    else
        if [ "$OFFLINE_MODE" = true ]; then
            print_error "❌ Python dependencies not found!"
            print_error "OFFLINE MODE: Please pre-install Python dependencies:"
            echo "  pip3 install -r requirements.txt --break-system-packages"
            echo "  Or manually: pip3 install flask --break-system-packages"
            echo ""
            print_error "If using pre-loaded packages, try:"
            echo "  sudo pip3 install --no-index --find-links=/tmp/dhcp-dashboard-packages/python-packages -r requirements.txt --break-system-packages"
            exit 1
        else
            print_status "⬇️  Downloading and installing Python dependencies..."
            if pip3 install -r requirements.txt --break-system-packages; then
                print_success "✅ Python dependencies installed successfully"
            else
                print_error "❌ Failed to install Python dependencies"
                exit 1
            fi
        fi
    fi
else
    print_warning "⚠️  requirements.txt not found, checking for Flask..."
    if python3 -c "import flask" 2>/dev/null; then
        print_success "✅ Flask already installed"
    else
        if [ "$OFFLINE_MODE" = true ]; then
            print_error "❌ Flask not found!"
            print_error "OFFLINE MODE: Please pre-install Flask:"
            echo "  pip3 install flask --break-system-packages"
            exit 1
        else
            print_status "⬇️  Downloading and installing Flask..."
            if pip3 install flask --break-system-packages; then
                print_success "✅ Flask installed successfully"
            else
                print_error "❌ Failed to install Flask"
                exit 1
            fi
        fi
    fi
fi

echo ""

################################################################################
# Configure File Permissions
################################################################################

print_status "Setting up file permissions..."

# Ensure the app file is executable (not really needed for Python, but good practice)
chmod +x "$APP_DIR/$APP_FILE" 2>/dev/null || true

# Create log files with proper permissions
touch "$APP_DIR/dhcp_dashboard.log"
touch "$APP_DIR/connection_log.json"
chmod 644 "$APP_DIR/dhcp_dashboard.log"
chmod 644 "$APP_DIR/connection_log.json"

# Allow the application to run on port 8080 without sudo (if needed)
# Note: Ports below 1024 require root, but 8080 doesn't

print_success "File permissions configured"
echo ""

################################################################################
# Fix Access Point Setup Issues and Conflicts
################################################################################

print_status "Fixing Access Point setup issues and service conflicts..."

# 1. Unmask hostapd service (common issue)
print_status "Unmasking hostapd service..."
systemctl unmask hostapd 2>/dev/null || true

# 2. Stop and disable NetworkManager (conflicts with hostapd)
if systemctl is-active --quiet NetworkManager; then
    print_status "Disabling NetworkManager (conflicts with hostapd)..."
    systemctl stop NetworkManager 2>/dev/null || true
    systemctl disable NetworkManager 2>/dev/null || true
    print_success "NetworkManager disabled"
fi

# 3. Configure wpa_supplicant to avoid wlan0 conflicts
print_status "Configuring wpa_supplicant to avoid wlan0 conflicts..."
systemctl stop wpa_supplicant@wlan0 2>/dev/null || true
systemctl disable wpa_supplicant@wlan0 2>/dev/null || true

# Create wpa_supplicant override to use only wlan1 if it exists
WPA_SERVICE_DIR="/etc/systemd/system/wpa_supplicant.service.d"
mkdir -p "$WPA_SERVICE_DIR"
cat > "$WPA_SERVICE_DIR/override.conf" << 'EOF'
[Service]
ExecStart=
ExecStart=/sbin/wpa_supplicant -u -s -c /etc/wpa_supplicant/wpa_supplicant.conf -i wlan1
EOF

# 4. Stop conflicting services
print_status "Stopping services before configuration..."
systemctl stop hostapd 2>/dev/null || true
systemctl stop dnsmasq 2>/dev/null || true

print_success "Access Point conflicts resolved"
echo ""

################################################################################
# Clean DHCP Configuration (Start Fresh)
################################################################################

print_status "Cleaning existing DHCP host entries from dnsmasq.conf..."

# Backup current dnsmasq.conf before cleaning
if [ -f "/etc/dnsmasq.conf" ]; then
    BACKUP_FILE="/etc/dnsmasq.conf.backup_$(date +%Y%m%d_%H%M%S)"
    cp /etc/dnsmasq.conf "$BACKUP_FILE"
    print_success "Backed up existing config to: $BACKUP_FILE"
    
    # Count current dhcp-host entries (improved pattern matching)
    CURRENT_COUNT=$(grep -c -E "dhcp-host=" /etc/dnsmasq.conf 2>/dev/null || echo "0")
    CURRENT_COUNT=$(echo "$CURRENT_COUNT" | tr -d '\n\r' | head -1)
    
    if [ "$CURRENT_COUNT" -gt 0 ]; then
        print_status "Found $CURRENT_COUNT DHCP host entries to remove"
        
        # Remove ALL lines containing dhcp-host= (comprehensive cleanup)
        sed -i '/dhcp-host=/d' /etc/dnsmasq.conf
        
        # Verify cleanup with improved pattern matching
        REMAINING=$(grep -c -E "dhcp-host=" /etc/dnsmasq.conf 2>/dev/null || echo "0")
        REMAINING=$(echo "$REMAINING" | tr -d '\n\r' | head -1)
        
        if [ "$REMAINING" -eq 0 ]; then
            print_success "Successfully removed all $CURRENT_COUNT DHCP host entries"
        else
            print_warning "Found $REMAINING remaining dhcp-host entries"
            # Show remaining entries for debugging
            grep -n "dhcp-host=" /etc/dnsmasq.conf 2>/dev/null || true
        fi
    else
        print_success "No DHCP host entries found - starting clean"
    fi
    
    # Restart dnsmasq to apply clean configuration
    print_status "Restarting dnsmasq with clean configuration..."
    systemctl restart dnsmasq 2>/dev/null || true
    sleep 2
    print_success "DNSMASQ restarted with clean host list"
else
    print_warning "No existing dnsmasq.conf found - will be created when you configure AP"
fi

echo ""

################################################################################
# Create Systemd Service
################################################################################

print_status "Creating systemd service for auto-start on boot..."

# Create the systemd service file
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=DHCP Dashboard Web Application
After=network.target dnsmasq.service

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/python3 ${APP_DIR}/${APP_FILE}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

# Environment
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

print_success "Systemd service file created at /etc/systemd/system/${SERVICE_NAME}.service"
echo ""

################################################################################
# Enable and Start Service
################################################################################

print_status "Enabling ${SERVICE_NAME} service to start on boot..."

# Reload systemd to recognize new service
systemctl daemon-reload

# Enable the service (start on boot)
systemctl enable ${SERVICE_NAME}.service

print_success "Service enabled for automatic startup on boot"
echo ""

################################################################################
# Configure Sudoers (Allow Python Script to Run System Commands)
################################################################################

print_status "Configuring sudo permissions for the application..."

# Create a sudoers file that allows the application to run necessary commands without password
SUDOERS_FILE="/etc/sudoers.d/dhcp-dashboard"

cat > "$SUDOERS_FILE" << 'EOF'
# DHCP Dashboard - Allow necessary system commands without password
# This allows the Flask app to manage network services

# Allow all users to run systemctl commands for these services
ALL ALL=(ALL) NOPASSWD: /bin/systemctl restart dnsmasq
ALL ALL=(ALL) NOPASSWD: /bin/systemctl status dnsmasq
ALL ALL=(ALL) NOPASSWD: /bin/systemctl restart hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl status hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl is-active hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl is-enabled hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl stop hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl enable hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl disable hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl unmask hostapd
ALL ALL=(ALL) NOPASSWD: /bin/systemctl restart dhcpcd

# Allow network interface commands
ALL ALL=(ALL) NOPASSWD: /sbin/ifconfig wlan0 *
ALL ALL=(ALL) NOPASSWD: /sbin/wpa_cli *
ALL ALL=(ALL) NOPASSWD: /sbin/iw dev wlan0 *

# Allow iptables commands
ALL ALL=(ALL) NOPASSWD: /sbin/iptables *
ALL ALL=(ALL) NOPASSWD: /sbin/sysctl *

# Allow shutdown
ALL ALL=(ALL) NOPASSWD: /sbin/shutdown *

# Allow AP state manager
ALL ALL=(ALL) NOPASSWD: /usr/local/bin/ap-manager.sh *
EOF

# Set proper permissions on sudoers file
chmod 0440 "$SUDOERS_FILE"

# Validate the sudoers file
if visudo -c -f "$SUDOERS_FILE"; then
    print_success "Sudo permissions configured"
else
    print_error "Sudoers file validation failed"
    rm "$SUDOERS_FILE"
    exit 1
fi

echo ""

################################################################################
# Setup Access Point State Persistence System
################################################################################

print_status "Setting up Access Point state persistence system..."

# Create AP state directory
AP_STATE_DIR="/var/lib/dhcp-dashboard"
AP_STATE_FILE="$AP_STATE_DIR/ap_state"
mkdir -p "$AP_STATE_DIR"

# Create AP state management script
AP_MANAGER_SCRIPT="/usr/local/bin/ap-manager.sh"
cat > "$AP_MANAGER_SCRIPT" << 'EOF'
#!/bin/bash

# Access Point State Manager
STATE_FILE="/var/lib/dhcp-dashboard/ap_state"
LOG_FILE="/var/log/ap-manager.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

case "$1" in
    "start")
        if [ -f "$STATE_FILE" ]; then
            AP_STATE=$(cat "$STATE_FILE")
            log_message "Found saved AP state: $AP_STATE"
            
            if [ "$AP_STATE" = "enabled" ]; then
                log_message "Starting Access Point services..."
                systemctl start dnsmasq
                sleep 2
                systemctl start hostapd
                sleep 2
                
                if systemctl is-active --quiet hostapd && systemctl is-active --quiet dnsmasq; then
                    log_message "Access Point started successfully"
                else
                    log_message "ERROR: Failed to start Access Point"
                fi
            else
                log_message "AP state is disabled - not starting"
                systemctl stop hostapd 2>/dev/null || true
                systemctl stop dnsmasq 2>/dev/null || true
            fi
        else
            log_message "No saved AP state found - defaulting to disabled"
            echo "disabled" > "$STATE_FILE"
        fi
        ;;
    "enable")
        log_message "Enabling Access Point..."
        echo "enabled" > "$STATE_FILE"
        systemctl unmask hostapd
        systemctl enable hostapd
        systemctl enable dnsmasq
        systemctl start dnsmasq
        sleep 2
        systemctl start hostapd
        log_message "Access Point enabled and started"
        ;;
    "disable")
        log_message "Disabling Access Point..."
        echo "disabled" > "$STATE_FILE"
        systemctl stop hostapd
        systemctl stop dnsmasq
        systemctl disable hostapd
        log_message "Access Point disabled and stopped"
        ;;
    "status")
        if [ -f "$STATE_FILE" ]; then
            cat "$STATE_FILE"
        else
            echo "disabled"
        fi
        ;;
    *)
        echo "Usage: $0 {start|enable|disable|status}"
        exit 1
        ;;
esac
EOF

chmod +x "$AP_MANAGER_SCRIPT"

# Create systemd service for AP state management
AP_SERVICE_FILE="/etc/systemd/system/ap-state-manager.service"
cat > "$AP_SERVICE_FILE" << EOF
[Unit]
Description=Access Point State Manager
After=multi-user.target
Wants=network.target

[Service]
Type=oneshot
ExecStart=$AP_MANAGER_SCRIPT start
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Enable the AP state manager service
systemctl daemon-reload
systemctl enable ap-state-manager.service

# Set initial state as enabled (since we just configured AP)
echo "enabled" > "$AP_STATE_FILE"

# Enable and start the AP services immediately
print_status "Enabling Access Point services for immediate use..."
systemctl enable hostapd
systemctl enable dnsmasq

print_success "Access Point state persistence system configured (enabled by default)"
echo ""

################################################################################
# Configure Default hostapd Configuration with AP Credentials
################################################################################

print_status "Setting up hostapd configuration with default AP settings..."

# Create hostapd configuration directory
mkdir -p /etc/hostapd

# Prompt user for AP credentials or use defaults
echo ""
echo -e "${YELLOW}=========================================="
echo -e "Access Point Configuration"
echo -e "==========================================${NC}"
echo ""
echo -e "${BLUE}You can set up your Access Point credentials now, or press Enter to use defaults.${NC}"
echo ""

# Get SSID
read -p "Enter AP Name (SSID) [default: RaspberryPi-AP]: " AP_SSID
AP_SSID=${AP_SSID:-"RaspberryPi-AP"}

# Get Password
read -s -p "Enter AP Password (min 8 chars) [default: raspberry123]: " AP_PASSWORD
echo ""
AP_PASSWORD=${AP_PASSWORD:-"raspberry123"}

# Validate password length
while [ ${#AP_PASSWORD} -lt 8 ]; do
    echo ""
    print_warning "Password must be at least 8 characters long"
    read -s -p "Enter AP Password (min 8 chars): " AP_PASSWORD
    echo ""
done

echo ""
print_status "Creating hostapd configuration..."
print_status "AP Name (SSID): $AP_SSID"
print_status "AP Password: [hidden - ${#AP_PASSWORD} characters]"

# Create hostapd.conf with user settings
cat > /etc/hostapd/hostapd.conf << EOF
# Interface and driver
interface=wlan0
driver=nl80211

# Access Point settings
ssid=$AP_SSID
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0

# WPA settings
wpa=2
wpa_passphrase=$AP_PASSWORD
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP

# Country code (change if needed)
country_code=US
ieee80211n=1
ieee80211d=1
EOF

print_success "hostapd.conf created with custom settings"

# Update /etc/default/hostapd
HOSTAPD_DEFAULT="/etc/default/hostapd"
if [ -f "$HOSTAPD_DEFAULT" ]; then
    if grep -q "^DAEMON_CONF=" "$HOSTAPD_DEFAULT"; then
        sed -i 's|^DAEMON_CONF=.*|DAEMON_CONF="/etc/hostapd/hostapd.conf"|' "$HOSTAPD_DEFAULT"
    else
        echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' >> "$HOSTAPD_DEFAULT"
    fi
else
    echo 'DAEMON_CONF="/etc/hostapd/hostapd.conf"' > "$HOSTAPD_DEFAULT"
fi

print_success "hostapd default configuration updated"

# Configure network interfaces for AP
print_status "Configuring network interfaces for Access Point..."

# Configure dhcpcd for static IP on wlan0
if ! grep -q "interface wlan0" /etc/dhcpcd.conf; then
    cat >> /etc/dhcpcd.conf << 'EOF'

# Static IP for Access Point
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF
    print_success "dhcpcd configured for wlan0 static IP"
else
    print_success "dhcpcd already configured for wlan0"
fi

# Configure dnsmasq for DHCP
print_status "Configuring DHCP server..."
DNSMASQ_CONF="/etc/dnsmasq.conf"
if [ -f "$DNSMASQ_CONF" ]; then
    # Backup existing config
    cp "$DNSMASQ_CONF" "${DNSMASQ_CONF}.backup_$(date +%Y%m%d_%H%M%S)"
fi

# Add AP configuration if not present
if ! grep -q "interface=wlan0" "$DNSMASQ_CONF" 2>/dev/null; then
    cat >> "$DNSMASQ_CONF" << 'EOF'

# Access Point Configuration
interface=wlan0
dhcp-range=192.168.4.10,192.168.4.50,255.255.255.0,24h
bind-interfaces
server=8.8.8.8
domain-needed
bogus-priv
log-dhcp
EOF
    print_success "dnsmasq configured for Access Point"
else
    print_success "dnsmasq already configured"
fi

# Enable IP forwarding for internet sharing
print_status "Enabling IP forwarding for internet sharing..."
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo 'net.ipv4.ip_forward=1' >> /etc/sysctl.conf
fi
sysctl -p > /dev/null 2>&1

# Configure iptables for NAT
print_status "Setting up NAT routing..."
iptables -t nat -F POSTROUTING 2>/dev/null || true
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || true
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT 2>/dev/null || true

# Save iptables rules
sh -c "iptables-save > /etc/iptables.ipv4.nat" 2>/dev/null

# Add iptables restore to rc.local if not present
if [ -f /etc/rc.local ] && ! grep -q "iptables-restore" /etc/rc.local; then
    sed -i 's|^exit 0|iptables-restore < /etc/iptables.ipv4.nat\nexit 0|' /etc/rc.local
fi

print_success "Network configuration completed"
echo ""

################################################################################
# Start the Service
################################################################################

print_status "Starting ${SERVICE_NAME} service..."

# Start the service
systemctl start ${SERVICE_NAME}.service

# Wait a moment for service to start
sleep 3

# Check if service is running
if systemctl is-active --quiet ${SERVICE_NAME}.service; then
    print_success "Service started successfully!"
else
    print_error "Service failed to start. Check logs with: journalctl -u ${SERVICE_NAME}.service -n 50"
    exit 1
fi

echo ""

################################################################################
# Display Network Information
################################################################################

print_status "Getting network information..."

# Get the IP address of the Raspberry Pi
IP_ADDRESS=$(hostname -I | awk '{print $1}')

echo ""
if [ "$OFFLINE_MODE" = true ]; then
    print_success "=========================================="
    print_success "OFFLINE INSTALLATION COMPLETED!"
    print_success "=========================================="
    echo ""
    echo -e "${GREEN}📦 Installation Mode:${NC} Offline (Pre-loaded packages)"
else
    print_success "=========================================="
    print_success "ONLINE INSTALLATION COMPLETED!"
    print_success "=========================================="
    echo ""
    echo -e "${GREEN}🌐 Installation Mode:${NC} Online (Downloaded packages)"
fi
echo ""
echo -e "${GREEN}Dashboard URL:${NC} http://${IP_ADDRESS}:8080"
echo -e "${GREEN}or:${NC} http://$(hostname).local:8080"
echo ""
echo -e "${YELLOW}Service Management Commands:${NC}"
echo -e "  Start:   ${BLUE}sudo systemctl start ${SERVICE_NAME}${NC}"
echo -e "  Stop:    ${BLUE}sudo systemctl stop ${SERVICE_NAME}${NC}"
echo -e "  Restart: ${BLUE}sudo systemctl restart ${SERVICE_NAME}${NC}"
echo -e "  Status:  ${BLUE}sudo systemctl status ${SERVICE_NAME}${NC}"
echo -e "  Logs:    ${BLUE}sudo journalctl -u ${SERVICE_NAME} -f${NC}"
echo ""
echo -e "${YELLOW}Configuration Files:${NC}"
echo -e "  App Directory:     ${APP_DIR}"
echo -e "  Application Log:   ${APP_DIR}/dhcp_dashboard.log"
echo -e "  Connection Log:    ${APP_DIR}/connection_log.json"
echo -e "  DNSMASQ Config:    /etc/dnsmasq.conf"
echo -e "  Hostapd Config:    /etc/hostapd/hostapd.conf"
echo ""
echo -e "${YELLOW}Starting Access Point services...${NC}"

# Start networking services in correct order
print_status "Restarting networking services..."
systemctl daemon-reload

# Restart dhcpcd to apply new configuration
systemctl restart dhcpcd 2>/dev/null || true
sleep 2

# Start dnsmasq
systemctl restart dnsmasq
sleep 2

# Start hostapd
systemctl restart hostapd
sleep 3

# Check if AP services started successfully
AP_RUNNING=false
if systemctl is-active --quiet hostapd && systemctl is-active --quiet dnsmasq; then
    print_success "Access Point started successfully!"
    AP_RUNNING=true
else
    print_warning "Access Point services may need manual restart after reboot"
    print_warning "Use: sudo systemctl restart hostapd && sudo systemctl restart dnsmasq"
fi

echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo -e "  1. Access the dashboard at: ${BLUE}http://${IP_ADDRESS}:8080${NC}"
if [ "$AP_RUNNING" = true ]; then
    echo -e "  2. ${GREEN}Your Access Point is now running:${NC}"
    echo -e "     - SSID: ${BLUE}$AP_SSID${NC}"
    echo -e "     - Password: ${BLUE}[as configured]${NC}"
    echo -e "     - AP IP: ${BLUE}192.168.4.1${NC}"
    echo -e "  3. Connect devices to the Wi-Fi network"
    echo -e "  4. Access dashboard from connected devices at: ${BLUE}http://192.168.4.1:8080${NC}"
else
    echo -e "  2. Restart Access Point services if needed"
    echo -e "  3. Connect devices via Wi-Fi (once AP is running) or Ethernet"
fi
echo ""
print_success "The application and Access Point will automatically start on every boot!"
echo ""

################################################################################
# Final Status Check
################################################################################

print_status "Final system status:"
echo -e "  Dashboard service: $(systemctl is-active dhcp-dashboard || echo 'inactive')"
echo -e "  Access Point (hostapd): $(systemctl is-active hostapd || echo 'inactive')"
echo -e "  DHCP Server (dnsmasq): $(systemctl is-active dnsmasq || echo 'inactive')"
echo -e "  AP Persistence: $(cat /var/lib/dhcp-dashboard/ap_state 2>/dev/null || echo 'unknown')"
echo ""

print_success "Setup complete! Your DHCP Dashboard with Access Point is ready!"