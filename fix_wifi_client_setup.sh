#!/bin/bash

################################################################################
# Wi-Fi Client Setup Fix Script
# 
# This script addresses the wlan1 (USB Wi-Fi) connectivity issues
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
echo "Wi-Fi Client Setup Analysis & Fix"
echo "=========================================="

# Check current Wi-Fi interfaces
print_status "Checking available Wi-Fi interfaces..."
WLAN0_EXISTS=false
WLAN1_EXISTS=false

if iwconfig 2>/dev/null | grep -q "wlan0"; then
    WLAN0_EXISTS=true
    print_success "wlan0 found (built-in Wi-Fi)"
else
    print_error "wlan0 not found"
fi

if iwconfig 2>/dev/null | grep -q "wlan1"; then
    WLAN1_EXISTS=true
    print_success "wlan1 found (USB Wi-Fi adapter)"
else
    print_warning "wlan1 NOT found (no USB Wi-Fi adapter connected)"
fi

echo ""

if [ "$WLAN1_EXISTS" = false ]; then
    print_error "PROBLEM IDENTIFIED: No wlan1 interface available!"
    echo ""
    print_status "Your dashboard is configured for DUAL Wi-Fi setup:"
    echo "  - wlan0 = Access Point (broadcasting 'KraakMij')"
    echo "  - wlan1 = Wi-Fi Client (connecting to internet)"
    echo ""
    print_warning "But you only have wlan0 (built-in Wi-Fi)"
    echo ""
    print_status "SOLUTION OPTIONS:"
    echo ""
    echo "OPTION 1: Get USB Wi-Fi Adapter (Recommended)"
    echo "  - Buy a USB Wi-Fi dongle"
    echo "  - Plug it in to get wlan1"
    echo "  - Then wlan0=AP, wlan1=Client works perfectly"
    echo ""
    echo "OPTION 2: Use Ethernet + Wi-Fi AP"
    echo "  - Connect Ethernet cable for internet"
    echo "  - Use wlan0 only as Access Point"
    echo "  - No Wi-Fi client needed"
    echo ""
    echo "OPTION 3: Single Wi-Fi Mode (either AP OR client)"
    echo "  - Use wlan0 as AP only (no internet sharing)"
    echo "  - OR use wlan0 as client only (no AP)"
    echo ""
    
    read -p "Which option do you prefer? (1/2/3): " choice
    
    case $choice in
        1)
            print_status "Option 1 chosen: USB Wi-Fi Adapter"
            echo "Recommended USB Wi-Fi adapters:"
            echo "  - TP-Link AC600 T2U Plus"
            echo "  - Panda PAU09"
            echo "  - Any RTL8188CUS-based adapter"
            echo ""
            print_warning "After connecting USB adapter:"
            echo "  1. Reboot: sudo reboot"
            echo "  2. Run: iwconfig (should show wlan1)"
            echo "  3. Try Wi-Fi setup again in dashboard"
            ;;
        2)
            print_status "Option 2 chosen: Ethernet + Wi-Fi AP"
            print_status "Setting up Ethernet-based internet sharing..."
            
            # Modify iptables for eth0 instead of wlan1
            print_status "Configuring NAT for Ethernet internet sharing..."
            
            # Clear existing rules
            iptables -t nat -F
            iptables -F FORWARD
            
            # Set up NAT for eth0 (ethernet) to wlan0 (AP)
            iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
            iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
            iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT
            
            # Save rules
            sh -c "iptables-save > /etc/iptables.ipv4.nat"
            
            print_success "Ethernet internet sharing configured"
            print_warning "Connect Ethernet cable for internet access"
            print_success "Devices connecting to 'KraakMij' will have internet via Ethernet"
            ;;
        3)
            print_status "Option 3 chosen: Single Wi-Fi Mode"
            echo ""
            echo "Choose single Wi-Fi mode:"
            echo "  A) wlan0 as Access Point only (no internet)"
            echo "  B) wlan0 as Wi-Fi Client only (no AP)"
            echo ""
            read -p "Choose A or B: " mode
            
            if [[ "$mode" == "A" || "$mode" == "a" ]]; then
                print_status "Configuring wlan0 as AP-only (isolated network)..."
                
                # Clear NAT rules (no internet sharing)
                iptables -t nat -F
                iptables -F FORWARD
                
                # Disable IP forwarding
                echo 'net.ipv4.ip_forward=0' > /etc/sysctl.conf
                sysctl -p
                
                print_success "wlan0 configured as isolated Access Point"
                print_warning "Devices can connect to 'KraakMij' but won't have internet"
                
            elif [[ "$mode" == "B" || "$mode" == "b" ]]; then
                print_status "Configuring wlan0 as Wi-Fi Client only..."
                
                # Stop AP services
                systemctl stop hostapd
                systemctl disable hostapd
                
                # Enable wpa_supplicant on wlan0
                systemctl enable wpa_supplicant@wlan0
                
                print_success "wlan0 configured as Wi-Fi client"
                print_warning "You can now connect to other networks, but can't host AP"
                print_warning "Configure Wi-Fi via: sudo raspi-config"
            fi
            ;;
        *)
            print_error "Invalid choice. Please run script again."
            exit 1
            ;;
    esac
    
else
    print_success "wlan1 detected! Checking wlan1 configuration..."
    
    # Check if wlan1 is up
    if ip link show wlan1 | grep -q "state UP"; then
        print_success "wlan1 is up and ready"
    else
        print_status "Bringing up wlan1 interface..."
        ip link set wlan1 up
    fi
    
    # Test wlan1 scan capability
    print_status "Testing wlan1 Wi-Fi scanning..."
    if iw wlan1 scan | head -5 > /dev/null 2>&1; then
        print_success "wlan1 can scan for networks"
        print_status "Available networks:"
        iw wlan1 scan | grep "SSID:" | head -10
    else
        print_error "wlan1 cannot scan for networks"
        print_warning "Try: sudo modprobe -r rtl8192cu && sudo modprobe rtl8192cu"
    fi
    
    # Check wpa_supplicant configuration
    print_status "Checking wpa_supplicant for wlan1..."
    if systemctl is-active --quiet wpa_supplicant@wlan1; then
        print_success "wpa_supplicant is running on wlan1"
    else
        print_status "Starting wpa_supplicant on wlan1..."
        systemctl enable wpa_supplicant@wlan1
        systemctl start wpa_supplicant@wlan1
    fi
fi

echo ""
print_status "Analysis complete!"
echo "Choose your preferred setup and follow the instructions above."