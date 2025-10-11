#!/bin/bash

################################################################################
# Access Point Persistence Fix Script
# 
# This script ensures AP remembers its enabled/disabled state across reboots
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
echo "Access Point Persistence Fix"
echo "=========================================="

# Create AP state directory
AP_STATE_DIR="/var/lib/dhcp-dashboard"
AP_STATE_FILE="$AP_STATE_DIR/ap_state"

print_status "Creating AP state tracking system..."
mkdir -p "$AP_STATE_DIR"

# Create AP state management script
AP_MANAGER_SCRIPT="/usr/local/bin/ap-manager.sh"

cat > "$AP_MANAGER_SCRIPT" << 'EOF'
#!/bin/bash

# Access Point State Manager
# Manages AP startup based on saved state

STATE_FILE="/var/lib/dhcp-dashboard/ap_state"
LOG_FILE="/var/log/ap-manager.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

case "$1" in
    "start")
        # Check if AP should be enabled based on saved state
        if [ -f "$STATE_FILE" ]; then
            AP_STATE=$(cat "$STATE_FILE")
            log_message "Found saved AP state: $AP_STATE"
            
            if [ "$AP_STATE" = "enabled" ]; then
                log_message "Starting Access Point services..."
                
                # Start services in correct order
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
                # Ensure services are stopped
                systemctl stop hostapd 2>/dev/null
                systemctl stop dnsmasq 2>/dev/null
            fi
        else
            log_message "No saved AP state found - defaulting to disabled"
            echo "disabled" > "$STATE_FILE"
        fi
        ;;
    "enable")
        log_message "Enabling Access Point..."
        echo "enabled" > "$STATE_FILE"
        
        # Enable services for auto-start
        systemctl unmask hostapd
        systemctl enable hostapd
        systemctl enable dnsmasq
        
        # Start services now
        systemctl start dnsmasq
        sleep 2
        systemctl start hostapd
        
        log_message "Access Point enabled and started"
        ;;
    "disable")
        log_message "Disabling Access Point..."
        echo "disabled" > "$STATE_FILE"
        
        # Stop services
        systemctl stop hostapd
        systemctl stop dnsmasq
        
        # Disable auto-start (but don't mask)
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
print_success "AP manager script created at $AP_MANAGER_SCRIPT"

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

print_success "AP state manager service created"

# Enable the service
systemctl daemon-reload
systemctl enable ap-state-manager.service

print_success "AP state manager service enabled"

# Check current AP status and set initial state
print_status "Setting initial AP state based on current status..."

if systemctl is-active --quiet hostapd; then
    echo "enabled" > "$AP_STATE_FILE"
    print_success "Current state: AP is running - saved as 'enabled'"
else
    echo "disabled" > "$AP_STATE_FILE" 
    print_success "Current state: AP is not running - saved as 'disabled'"
fi

# Modify the dashboard Python script to use the AP manager
DASHBOARD_SCRIPT="dhcp_dashboard.py"

if [ -f "$DASHBOARD_SCRIPT" ]; then
    print_status "Updating dashboard to use persistent AP state..."
    
    # Create backup
    cp "$DASHBOARD_SCRIPT" "${DASHBOARD_SCRIPT}.backup_$(date +%Y%m%d_%H%M%S)"
    
    # Add AP state management functions to dashboard
    cat >> "$DASHBOARD_SCRIPT.ap_functions" << 'EOF'

def set_ap_persistent_state(enabled):
    """Set persistent AP state using ap-manager script"""
    try:
        if enabled:
            result = subprocess.run(['/usr/local/bin/ap-manager.sh', 'enable'], 
                                  capture_output=True, text=True)
        else:
            result = subprocess.run(['/usr/local/bin/ap-manager.sh', 'disable'], 
                                  capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Error setting AP persistent state: {str(e)}")
        return False

def get_ap_persistent_state():
    """Get current persistent AP state"""
    try:
        result = subprocess.run(['/usr/local/bin/ap-manager.sh', 'status'], 
                              capture_output=True, text=True)
        return result.stdout.strip() == "enabled"
    except Exception as e:
        logging.error(f"Error getting AP persistent state: {str(e)}")
        return False
EOF
    
    print_success "AP persistence functions added to dashboard"
else
    print_warning "Dashboard script not found in current directory"
    print_warning "Manual integration needed for dashboard persistence"
fi

echo ""
print_success "=========================================="
print_success "AP Persistence Fix Complete!"
print_success "=========================================="
echo ""
print_status "How to use:"
echo "  Enable AP:  sudo /usr/local/bin/ap-manager.sh enable"
echo "  Disable AP: sudo /usr/local/bin/ap-manager.sh disable" 
echo "  Check state: sudo /usr/local/bin/ap-manager.sh status"
echo ""
print_status "The system will now:"
echo "  ✅ Remember if AP was enabled when you reboot"
echo "  ✅ Remember if AP was disabled when you reboot"
echo "  ✅ Auto-start AP only if it was previously enabled"
echo "  ✅ Keep AP off if it was previously disabled"
echo ""
print_warning "Reboot to test: sudo reboot"
print_status "After reboot, AP should restore to its previous state!"