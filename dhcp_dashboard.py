import flask
from flask import Flask, request, render_template_string, flash, redirect, url_for, jsonify, send_file
from flask_restx import Api, Resource, fields, Namespace
import subprocess
import re
import shutil
from datetime import datetime, timedelta
import logging
import os
import time
import json
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a real secret key

# Initialize Flask-RESTX for Swagger documentation
api = Api(app, version='1.0', title='DHCP Dashboard API',
    description='RESTful API for managing DHCP/DNS and Access Point on Raspberry Pi',
    doc='/api/docs',  # Swagger UI will be available at this endpoint
    prefix='/api'
)

# Create namespaces for organizing API endpoints
ns_hosts = api.namespace('hosts', description='DHCP host management operations')
ns_ap = api.namespace('ap', description='Access Point configuration and management')
ns_connections = api.namespace('connections', description='Connection tracking and monitoring')
ns_logs = api.namespace('logs', description='Application log management')
# API Models for Swagger documentation
host_model = api.model('Host', {
    'mac': fields.String(required=True, description='MAC address (format: aa:bb:cc:dd:ee:ff)', example='00:11:22:33:44:55'),
    'hostname': fields.String(required=True, description='Device hostname', example='laptop'),
    'ip': fields.String(required=False, description='Static IP address (optional)', example='192.168.4.50')
})

ap_config_model = api.model('AccessPointConfig', {
    'ssid': fields.String(required=True, description='Access Point SSID', example='MyLabNetwork'),
    'password': fields.String(required=True, description='WPA2 password (min 8 characters)', example='securepass123'),
    'channel': fields.String(required=False, description='Wi-Fi channel', example='6'),
    'hw_mode': fields.String(required=False, description='Hardware mode (a/b/g/n)', example='g'),
    'country': fields.String(required=False, description='Country code', example='BE')
})

connection_model = api.model('Connection', {
    'timestamp': fields.String(description='ISO 8601 timestamp', example='2024-01-15T10:30:00'),
    'event': fields.String(description='Event type', enum=['connect', 'disconnect']),
    'mac': fields.String(description='MAC address', example='aa:bb:cc:dd:ee:ff'),
    'ip': fields.String(description='IP address', example='192.168.4.15'),
    'hostname': fields.String(description='Device hostname', example='laptop'),
    'interface': fields.String(description='Network interface', enum=['wlan0', 'eth0'])
})


DNSMASQ_CONF = '/etc/dnsmasq.conf'
WPA_SUPPLICANT_CONF = '/etc/wpa_supplicant/wpa_supplicant.conf'
HOSTAPD_CONF = '/etc/hostapd/hostapd.conf'
DHCPCD_CONF = '/etc/dhcpcd.conf'
LOG_FILE = 'dhcp_dashboard.log'
CONNECTION_LOG_FILE = 'connection_log.json'
DHCP_SCRIPT = '/usr/local/bin/dhcp-event.sh'

# Connection tracking
connection_history = []

def load_connection_history():
    """Load connection history from JSON file"""
    global connection_history
    try:
        if os.path.exists(CONNECTION_LOG_FILE):
            with open(CONNECTION_LOG_FILE, 'r') as f:
                connection_history = json.load(f)
        logging.info(f"Loaded {len(connection_history)} connection records")
    except Exception as e:
        logging.error(f"Error loading connection history: {str(e)}")
        connection_history = []

def save_connection_history():
    """Save connection history to JSON file"""
    try:
        with open(CONNECTION_LOG_FILE, 'w') as f:
            json.dump(connection_history, f, indent=2)
        logging.info(f"Saved {len(connection_history)} connection records")
    except Exception as e:
        logging.error(f"Error saving connection history: {str(e)}")

def log_connection_event(event_type, mac, ip, hostname=None, interface='unknown'):
    """Log a connection or disconnection event"""
    try:
        timestamp = datetime.now().isoformat()
        event = {
            'timestamp': timestamp,
            'event': event_type,  # 'connect' or 'disconnect'
            'mac': mac,
            'ip': ip,
            'hostname': hostname or 'Unknown',
            'interface': interface  # 'wlan0' or 'eth0'
        }

        connection_history.append(event)
        save_connection_history()

        # Enhanced logging with more details
        event_emoji = "🔌" if event_type == 'connect' else "🔌❌"
        logging.info(f"{event_emoji} CONNECTION EVENT: {event_type.upper()} - MAC:{mac} IP:{ip} Host:{hostname} Interface:{interface} Time:{timestamp}")
        logging.info(f"Total connection history: {len(connection_history)} events")

        # Also log to a separate connection log file for easier monitoring
        try:
            with open('connection_events.log', 'a') as f:
                f.write(f"{timestamp} | {event_type.upper()} | {mac} | {ip} | {hostname} | {interface}\n")
        except Exception as log_e:
            logging.warning(f"Could not write to connection_events.log: {log_e}")

    except Exception as e:
        logging.error(f"Error logging connection event: {str(e)}")

def parse_dnsmasq_leases():
    """Parse dnsmasq leases file to get current connections"""
    leases = []
    lease_file = '/var/lib/misc/dnsmasq.leases'
    try:
        if os.path.exists(lease_file):
            with open(lease_file, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        lease = {
                            'expiry': parts[0],
                            'mac': parts[1],
                            'ip': parts[2],
                            'hostname': parts[3] if len(parts) > 3 else 'Unknown',
                            'client_id': parts[4] if len(parts) > 4 else ''
                        }
                        leases.append(lease)
    except Exception as e:
        logging.error(f"Error parsing dnsmasq leases: {str(e)}")
    return leases

def get_active_connections():
    """Get currently active connections from dnsmasq leases"""
    leases = parse_dnsmasq_leases()
    active = []
    
    for lease in leases:
        # Check if lease is still valid (expiry timestamp in future)
        try:
            expiry_ts = int(lease['expiry'])
            current_ts = int(time.time())
            if expiry_ts > current_ts:
                active.append(lease)
        except:
            # If we can't parse expiry, assume it's active
            active.append(lease)
    
    return active

def monitor_connections():
    """Monitor for new connections and disconnections"""
    try:
        # Get current active leases
        current_leases = parse_dnsmasq_leases()
        current_macs = {lease['mac']: lease for lease in current_leases}
        
        # Get previously known connections from last 5 minutes
        recent_threshold = (datetime.now() - timedelta(minutes=5)).isoformat()
        recent_connections = [
            event for event in connection_history[-100:]  # Check last 100 events
            if event['timestamp'] > recent_threshold and event['event'] == 'connect'
        ]
        recent_macs = {event['mac'] for event in recent_connections}
        
        # Check for new connections
        for mac, lease in current_macs.items():
            if mac not in recent_macs:
                # Determine interface based on IP range or other factors
                interface = 'wlan0' if lease['ip'].startswith('192.168.4.') else 'eth0'
                log_connection_event('connect', mac, lease['ip'], lease['hostname'], interface)
        
        # Check for disconnections (MACs that were recently connected but not in current leases)
        for mac in recent_macs:
            if mac not in current_macs:
                # Find the last connection event for this MAC
                for event in reversed(connection_history):
                    if event['mac'] == mac and event['event'] == 'connect':
                        log_connection_event('disconnect', mac, event['ip'], event['hostname'], event['interface'])
                        break
                        
    except Exception as e:
        logging.error(f"Error monitoring connections: {str(e)}")

logging.basicConfig(filename='dhcp_dashboard.log', level=logging.DEBUG)


def read_dhcp_hosts():
    try:
        with open(DNSMASQ_CONF, 'r') as f:
            content = f.read()
        hosts = re.findall(r'dhcp-host=([\w:]+),([\w.-]+)(?:,([\d.]+))?', content)
        logging.info(f"Read {len(hosts)} hosts from configuration")
        return hosts
    except Exception as e:
        logging.error(f"Error reading DHCP hosts: {str(e)}")
        return []


def write_dhcp_hosts(hosts):
    try:
        with open(DNSMASQ_CONF, 'r') as f:
            content = f.readlines()

        # Remove all existing dhcp-host lines
        new_content = [line for line in content if not line.startswith('dhcp-host=')]
        
        # Check for duplicate IPs before writing
        seen_ips = set()
        seen_macs = set()
        seen_hostnames = set()
        deduplicated_hosts = []
        
        for mac, hostname, ip in hosts:
            # Skip if MAC already seen
            if mac in seen_macs:
                logging.warning(f"Skipping duplicate MAC address: {mac}")
                continue
            
            # Skip if hostname already seen
            if hostname in seen_hostnames:
                logging.warning(f"Skipping duplicate hostname: {hostname}")
                continue
            
            # Skip if IP already seen (and IP is not None/empty)
            if ip and ip in seen_ips:
                logging.warning(f"Skipping duplicate IP address: {ip}")
                continue
            
            # Add to tracking sets
            seen_macs.add(mac)
            seen_hostnames.add(hostname)
            if ip:
                seen_ips.add(ip)
            
            deduplicated_hosts.append((mac, hostname, ip))
        
        # Write deduplicated hosts
        for mac, hostname, ip in deduplicated_hosts:
            if ip:
                new_content.append(f'dhcp-host={mac},{hostname},{ip}\n')
            else:
                new_content.append(f'dhcp-host={mac},{hostname}\n')

        with open(DNSMASQ_CONF, 'w') as f:
            f.writelines(new_content)

        logging.info(f"Wrote {len(deduplicated_hosts)} hosts to configuration (removed {len(hosts) - len(deduplicated_hosts)} duplicates)")
    except Exception as e:
        logging.error(f"Error writing DHCP hosts: {str(e)}")
        raise


def restart_dnsmasq():
    try:
        result = subprocess.run(['sudo', 'systemctl', 'restart', 'dnsmasq'], capture_output=True, text=True)
        if result.returncode != 0:
            status_output = get_dnsmasq_status()
            logging.error(f"Error restarting DNSMASQ: {result.stderr}\nStatus: {status_output}")
            raise Exception(f"Failed to restart DNSMASQ. Status: {status_output}")
        logging.info("DNSMASQ restarted successfully")
    except Exception as e:
        logging.error(f"Exception when restarting DNSMASQ: {str(e)}")
        raise


def get_dnsmasq_status():
    try:
        result = subprocess.run(['sudo', 'systemctl', 'status', 'dnsmasq'], capture_output=True, text=True)
        return result.stdout
    except Exception as e:
        logging.error(f"Error getting DNSMASQ status: {str(e)}")
        return "Unable to get DNSMASQ status"


def backup_dnsmasq_conf():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"{DNSMASQ_CONF}.backup_{timestamp}"
        shutil.copy2(DNSMASQ_CONF, backup_file)
        logging.info(f"Backup created: {backup_file}")
        return backup_file
    except Exception as e:
        logging.error(f"Error creating backup: {str(e)}")
        raise


def shutdown_pi():
    os.system("sudo shutdown -h now")


def update_wifi_settings(ssid, password):
    """Configure wlan1 as Wi-Fi client (wlan0 is reserved for Access Point)"""
    try:
        wpa_config = f'''
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=BE

network={{
    ssid="{ssid}"
    psk="{password}"
}}
'''
        with open(WPA_SUPPLICANT_CONF, 'w') as f:
            f.write(wpa_config)

        # Restart wlan1 (USB Wi-Fi adapter for client connection)
        subprocess.run(['sudo', 'ifconfig', 'wlan1', 'down'], check=True)
        time.sleep(1)
        subprocess.run(['sudo', 'ifconfig', 'wlan1', 'up'], check=True)
        time.sleep(2)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan1', 'reconfigure'], check=True)

        # Wait for the connection to be established on wlan1
        for _ in range(30):  # Wait up to 30 seconds
            result = subprocess.run(['iwgetid', 'wlan1', '-r'], capture_output=True, text=True)
            if result.stdout.strip() == ssid:
                logging.info(f"Successfully connected to Wi-Fi network: {ssid} on wlan1")
                return True
            time.sleep(1)

        logging.error(f"Failed to connect to Wi-Fi network: {ssid} on wlan1")
        return False
    except Exception as e:
        logging.error(f"Error updating Wi-Fi settings on wlan1: {str(e)}")
        return False


def read_ap_config():
    """Read current access point configuration from hostapd.conf"""
    try:
        config = {
            'ssid': '',
            'password': '',
            'channel': '6',
            'hw_mode': 'g',
            'country': 'BE',
            'enabled': False
        }
        
        if os.path.exists(HOSTAPD_CONF):
            with open(HOSTAPD_CONF, 'r') as f:
                content = f.read()
                ssid_match = re.search(r'ssid=(.+)', content)
                if ssid_match:
                    config['ssid'] = ssid_match.group(1)
                password_match = re.search(r'wpa_passphrase=(.+)', content)
                if password_match:
                    config['password'] = password_match.group(1)
                channel_match = re.search(r'channel=(\d+)', content)
                if channel_match:
                    config['channel'] = channel_match.group(1)
                hw_mode_match = re.search(r'hw_mode=(.)', content)
                if hw_mode_match:
                    config['hw_mode'] = hw_mode_match.group(1)
                country_match = re.search(r'country_code=(.+)', content)
                if country_match:
                    config['country'] = country_match.group(1)
            
            # Check if hostapd service is enabled
            result = subprocess.run(['sudo', 'systemctl', 'is-enabled', 'hostapd'],
                                  capture_output=True, text=True)
            config['enabled'] = result.returncode == 0
        
        return config
    except Exception as e:
        logging.error(f"Error reading AP config: {str(e)}")
        return config


def configure_access_point(ssid, password, channel='6', hw_mode='g', country='BE'):
    """Configure the Raspberry Pi as a wireless access point"""
    try:
        # Create hostapd configuration
        hostapd_config = f'''interface=wlan0
driver=nl80211
ssid={ssid}
hw_mode={hw_mode}
channel={channel}
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
country_code={country}
'''
        
        # Write hostapd configuration
        with open(HOSTAPD_CONF, 'w') as f:
            f.write(hostapd_config)
        
        # Update /etc/default/hostapd to point to config
        default_hostapd = '/etc/default/hostapd'
        if os.path.exists(default_hostapd):
            with open(default_hostapd, 'r') as f:
                lines = f.readlines()
            
            with open(default_hostapd, 'w') as f:
                found = False
                for line in lines:
                    if line.startswith('#DAEMON_CONF=') or line.startswith('DAEMON_CONF='):
                        f.write(f'DAEMON_CONF="{HOSTAPD_CONF}"\n')
                        found = True
                    else:
                        f.write(line)
                if not found:
                    f.write(f'DAEMON_CONF="{HOSTAPD_CONF}"\n')
        
        logging.info(f"Configured access point: {ssid}")
        return True
    except Exception as e:
        logging.error(f"Error configuring access point: {str(e)}")
        return False


def configure_network_interfaces():
    """Configure network interfaces - wlan0 for AP, wlan1 for Wi-Fi client, eth0 for local network"""
    try:
        # Configure dhcpcd for dual Wi-Fi adapter setup
        dhcpcd_config = '''
# Local Network Configuration
# wlan0 = Access Point (static IP)
# wlan1 = Wi-Fi Client (DHCP or will be configured separately)
# eth0 = Wired/Switch connection (static IP)

# Static IP configuration for wlan0 (Wireless Access Point)
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant

# Static IP configuration for eth0 (Wired/Switch connection)
interface eth0
    static ip_address=192.168.4.1/24

# wlan1 (USB Wi-Fi adapter) - Wi-Fi Client mode (uses wpa_supplicant)
# Gets IP via DHCP from the network it connects to
interface wlan1
    # DHCP client - automatically configured
'''
        
        # Backup existing dhcpcd.conf
        if os.path.exists(DHCPCD_CONF):
            backup_file = f"{DHCPCD_CONF}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(DHCPCD_CONF, backup_file)
            logging.info(f"Backed up dhcpcd.conf to {backup_file}")
        
        # Read existing dhcpcd.conf and remove old wlan0/wlan1/eth0 configurations
        existing_lines = []
        if os.path.exists(DHCPCD_CONF):
            with open(DHCPCD_CONF, 'r') as f:
                skip = False
                for line in f:
                    if (line.strip().startswith('interface wlan0') or
                        line.strip().startswith('interface wlan1') or
                        line.strip().startswith('interface eth0')):
                        skip = True
                        continue
                    if skip and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                        skip = False
                    if not skip:
                        existing_lines.append(line)
        
        # Write updated configuration
        with open(DHCPCD_CONF, 'w') as f:
            f.writelines(existing_lines)
            f.write(dhcpcd_config)
        
        logging.info("Configured network interfaces for AP mode")
        return True
    except Exception as e:
        logging.error(f"Error configuring network interfaces: {str(e)}")
        return False


def configure_dnsmasq_for_ap():
    """Configure dnsmasq for unified local network (wlan0 + eth0)"""
    try:
        # Backup current dnsmasq configuration
        backup_dnsmasq_conf()
        
        # Read existing configuration
        with open(DNSMASQ_CONF, 'r') as f:
            lines = f.readlines()
        
        # Remove old interface and dhcp-range settings
        new_lines = []
        for line in lines:
            if not (line.startswith('interface=') or
                   line.startswith('dhcp-range=') or
                   line.startswith('bind-interfaces') or
                   line.startswith('server=') or
                   line.startswith('domain-needed') or
                   line.startswith('bogus-priv') or
                   line.startswith('listen-address=')):
                new_lines.append(line)
        
        # Add unified network configuration
        ap_config = '''# Unified Local Network Configuration
# Listen on both wireless (wlan0) and wired (eth0) interfaces
interface=wlan0
interface=eth0
bind-interfaces
listen-address=192.168.4.1
server=8.8.8.8
server=8.8.4.4
domain-needed
bogus-priv
# DHCP range for all devices (wireless + wired)
dhcp-range=192.168.4.10,192.168.4.250,255.255.255.0,24h
# Enable DHCP logging
log-dhcp
log-queries

'''
        
        # Write updated configuration
        with open(DNSMASQ_CONF, 'w') as f:
            f.write(ap_config)
            f.writelines(new_lines)
        
        logging.info("Configured dnsmasq for AP mode")
        return True
    except Exception as e:
        logging.error(f"Error configuring dnsmasq for AP: {str(e)}")
        return False


def enable_internet_sharing():
    """Enable internet sharing from wlan1 to local network (wlan0 + eth0)"""
    try:
        # Enable IP forwarding
        with open('/etc/sysctl.conf', 'r') as f:
            lines = f.readlines()
        
        with open('/etc/sysctl.conf', 'w') as f:
            found = False
            for line in lines:
                if 'net.ipv4.ip_forward' in line:
                    f.write('net.ipv4.ip_forward=1\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write('\nnet.ipv4.ip_forward=1\n')
        
        # Apply sysctl changes
        subprocess.run(['sudo', 'sysctl', '-p'], check=True)
        
        # Configure iptables for NAT (share internet from wlan1 to local network)
        # Clear existing rules first
        subprocess.run(['sudo', 'iptables', '-t', 'nat', '-F'], capture_output=True)
        subprocess.run(['sudo', 'iptables', '-F', 'FORWARD'], capture_output=True)
        
        # Enable NAT from wlan1
        subprocess.run(['sudo', 'iptables', '-t', 'nat', '-A', 'POSTROUTING', '-o', 'wlan1', '-j', 'MASQUERADE'],
                      capture_output=True)
        
        # Allow forwarding between interfaces
        subprocess.run(['sudo', 'iptables', '-A', 'FORWARD', '-i', 'wlan1', '-o', 'wlan0', '-m', 'state',
                       '--state', 'RELATED,ESTABLISHED', '-j', 'ACCEPT'], capture_output=True)
        subprocess.run(['sudo', 'iptables', '-A', 'FORWARD', '-i', 'wlan0', '-o', 'wlan1', '-j', 'ACCEPT'],
                      capture_output=True)
        subprocess.run(['sudo', 'iptables', '-A', 'FORWARD', '-i', 'wlan1', '-o', 'eth0', '-m', 'state',
                       '--state', 'RELATED,ESTABLISHED', '-j', 'ACCEPT'], capture_output=True)
        subprocess.run(['sudo', 'iptables', '-A', 'FORWARD', '-i', 'eth0', '-o', 'wlan1', '-j', 'ACCEPT'],
                      capture_output=True)
        
        # Save iptables rules
        subprocess.run(['sudo', 'sh', '-c', 'iptables-save > /etc/iptables.ipv4.nat'],
                      capture_output=True)
        
        logging.info("Internet sharing enabled (wlan1 → wlan0 + eth0)")
        return True
    except Exception as e:
        logging.error(f"Error enabling internet sharing: {str(e)}")
        return False


def disable_internet_sharing():
    """Disable internet sharing - isolate local network"""
    try:
        # Disable IP forwarding
        with open('/etc/sysctl.conf', 'r') as f:
            lines = f.readlines()
        
        with open('/etc/sysctl.conf', 'w') as f:
            found = False
            for line in lines:
                if 'net.ipv4.ip_forward' in line:
                    f.write('net.ipv4.ip_forward=0\n')
                    found = True
                else:
                    f.write(line)
            if not found:
                f.write('\nnet.ipv4.ip_forward=0\n')
        
        # Apply sysctl changes
        subprocess.run(['sudo', 'sysctl', '-p'], check=True)
        
        # Clear NAT rules
        subprocess.run(['sudo', 'iptables', '-t', 'nat', '-F'], capture_output=True)
        subprocess.run(['sudo', 'iptables', '-F', 'FORWARD'], capture_output=True)
        
        # Remove saved rules
        if os.path.exists('/etc/iptables.ipv4.nat'):
            os.remove('/etc/iptables.ipv4.nat')
        
        logging.info("Internet sharing disabled - local network isolated")
        return True
    except Exception as e:
        logging.error(f"Error disabling internet sharing: {str(e)}")
        return False


def get_internet_sharing_status():
    """Check if internet sharing is currently enabled"""
    try:
        # Check IP forwarding status
        result = subprocess.run(['sysctl', 'net.ipv4.ip_forward'], capture_output=True, text=True)
        ip_forward_enabled = 'net.ipv4.ip_forward = 1' in result.stdout
        
        # Check if NAT rules exist
        result = subprocess.run(['sudo', 'iptables', '-t', 'nat', '-L', 'POSTROUTING'],
                              capture_output=True, text=True)
        nat_configured = 'MASQUERADE' in result.stdout and 'wlan1' in result.stdout
        
        return {
            'enabled': ip_forward_enabled and nat_configured,
            'ip_forward': ip_forward_enabled,
            'nat_rules': nat_configured
        }
    except Exception as e:
        logging.error(f"Error getting internet sharing status: {str(e)}")
        return {'enabled': False, 'ip_forward': False, 'nat_rules': False}


def enable_ip_forwarding():
    """Wrapper for backward compatibility - disables internet sharing by default"""
    return disable_internet_sharing()


def start_access_point():
    """Start the access point services"""
    try:
        # Unmask and enable hostapd
        subprocess.run(['sudo', 'systemctl', 'unmask', 'hostapd'], capture_output=True)
        subprocess.run(['sudo', 'systemctl', 'enable', 'hostapd'], capture_output=True)
        
        # Restart services
        subprocess.run(['sudo', 'systemctl', 'restart', 'dhcpcd'], capture_output=True)
        time.sleep(2)
        subprocess.run(['sudo', 'systemctl', 'restart', 'dnsmasq'], capture_output=True)
        time.sleep(1)
        subprocess.run(['sudo', 'systemctl', 'restart', 'hostapd'], capture_output=True)
        
        logging.info("Access point services started")
        return True
    except Exception as e:
        logging.error(f"Error starting access point: {str(e)}")
        return False


def stop_access_point():
    """Stop the access point services"""
    try:
        subprocess.run(['sudo', 'systemctl', 'stop', 'hostapd'], capture_output=True)
        subprocess.run(['sudo', 'systemctl', 'disable', 'hostapd'], capture_output=True)
        
        logging.info("Access point services stopped")
        return True
    except Exception as e:
        logging.error(f"Error stopping access point: {str(e)}")
        return False


def get_ap_status():
    """Get the current status of the access point"""
    try:
        result = subprocess.run(['sudo', 'systemctl', 'is-active', 'hostapd'],
                              capture_output=True, text=True)
        is_active = result.stdout.strip() == 'active'
        
        status_result = subprocess.run(['sudo', 'systemctl', 'status', 'hostapd'],
                                     capture_output=True, text=True)
        
        # Get connected clients
        clients = []
        try:
            iw_result = subprocess.run(['sudo', 'iw', 'dev', 'wlan0', 'station', 'dump'],
                                      capture_output=True, text=True)
            stations = re.findall(r'Station ([0-9a-f:]+)', iw_result.stdout)
            clients = stations
        except:
            pass
        
        return {
            'active': is_active,
            'status': status_result.stdout,
            'clients': clients,
            'client_count': len(clients)
        }
    except Exception as e:
        logging.error(f"Error getting AP status: {str(e)}")
        return {
            'active': False,
            'status': 'Error getting status',
            'clients': [],
            'client_count': 0
        }


@ns_hosts.route('')
class HostList(Resource):
    @ns_hosts.doc('list_hosts')
    @ns_hosts.marshal_list_with(host_model)
    def get(self):
        '''List all DHCP hosts'''
        hosts = read_dhcp_hosts()
        return [{'mac': mac, 'hostname': hostname, 'ip': ip or ''} for mac, hostname, ip in hosts]
    
    @ns_hosts.doc('create_host')
    @ns_hosts.expect(host_model)
    @ns_hosts.response(201, 'Host created successfully')
    @ns_hosts.response(400, 'Validation error')
    def post(self):
        '''Add a new DHCP host'''
        data = api.payload
        if not data or 'mac' not in data or 'hostname' not in data:
            api.abort(400, 'Missing required fields (mac, hostname)')

        mac = data['mac']
        hostname = data['hostname']
        ip = data.get('ip')

        hosts = read_dhcp_hosts()
        if any(h[0] == mac for h in hosts):
            api.abort(400, 'MAC address already exists')
        if any(h[1] == hostname for h in hosts):
            api.abort(400, 'Hostname already exists')

        hosts.append((mac, hostname, ip))
        try:
            write_dhcp_hosts(hosts)
            restart_dnsmasq()
            return {'message': 'Host added successfully'}, 201
        except Exception as e:
            logging.error(f"Error adding host via API: {str(e)}")
            api.abort(500, 'Failed to add host')


@ns_hosts.route('/<string:mac>')
@ns_hosts.param('mac', 'The MAC address')
class Host(Resource):
    @ns_hosts.doc('delete_host')
    @ns_hosts.response(200, 'Host deleted successfully')
    @ns_hosts.response(404, 'Host not found')
    def delete(self, mac):
        '''Delete a DHCP host by MAC address'''
        hosts = read_dhcp_hosts()
        original_count = len(hosts)
        hosts = [h for h in hosts if h[0] != mac]
        if len(hosts) == original_count:
            api.abort(404, 'Host not found')

        try:
            write_dhcp_hosts(hosts)
            restart_dnsmasq()
            return {'message': 'Host removed successfully'}, 200
        except Exception as e:
            logging.error(f"Error removing host via API: {str(e)}")
            api.abort(500, 'Failed to remove host')


@ns_logs.route('')
class LogsList(Resource):
    @ns_logs.doc('get_logs')
    @ns_logs.param('lines', 'Number of log lines to retrieve (default: 50)')
    def get(self):
        '''Get application logs'''
        lines = request.args.get('lines', default=50, type=int)
        try:
            with open(LOG_FILE, 'r') as file:
                log_contents = file.readlines()
            last_logs = log_contents[-lines:]
            return {'logs': last_logs}
        except Exception as e:
            logging.error(f"Error reading log file: {str(e)}")
            api.abort(500, 'Failed to read log file')


@ns_logs.route('/download')
class LogsDownload(Resource):
    @ns_logs.doc('download_logs')
    def get(self):
        '''Download complete log file'''
        try:
            return send_file(LOG_FILE, as_attachment=True)
        except Exception as e:
            logging.error(f"Error downloading log file: {str(e)}")
            api.abort(500, 'Failed to download log file')


@ns_ap.route('/config')
class AccessPointConfig(Resource):
    @ns_ap.doc('get_ap_config')
    def get(self):
        '''Get current Access Point configuration'''
        config = read_ap_config()
        return config
    
    @ns_ap.doc('configure_ap')
    @ns_ap.expect(ap_config_model)
    @ns_ap.response(200, 'Access Point configured successfully')
    @ns_ap.response(400, 'Validation error')
    def post(self):
        '''Configure Access Point settings'''
        data = api.payload
        if not data or 'ssid' not in data or 'password' not in data:
            api.abort(400, 'Missing required fields (ssid, password)')
        
        ssid = data['ssid']
        password = data['password']
        channel = data.get('channel', '6')
        hw_mode = data.get('hw_mode', 'g')
        country = data.get('country', 'BE')
        
        if len(password) < 8:
            api.abort(400, 'Password must be at least 8 characters')
        
        try:
            if not configure_access_point(ssid, password, channel, hw_mode, country):
                api.abort(500, 'Failed to configure access point')
            
            if not configure_network_interfaces():
                api.abort(500, 'Failed to configure network interfaces')
            
            if not configure_dnsmasq_for_ap():
                api.abort(500, 'Failed to configure dnsmasq')
            
            if not enable_ip_forwarding():
                api.abort(500, 'Failed to configure network')
            
            return {'message': 'Access point configured successfully'}, 200
        except Exception as e:
            logging.error(f"Error configuring AP via API: {str(e)}")
            api.abort(500, f'Failed to configure access point: {str(e)}')


@ns_ap.route('/start')
class AccessPointStart(Resource):
    @ns_ap.doc('start_ap')
    @ns_ap.response(200, 'Access Point started')
    def post(self):
        '''Start the Access Point'''
        try:
            if start_access_point():
                return {'message': 'Access point started successfully'}, 200
            else:
                api.abort(500, 'Failed to start access point')
        except Exception as e:
            logging.error(f"Error starting AP via API: {str(e)}")
            api.abort(500, f'Failed to start access point: {str(e)}')


@ns_ap.route('/stop')
class AccessPointStop(Resource):
    @ns_ap.doc('stop_ap')
    @ns_ap.response(200, 'Access Point stopped')
    def post(self):
        '''Stop the Access Point'''
        try:
            if stop_access_point():
                return {'message': 'Access point stopped successfully'}, 200
            else:
                api.abort(500, 'Failed to stop access point')
        except Exception as e:
            logging.error(f"Error stopping AP via API: {str(e)}")
            api.abort(500, f'Failed to stop access point: {str(e)}')


@ns_ap.route('/status')
class AccessPointStatus(Resource):
    @ns_ap.doc('get_ap_status')
    def get(self):
        '''Get Access Point status and connected clients'''
        status = get_ap_status()
        return status

@ns_ap.route('/internet-sharing/status')
class InternetSharingStatus(Resource):
    @ns_ap.doc('get_internet_sharing_status')
    def get(self):
        '''Get internet sharing status'''
        status = get_internet_sharing_status()
        return status


@ns_ap.route('/internet-sharing/enable')
class InternetSharingEnable(Resource):
    @ns_ap.doc('enable_internet_sharing')
    @ns_ap.response(200, 'Internet sharing enabled')
    def post(self):
        '''Enable internet sharing from wlan1 to local network (wlan0 + eth0)'''
        try:
            if enable_internet_sharing():
                return {'message': 'Internet sharing enabled successfully'}, 200
            else:
                api.abort(500, 'Failed to enable internet sharing')
        except Exception as e:
            logging.error(f"Error enabling internet sharing via API: {str(e)}")
            api.abort(500, f'Failed to enable internet sharing: {str(e)}')


@ns_ap.route('/internet-sharing/disable')
class InternetSharingDisable(Resource):
    @ns_ap.doc('disable_internet_sharing')
    @ns_ap.response(200, 'Internet sharing disabled')
    def post(self):
        '''Disable internet sharing - isolate local network'''
        try:
            if disable_internet_sharing():
                return {'message': 'Internet sharing disabled successfully'}, 200
            else:
                api.abort(500, 'Failed to disable internet sharing')
        except Exception as e:
            logging.error(f"Error disabling internet sharing via API: {str(e)}")
            api.abort(500, f'Failed to disable internet sharing: {str(e)}')



@ns_connections.route('')
class ConnectionList(Resource):
    @ns_connections.doc('get_connections')
    @ns_connections.param('limit', 'Maximum number of results (default: 100)')
    @ns_connections.param('type', 'Filter by event type (connect/disconnect)')
    @ns_connections.param('mac', 'Filter by MAC address')
    @ns_connections.param('interface', 'Filter by interface (wlan0/eth0)')
    def get(self):
        '''Get connection history with optional filters'''
        limit = request.args.get('limit', default=100, type=int)
        filter_type = request.args.get('type')
        filter_mac = request.args.get('mac')
        filter_interface = request.args.get('interface')
        
        filtered = connection_history.copy()
        
        if filter_type:
            filtered = [c for c in filtered if c['event'] == filter_type]
        if filter_mac:
            filtered = [c for c in filtered if c['mac'].lower() == filter_mac.lower()]
        if filter_interface:
            filtered = [c for c in filtered if c['interface'] == filter_interface]
        
        filtered = list(reversed(filtered))[:limit]
        
        return {
            'total': len(connection_history),
            'filtered': len(filtered),
            'connections': filtered
        }


@ns_connections.route('/active')
class ConnectionActive(Resource):
    @ns_connections.doc('get_active_connections')
    def get(self):
        '''Get currently active connections'''
        active = get_active_connections()
        return {
            'count': len(active),
            'connections': active
        }


@ns_connections.route('/monitor')
class ConnectionMonitor(Resource):
    @ns_connections.doc('monitor_connections')
    @ns_connections.response(200, 'Monitoring completed')
    def post(self):
        '''Manually trigger connection monitoring'''
        try:
            monitor_connections()
            return {'message': 'Connection monitoring completed'}, 200
        except Exception as e:
            logging.error(f"Error monitoring connections: {str(e)}")
            api.abort(500, 'Failed to monitor connections')


@ns_connections.route('/stats')
class ConnectionStats(Resource):
    @ns_connections.doc('get_connection_stats')
    def get(self):
        '''Get connection statistics'''
        total_connections = len([c for c in connection_history if c['event'] == 'connect'])
        total_disconnections = len([c for c in connection_history if c['event'] == 'disconnect'])
        
        wlan_connections = len([c for c in connection_history if c['event'] == 'connect' and c['interface'] == 'wlan0'])
        eth_connections = len([c for c in connection_history if c['event'] == 'connect' and c['interface'] == 'eth0'])
        
        unique_macs = len(set(c['mac'] for c in connection_history))
        active = get_active_connections()
        
        return {
            'total_connections': total_connections,
            'total_disconnections': total_disconnections,
            'wireless_connections': wlan_connections,
            'wired_connections': eth_connections,
            'unique_devices': unique_macs,
            'currently_active': len(active),
            'active_devices': active
        }

@app.route('/', methods=['GET', 'POST'])
def dashboard():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            try:
                mac = request.form.get('mac')
                hostname = request.form.get('hostname')
                ip = request.form.get('ip') or None
                hosts = read_dhcp_hosts()
                if any(h[0] == mac for h in hosts):
                    flash(f"MAC address {mac} already exists. Edit the existing entry to update.")
                elif any(h[1] == hostname for h in hosts):
                    flash(f"Hostname {hostname} already exists. Choose a different hostname.")
                else:
                    hosts.append((mac, hostname, ip))
                    write_dhcp_hosts(hosts)
                    restart_dnsmasq()
                    flash("Host added successfully.")
            except Exception as e:
                flash(f"Error adding host: {str(e)}")
                logging.error(f"Error adding host: {str(e)}")
        elif action == 'restart':
            try:
                restart_dnsmasq()
                flash("DNSMASQ service restarted.")
            except Exception as e:
                flash(f"Error restarting DNSMASQ: {str(e)}")
        elif action == 'backup':
            try:
                backup_file = backup_dnsmasq_conf()
                flash(f"Backup created: {backup_file}")
            except Exception as e:
                flash(f"Error creating backup: {str(e)}")
        elif action == 'status':
            status = get_dnsmasq_status()
            flash(f"DNSMASQ Status:\n{status}")
        elif action == 'shutdown':
            return render_template_string('''
<!DOCTYPE html>
<html lang="en">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Confirm Shutdown</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background-color: #f5f5f5;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        min-height: 100vh;
                    }
                    .container {
                        background-color: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        max-width: 400px;
                        width: 100%;
                    }
                    h1 {
                        color: #343f48;
                        margin-top: 0;
                        font-size: 24px;
                    }
                    .warning {
                        color: red;
                        font-weight: bold;
                        font-size: 18px;
                    }
                    p {
                        font-size: 16px;
                        line-height: 1.5;
                    }
                    input[type="submit"] {
                        background-color: #343f48;
                        color: #ffd700;
                        font-size: 16px;
                        border: none;
                        border-radius: 5px;
                        padding: 12px 20px;
                        cursor: pointer;
                        width: 100%;
                        margin-top: 20px;
                    }
                    input[type="submit"]:hover {
                        background-color: red;
                        color: yellow;
                        font-weight: bold;
                    }
                    .cancel-link {
                        display: block;
                        text-align: center;
                        margin-top: 20px;
                        color: #343f48;
                        text-decoration: none;
                        font-size: 16px;
                    }
                    .cancel-link:hover {
                        text-decoration: underline;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Confirm Shutdown</h1>
                    <p class="warning">Are you sure you want to shut down the Raspberry Pi?</p>
                    <p>This will terminate all services and you won't be able to access the device remotely until it's manually restarted.</p>
                    <form method="post">
                        <input type="hidden" name="action" value="confirm_shutdown">
                        <input type="submit" value="Yes, Shut Down">
                    </form>
                    <a href="{{ url_for('dashboard') }}" class="cancel-link">Cancel</a>
                </div>
            </body>
            </html>
            ''')
        elif action == 'confirm_shutdown':
            flash("Shutting down the Raspberry Pi...")
            shutdown_pi()
        elif action == 'wifi':
            ssid = request.form.get('ssid')
            password = request.form.get('password')
            if update_wifi_settings(ssid, password):
                flash("Wi-Fi settings updated successfully. The Raspberry Pi has connected to the new network.",
                      "success")
            else:
                flash("Failed to update Wi-Fi settings or connect to the new network.", "error")
        elif action == 'configure_ap':
            ssid = request.form.get('ap_ssid')
            password = request.form.get('ap_password')
            channel = request.form.get('ap_channel', '6')
            if len(password) < 8:
                flash("Access Point password must be at least 8 characters.", "error")
            else:
                try:
                    if (configure_access_point(ssid, password, channel) and
                        configure_network_interfaces() and
                        configure_dnsmasq_for_ap() and
                        enable_ip_forwarding()):
                        flash("Access Point configured successfully. Use 'Start Access Point' to enable it.", "success")
                    else:
                        flash("Failed to configure Access Point.", "error")
                except Exception as e:
                    flash(f"Error configuring Access Point: {str(e)}", "error")
        elif action == 'start_ap':
            try:
                if start_access_point():
                    flash("Access Point started successfully.", "success")
                else:
                    flash("Failed to start Access Point.", "error")
            except Exception as e:
                flash(f"Error starting Access Point: {str(e)}", "error")
        elif action == 'stop_ap':
            try:
                if stop_access_point():
                    flash("Access Point stopped successfully.", "success")
                else:
                    flash("Failed to stop Access Point.", "error")
            except Exception as e:
                flash(f"Error stopping Access Point: {str(e)}", "error")
        elif action == 'ap_status':
            try:
                status = get_ap_status()
                if status['active']:
                    flash(f"Access Point is ACTIVE\nConnected clients: {status['client_count']}\nClients: {', '.join(status['clients']) if status['clients'] else 'None'}", "success")
                else:
                    flash("Access Point is INACTIVE", "error")
            except Exception as e:
                flash(f"Error getting AP status: {str(e)}", "error")
        elif action == 'enable_internet':
            try:
                if enable_internet_sharing():
                    flash("Internet sharing ENABLED! Devices on wlan0/eth0 can now access internet through wlan1.", "success")
                else:
                    flash("Failed to enable internet sharing.", "error")
            except Exception as e:
                flash(f"Error enabling internet sharing: {str(e)}", "error")
        elif action == 'disable_internet':
            try:
                if disable_internet_sharing():
                    flash("Internet sharing DISABLED. Local network is now isolated.", "success")
                else:
                    flash("Failed to disable internet sharing.", "error")
            except Exception as e:
                flash(f"Error disabling internet sharing: {str(e)}", "error")

    hosts = read_dhcp_hosts()
    ap_config = read_ap_config()
    internet_sharing = get_internet_sharing_status()
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DHCP/DNS Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        :root {
            --primary-color: #343f48;
            --accent-color: #ffd700;
            --success-color: #28a745;
            --danger-color: #dc3545;
            --info-color: #17a2b8;
            --warning-color: #ffc107;
            --light-gray: #f8f9fa;
            --border-color: #dee2e6;
            --text-color: #333;
            --shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
        }
        
        html, body {
            height: 100%;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--light-gray);
            color: var(--text-color);
        }
        
        .container {
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }
        
        /* Header */
        .header {
            background: linear-gradient(135deg, var(--primary-color), #2c3e50);
            color: white;
            padding: 1rem;
            box-shadow: var(--shadow);
        }
        
        .header h1 {
            font-size: 1.8rem;
            font-weight: 300;
        }
        
        /* Flash Messages */
        .flash-messages {
            padding: 1rem;
        }
        
        .flash {
            background-color: #e9ecef;
            border-left: 4px solid var(--info-color);
            padding: 1rem;
            margin-bottom: 1rem;
            border-radius: 4px;
            white-space: pre-wrap;
        }
        
        .flash.danger {
            background-color: #f8d7da;
            border-left-color: var(--danger-color);
            color: #721c24;
        }
        
        /* Navigation Tabs */
        .nav-tabs {
            background: white;
            border-bottom: 1px solid var(--border-color);
            box-shadow: var(--shadow);
            overflow-x: auto;
            white-space: nowrap;
        }
        
        .nav-tabs ul {
            display: flex;
            list-style: none;
            margin: 0;
            padding: 0;
            min-width: max-content;
        }
        
        .nav-tabs li {
            border-right: 1px solid var(--border-color);
        }
        
        .nav-tabs button {
            background: none;
            border: none;
            padding: 1rem 1.5rem;
            cursor: pointer;
            font-size: 0.95rem;
            color: var(--text-color);
            transition: all 0.3s ease;
            white-space: nowrap;
            width: 100%;
        }
        
        .nav-tabs button:hover {
            background-color: var(--light-gray);
        }
        
        .nav-tabs button.active {
            background-color: var(--primary-color);
            color: var(--accent-color);
            font-weight: 500;
        }
        
        .nav-tabs button.active::after {
            content: '';
            position: absolute;
            bottom: -1px;
            left: 0;
            right: 0;
            height: 3px;
            background-color: var(--accent-color);
        }
        
        .nav-tabs li {
            position: relative;
        }
        
        /* Content Area */
        .content {
            flex: 1;
            padding: 2rem;
            max-width: 1200px;
            margin: 0 auto;
            width: 100%;
        }
        
        .tab-content {
            display: none;
        }
        
        .tab-content.active {
            display: block;
        }
        
        /* Cards and Sections */
        .section {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: var(--shadow);
        }
        
        .section h2 {
            color: var(--primary-color);
            margin-bottom: 1.5rem;
            border-bottom: 2px solid var(--accent-color);
            padding-bottom: 0.5rem;
            font-size: 1.4rem;
            font-weight: 400;
        }
        
        /* Grid Layouts */
        .grid {
            display: grid;
            gap: 1.5rem;
        }
        
        .grid-2 {
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
        }
        
        .grid-3 {
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        }
        
        .grid-4 {
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        }
        
        /* Host Cards */
        .host-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: var(--shadow);
            border: 1px solid var(--border-color);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .host-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
        }
        
        .host-card h3 {
            color: var(--primary-color);
            margin-bottom: 1rem;
            font-size: 1.2rem;
            border-bottom: 2px solid var(--accent-color);
            padding-bottom: 0.5rem;
        }
        
        .host-info p {
            margin: 0.5rem 0;
            color: #666;
        }
        
        .host-info strong {
            color: var(--text-color);
        }
        
        .host-actions {
            display: flex;
            gap: 0.5rem;
            margin-top: 1rem;
        }
        
        .host-actions form {
            flex: 1;
        }
        
        /* Form Styling */
        .form-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: var(--shadow);
            border: 1px solid var(--border-color);
        }
        
        .form-card h3 {
            color: var(--primary-color);
            margin-bottom: 1.5rem;
            font-size: 1.2rem;
        }
        
        .form-group {
            margin-bottom: 1rem;
        }
        
        label {
            display: block;
            margin-bottom: 0.5rem;
            color: var(--text-color);
            font-weight: 500;
        }
        
        input[type="text"],
        input[type="password"],
        select {
            width: 100%;
            padding: 0.75rem;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            font-size: 1rem;
            transition: border-color 0.3s ease;
        }
        
        input[type="text"]:focus,
        input[type="password"]:focus,
        select:focus {
            outline: none;
            border-color: var(--primary-color);
        }
        
        /* Button Styling */
        .btn {
            display: inline-block;
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 8px;
            font-size: 0.95rem;
            font-weight: 500;
            text-decoration: none;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            min-width: 120px;
        }
        
        .btn-primary {
            background-color: var(--primary-color);
            color: var(--accent-color);
        }
        
        .btn-primary:hover {
            background-color: #2c3e50;
            transform: translateY(-1px);
        }
        
        .btn-success {
            background-color: var(--success-color);
            color: white;
        }
        
        .btn-success:hover {
            background-color: #218838;
        }
        
        .btn-danger {
            background-color: var(--danger-color);
            color: white;
        }
        
        .btn-danger:hover {
            background-color: #c82333;
        }
        
        .btn-info {
            background-color: var(--info-color);
            color: white;
        }
        
        .btn-info:hover {
            background-color: #138496;
        }
        
        .btn-warning {
            background-color: var(--warning-color);
            color: var(--text-color);
        }
        
        .btn-full {
            width: 100%;
        }
        
        .btn-group {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin: 1rem 0;
        }
        
        /* Status Indicators */
        .status {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 500;
        }
        
        .status-active {
            background-color: #d4edda;
            color: #155724;
        }
        
        .status-inactive {
            background-color: #f8d7da;
            color: #721c24;
        }
        
        .status-enabled {
            background-color: #d1ecf1;
            color: #0c5460;
        }
        
        /* Connection History Table */
        .table-responsive {
            overflow-x: auto;
            background: white;
            border-radius: 10px;
            box-shadow: var(--shadow);
            margin: 1rem 0;
        }
        
        .connection-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .connection-table th {
            background-color: var(--primary-color);
            color: var(--accent-color);
            padding: 1rem;
            text-align: left;
            font-weight: 500;
        }
        
        .connection-table td {
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
        }
        
        .connection-table tr:hover {
            background-color: var(--light-gray);
        }
        
        .interface-badge {
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8rem;
            font-weight: 500;
            color: white;
        }
        
        .interface-wlan0 {
            background-color: var(--info-color);
        }
        
        .interface-eth0 {
            background-color: #6c757d;
        }
        
        /* Stats Cards */
        .stat-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            text-align: center;
            box-shadow: var(--shadow);
            border: 1px solid var(--border-color);
        }
        
        .stat-card h4 {
            color: var(--primary-color);
            margin-bottom: 0.5rem;
            font-size: 1rem;
        }
        
        .stat-card .stat-number {
            font-size: 2rem;
            font-weight: bold;
            margin: 0.5rem 0;
        }
        
        .stat-success {
            color: var(--success-color);
        }
        
        .stat-danger {
            color: var(--danger-color);
        }
        
        .stat-info {
            color: var(--info-color);
        }
        
        .stat-warning {
            color: var(--warning-color);
        }
        
        /* Footer */
        .footer {
            background-color: var(--primary-color);
            color: white;
            text-align: center;
            padding: 1rem;
            margin-top: auto;
        }
        
        /* Responsive Design */
        @media (max-width: 768px) {
            .content {
                padding: 1rem;
            }
            
            .nav-tabs button {
                padding: 0.75rem 1rem;
                font-size: 0.9rem;
            }
            
            .btn-group {
                flex-direction: column;
            }
            
            .btn-group .btn {
                width: 100%;
                margin-bottom: 0.5rem;
            }
            
            .host-actions {
                flex-direction: column;
            }
            
            .grid-2,
            .grid-3,
            .grid-4 {
                grid-template-columns: 1fr;
            }
            
            .connection-table th,
            .connection-table td {
                padding: 0.5rem;
                font-size: 0.9rem;
            }
            
            .stat-card .stat-number {
                font-size: 1.5rem;
            }
        }
        
        @media (max-width: 480px) {
            .header {
                padding: 0.75rem;
            }
            
            .header h1 {
                font-size: 1.5rem;
            }
            
            .content {
                padding: 0.75rem;
            }
            
            .section {
                padding: 1rem;
            }
            
            .nav-tabs button {
                padding: 0.6rem 0.8rem;
                font-size: 0.85rem;
            }
        }
        
        /* Loading States */
        .loading {
            text-align: center;
            padding: 2rem;
            color: #666;
        }
        
        /* Note styling */
        .note {
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 1rem;
            margin: 1rem 0;
            font-size: 0.9rem;
            color: #856404;
        }
    </style>
</head>
<body>
    <div class="container">
        <header class="header">
            <h1>🌐 DHCP/DNS Dashboard</h1>
        </header>
        
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="flash-messages">
                    {% for message in messages %}
                        <div class="flash{% if 'error' in message.lower() or 'failed' in message.lower() %} danger{% endif %}">{{ message }}</div>
                    {% endfor %}
                </div>
            {% endif %}
        {% endwith %}
        
        <nav class="nav-tabs">
            <ul>
                <li><button class="tab-btn active" data-tab="overview">📊 Overview</button></li>
                <li><button class="tab-btn" data-tab="hosts">🖥️ Host Management</button></li>
                <li><button class="tab-btn" data-tab="network">📡 Network Config</button></li>
                <li><button class="tab-btn" data-tab="monitoring">📈 Monitoring</button></li>
                <li><button class="tab-btn" data-tab="system">⚙️ System</button></li>
            </ul>
        </nav>
        
        <main class="content">
            <!-- Overview Tab -->
            <div id="overview" class="tab-content active">
                <div class="section">
                    <h2>System Status Overview</h2>
                    <div class="grid grid-4">
                        <div class="stat-card">
                            <h4>DHCP Hosts</h4>
                            <div class="stat-number stat-info">{{ hosts|length }}</div>
                        </div>
                        <div class="stat-card">
                            <h4>Access Point</h4>
                            <div class="stat-number {% if ap_config.enabled %}stat-success{% else %}stat-danger{% endif %}">
                                {% if ap_config.enabled %}Active{% else %}Inactive{% endif %}
                            </div>
                        </div>
                        <div class="stat-card">
                            <h4>Internet Sharing</h4>
                            <div class="stat-number {% if internet_sharing.enabled %}stat-success{% else %}stat-warning{% endif %}">
                                {% if internet_sharing.enabled %}Enabled{% else %}Disabled{% endif %}
                            </div>
                        </div>
                        <div class="stat-card">
                            <h4>Network Status</h4>
                            <div class="stat-number stat-success">Online</div>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Quick Actions</h2>
                    <div class="btn-group">
                        <button class="btn btn-primary" onclick="showTab('hosts')">Manage Hosts</button>
                        <button class="btn btn-info" onclick="showTab('network')">Network Setup</button>
                        <button class="btn btn-success" onclick="showTab('monitoring')">View Monitoring</button>
                    </div>
                </div>
            </div>
            
            <!-- Host Management Tab -->
            <div id="hosts" class="tab-content">
                <div class="section">
                    <h2>Current DHCP Hosts</h2>
                    {% if hosts %}
                        <div class="grid grid-3">
                            {% for mac, hostname, ip in hosts %}
                            <div class="host-card">
                                <h3>{{ hostname }}</h3>
                                <div class="host-info">
                                    <p><strong>MAC:</strong> <code>{{ mac }}</code></p>
                                    <p><strong>IP:</strong> <code>{{ ip if ip else 'Dynamic' }}</code></p>
                                </div>
                                <div class="host-actions">
                                    <form method="get" action="{{ url_for('edit_host') }}">
                                        <input type="hidden" name="mac" value="{{ mac }}">
                                        <button type="submit" class="btn btn-primary btn-full">Edit</button>
                                    </form>
                                    <form onsubmit="return confirmRemove('{{ hostname }}')" method="post" action="{{ url_for('remove_host') }}">
                                        <input type="hidden" name="mac" value="{{ mac }}">
                                        <button type="submit" class="btn btn-danger btn-full">Remove</button>
                                    </form>
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                    {% else %}
                        <p>No DHCP hosts configured yet.</p>
                    {% endif %}
                </div>
                
                <div class="section">
                    <h2>Add New Host</h2>
                    <div class="form-card">
                        <form method="post">
                            <input type="hidden" name="action" value="add">
                            <div class="form-group">
                                <label for="mac">MAC Address:</label>
                                <input type="text" id="mac" name="mac" placeholder="00:11:22:33:44:55" required>
                            </div>
                            <div class="form-group">
                                <label for="hostname">Hostname:</label>
                                <input type="text" id="hostname" name="hostname" placeholder="device-name" required>
                            </div>
                            <div class="form-group">
                                <label for="ip">IP Address (optional):</label>
                                <input type="text" id="ip" name="ip" placeholder="192.168.4.100">
                            </div>
                            <button type="submit" class="btn btn-success btn-full">Add Host</button>
                        </form>
                    </div>
                </div>
            </div>
            
            <!-- Network Configuration Tab -->
            <div id="network" class="tab-content">
                <div class="grid grid-2">
                    <div class="section">
                        <h2>Wi-Fi Client Configuration</h2>
                        <p>Configure wlan1 to connect to an external Wi-Fi network for internet access.</p>
                        <div class="form-card">
                            <form method="post">
                                <input type="hidden" name="action" value="wifi">
                                <div class="form-group">
                                    <label for="ssid">Wi-Fi SSID:</label>
                                    <input type="text" id="ssid" name="ssid" required>
                                </div>
                                <div class="form-group">
                                    <label for="password">Wi-Fi Password:</label>
                                    <input type="password" id="password" name="password" required>
                                </div>
                                <button type="submit" class="btn btn-primary btn-full">Update Wi-Fi Settings</button>
                            </form>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>Access Point Configuration</h2>
                        <p>Configure wlan0 as a wireless access point for local devices.</p>
                        <div class="form-card">
                            <form method="post">
                                <input type="hidden" name="action" value="configure_ap">
                                <div class="form-group">
                                    <label for="ap_ssid">AP SSID:</label>
                                    <input type="text" id="ap_ssid" name="ap_ssid" value="{{ ap_config.ssid }}" required>
                                </div>
                                <div class="form-group">
                                    <label for="ap_password">AP Password (min 8 chars):</label>
                                    <input type="password" id="ap_password" name="ap_password" value="{{ ap_config.password }}" required minlength="8">
                                </div>
                                <div class="form-group">
                                    <label for="ap_channel">Wi-Fi Channel (2.4GHz):</label>
                                    <select id="ap_channel" name="ap_channel">
                                        <option value="1" {{ 'selected' if ap_config.channel == '1' else '' }}>Channel 1 (2412 MHz)</option>
                                        <option value="6" {{ 'selected' if ap_config.channel == '6' else '' }}>Channel 6 (2437 MHz) - Default</option>
                                        <option value="11" {{ 'selected' if ap_config.channel == '11' else '' }}>Channel 11 (2462 MHz)</option>
                                    </select>
                                </div>
                                <div class="note">
                                    💡 <strong>Tip:</strong> Channels 1, 6, and 11 are recommended for minimal interference.
                                </div>
                                <button type="submit" class="btn btn-primary btn-full">Configure Access Point</button>
                            </form>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <h2>Network Management</h2>
                    <div class="grid grid-2">
                        <div>
                            <h3>Access Point Control</h3>
                            <p><strong>Status:</strong> <span class="status {% if ap_config.enabled %}status-active{% else %}status-inactive{% endif %}">{{ 'Active' if ap_config.enabled else 'Inactive' }}</span></p>
                            <div class="btn-group">
                                <form method="post" style="display: inline;">
                                    <input type="hidden" name="action" value="start_ap">
                                    <button type="submit" class="btn btn-success">Start AP</button>
                                </form>
                                <form method="post" style="display: inline;">
                                    <input type="hidden" name="action" value="stop_ap">
                                    <button type="submit" class="btn btn-danger">Stop AP</button>
                                </form>
                                <form method="post" style="display: inline;">
                                    <input type="hidden" name="action" value="ap_status">
                                    <button type="submit" class="btn btn-info">Check Status</button>
                                </form>
                            </div>
                        </div>
                        
                        <div>
                            <h3>Internet Sharing</h3>
                            <p><strong>Status:</strong> <span class="status {% if internet_sharing.enabled %}status-enabled{% else %}status-inactive{% endif %}">{{ 'Enabled' if internet_sharing.enabled else 'Disabled' }}</span></p>
                            <p class="note">
                                {% if internet_sharing.enabled %}
                                🌐 Local devices can access internet through wlan1
                                {% else %}
                                🔒 Local network is isolated from internet
                                {% endif %}
                            </p>
                            <div class="btn-group">
                                <form method="post" style="display: inline;">
                                    <input type="hidden" name="action" value="enable_internet">
                                    <button type="submit" class="btn btn-info">Enable Sharing</button>
                                </form>
                                <form method="post" style="display: inline;">
                                    <input type="hidden" name="action" value="disable_internet">
                                    <button type="submit" class="btn btn-warning">Disable Sharing</button>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Monitoring Tab -->
            <div id="monitoring" class="tab-content">
                <div class="section">
                    <h2>Connection Statistics</h2>
                    <div class="btn-group">
                        <button class="btn btn-primary" onclick="loadConnections()">Refresh Data</button>
                        <button class="btn btn-info" onclick="loadStats()">View Statistics</button>
                    </div>
                    <div id="connectionStats" style="display: none;"></div>
                </div>
                
                <div class="section">
                    <h2>Recent Connections</h2>
                    <div id="connectionHistory" class="loading">Loading connection history...</div>
                </div>
            </div>
            
            <!-- System Tab -->
            <div id="system" class="tab-content">
                <div class="grid grid-2">
                    <div class="section">
                        <h2>DNSMASQ Management</h2>
                        <p>Manage the DHCP/DNS service that handles IP assignments and name resolution.</p>
                        <div class="btn-group">
                            <form method="post" style="display: inline;">
                                <input type="hidden" name="action" value="restart">
                                <button type="submit" class="btn btn-primary">Restart Service</button>
                            </form>
                            <form method="post" style="display: inline;">
                                <input type="hidden" name="action" value="backup">
                                <button type="submit" class="btn btn-info">Backup Config</button>
                            </form>
                            <form method="post" style="display: inline;">
                                <input type="hidden" name="action" value="status">
                                <button type="submit" class="btn btn-success">Check Status</button>
                            </form>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2>System Management</h2>
                        <p>System-level operations. Use with caution.</p>
                        <div class="note">
                            ⚠️ <strong>Warning:</strong> Shutdown will make the device inaccessible until manually restarted.
                        </div>
                        <form method="post" style="display: inline;">
                            <input type="hidden" name="action" value="shutdown">
                            <button type="submit" class="btn btn-danger btn-full" onclick="return confirm('Are you sure you want to shutdown the Raspberry Pi? This will make it inaccessible until manually restarted.')">Shutdown Raspberry Pi</button>
                        </form>
                    </div>
                </div>
            </div>
        </main>
        
        <footer class="footer">
            <p>&copy; <span id="current-year"></span> JPHsystems. All rights reserved.</p>
        </footer>

        <script>
            // Set current year
            document.getElementById('current-year').textContent = new Date().getFullYear();
            
            // Tab switching functionality
            function showTab(tabName) {
                // Hide all tab contents
                const tabContents = document.querySelectorAll('.tab-content');
                tabContents.forEach(content => content.classList.remove('active'));
                
                // Remove active class from all tab buttons
                const tabBtns = document.querySelectorAll('.tab-btn');
                tabBtns.forEach(btn => btn.classList.remove('active'));
                
                // Show selected tab content
                document.getElementById(tabName).classList.add('active');
                
                // Add active class to clicked tab button
                const activeBtn = document.querySelector(`[data-tab="${tabName}"]`);
                if (activeBtn) activeBtn.classList.add('active');
                
                // Load data for monitoring tab
                if (tabName === 'monitoring') {
                    loadConnections();
                }
            }
            
            // Add click event listeners to tab buttons
            document.querySelectorAll('.tab-btn').forEach(btn => {
                btn.addEventListener('click', () => {
                    showTab(btn.dataset.tab);
                });
            });
            
            function confirmRemove(hostname) {
                return confirm(`Are you sure you want to remove the host "${hostname}"?`);
            }

            function loadConnections() {
                const container = document.getElementById('connectionHistory');
                container.innerHTML = '<div class="loading">Loading connections...</div>';
                
                fetch('/api/connections?limit=50')
                    .then(response => response.json())
                    .then(data => {
                        if (data.connections && data.connections.length > 0) {
                            let html = '<div class="table-responsive">';
                            html += '<table class="connection-table">';
                            html += '<thead><tr>';
                            html += '<th>Time</th><th>Event</th><th>MAC Address</th>';
                            html += '<th>IP Address</th><th>Hostname</th><th>Interface</th>';
                            html += '</tr></thead><tbody>';
                            
                            data.connections.forEach(conn => {
                                const time = new Date(conn.timestamp).toLocaleString();
                                const eventColor = conn.event === 'connect' ? 'stat-success' : 'stat-danger';
                                const interfaceClass = conn.interface === 'wlan0' ? 'interface-wlan0' : 'interface-eth0';
                                
                                html += '<tr>';
                                html += `<td>${time}</td>`;
                                html += `<td><span class="${eventColor}">${conn.event.toUpperCase()}</span></td>`;
                                html += `<td><code>${conn.mac}</code></td>`;
                                html += `<td><code>${conn.ip}</code></td>`;
                                html += `<td>${conn.hostname}</td>`;
                                html += `<td><span class="interface-badge ${interfaceClass}">${conn.interface}</span></td>`;
                                html += '</tr>';
                            });
                            
                            html += '</tbody></table></div>';
                            html += `<p style="margin-top: 1rem; color: #666; text-align: center;">Showing recent 50 connections (Total: ${data.total})</p>`;
                            container.innerHTML = html;
                        } else {
                            container.innerHTML = '<p style="text-align: center; color: #666;">No connection history available yet.</p>';
                        }
                    })
                    .catch(error => {
                        container.innerHTML = `<p style="color: var(--danger-color); text-align: center;">Error loading connections: ${error}</p>`;
                    });
            }

            function loadStats() {
                const container = document.getElementById('connectionStats');
                
                fetch('/api/connections/stats')
                    .then(response => response.json())
                    .then(data => {
                        let html = '<div class="grid grid-4" style="margin-top: 1rem;">';
                        
                        html += `<div class="stat-card">
                            <h4>Total Connections</h4>
                            <div class="stat-number stat-success">${data.total_connections}</div>
                        </div>`;
                        
                        html += `<div class="stat-card">
                            <h4>Disconnections</h4>
                            <div class="stat-number stat-danger">${data.total_disconnections}</div>
                        </div>`;
                        
                        html += `<div class="stat-card">
                            <h4>Wireless Connections</h4>
                            <div class="stat-number stat-info">${data.wireless_connections}</div>
                        </div>`;
                        
                        html += `<div class="stat-card">
                            <h4>Unique Devices</h4>
                            <div class="stat-number stat-warning">${data.unique_devices}</div>
                        </div>`;
                        
                        html += `<div class="stat-card">
                            <h4>Wired Connections</h4>
                            <div class="stat-number">${data.wired_connections}</div>
                        </div>`;
                        
                        html += `<div class="stat-card">
                            <h4>Currently Active</h4>
                            <div class="stat-number stat-success">${data.currently_active}</div>
                        </div>`;
                        
                        html += '</div>';
                        container.innerHTML = html;
                        container.style.display = 'block';
                    })
                    .catch(error => {
                        container.innerHTML = `<p style="color: var(--danger-color);">Error loading statistics: ${error}</p>`;
                        container.style.display = 'block';
                    });
            }

            // Load connections on page load if on monitoring tab
            window.addEventListener('load', function() {
                const activeTab = document.querySelector('.tab-content.active');
                if (activeTab && activeTab.id === 'monitoring') {
                    loadConnections();
                }
            });
        </script>
    </div>
</body>
</html>
    ''', hosts=hosts, ap_config=ap_config, internet_sharing=internet_sharing)


@app.route('/edit', methods=['GET', 'POST'])
def edit_host():
    if request.method == 'POST':
        old_mac = request.form.get('old_mac')
        new_mac = request.form.get('new_mac')
        new_hostname = request.form.get('new_hostname')
        new_ip = request.form.get('new_ip') or None

        hosts = read_dhcp_hosts()
        updated_hosts = [(new_mac, new_hostname, new_ip) if h[0] == old_mac else h for h in hosts]

        if hosts == updated_hosts:
            flash("No changes were made.")
        else:
            write_dhcp_hosts(updated_hosts)
            restart_dnsmasq()
            flash("Host updated successfully.")

        return redirect(url_for('dashboard'))

    mac = request.args.get('mac')
    hosts = read_dhcp_hosts()
    host = next((h for h in hosts if h[0] == mac), None)

    if not host:
        flash("Host not found.")
        return redirect(url_for('dashboard'))

    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Edit DHCP Host</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f0f0f0;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .container {
            background-color: white;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            width: 350px;
        }
        h1 {
            color: #333;
            margin-bottom: 1.5rem;
            font-size: 1.5rem;
        }
        form {
            display: flex;
            flex-direction: column;
        }
        label {
            margin-bottom: 0.5rem;
            color: #555;
        }
        input[type="text"] {
            padding: 0.5rem;
            margin-bottom: 1rem;
            border: 1px solid #ddd;
            border-radius: 14px;
            width: 100%;
            box-sizing: border-box;
        }
        input[type="submit"] {
            background-color: #343f48;
            color: #ffd700;
            padding: 0.75rem;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1rem;
            transition: background-color 0.3s;
        }
        input[type="submit"]:hover {
            background-color: #45a049;
        }
        .cancel-link {
            display: inline-block;
            margin-top: 1rem;
            color: #666;
            text-decoration: none;
            transition: color 0.3s;
        }
        .cancel-link:hover {
            color: #333;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Edit DHCP Host</h1>
        <form method="post">
            <input type="hidden" name="old_mac" value="{{ host[0] }}">
            
            <label for="new_mac">MAC Address:</label>
            <input type="text" id="new_mac" name="new_mac" value="{{ host[0] }}" required>
            
            <label for="new_hostname">Hostname:</label>
            <input type="text" id="new_hostname" name="new_hostname" value="{{ host[1] }}" required>
            
            <label for="new_ip">IP Address:</label>
            <input type="text" id="new_ip" name="new_ip" value="{{ host[2] or '' }}">
            
            <input type="submit" value="Update Host">
        </form>
        <a href="{{ url_for('dashboard') }}" class="cancel-link">Cancel</a>
    </div>
</body>
</html>
    ''', host=host)


@app.route('/remove', methods=['POST'])
def remove_host():
    try:
        mac = request.form.get('mac')
        hosts = read_dhcp_hosts()
        original_count = len(hosts)
        hosts = [h for h in hosts if h[0] != mac]
        if len(hosts) == original_count:
            flash(f"No host found with MAC address {mac}")
            logging.warning(f"Attempted to remove non-existent host with MAC {mac}")
        else:
            write_dhcp_hosts(hosts)
            restart_dnsmasq()
            flash("Host removed successfully.")
            logging.info(f"Removed host with MAC {mac}")
    except Exception as e:
        flash(f"Error removing host: {str(e)}")
        logging.error(f"Error removing host: {str(e)}")
    return redirect(url_for('dashboard'))


# Initialize connection history on startup
load_connection_history()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
    app.config['FORCE_JSON'] = True
