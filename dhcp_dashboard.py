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
        
        logging.info(f"Connection Event: {event_type.upper()} - {mac} ({ip}) - {hostname} on {interface}")
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

        new_content = [line for line in content if not line.startswith('dhcp-host=')]
        for mac, hostname, ip in hosts:
            if ip:
                new_content.append(f'dhcp-host={mac},{hostname},{ip}\n')
            else:
                new_content.append(f'dhcp-host={mac},{hostname}\n')

        with open(DNSMASQ_CONF, 'w') as f:
            f.writelines(new_content)

        logging.info(f"Wrote {len(hosts)} hosts to configuration")
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

        # Restart the Wi-Fi interface
        subprocess.run(['sudo', 'ifconfig', 'wlan0', 'down'], check=True)
        time.sleep(1)
        subprocess.run(['sudo', 'ifconfig', 'wlan0', 'up'], check=True)
        time.sleep(2)
        subprocess.run(['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'], check=True)

        # Wait for the connection to be established
        for _ in range(30):  # Wait up to 30 seconds
            result = subprocess.run(['iwgetid', '-r'], capture_output=True, text=True)
            if result.stdout.strip() == ssid:
                logging.info(f"Successfully connected to Wi-Fi network: {ssid}")
                return True
            time.sleep(1)

        logging.error(f"Failed to connect to Wi-Fi network: {ssid}")
        return False
    except Exception as e:
        logging.error(f"Error updating Wi-Fi settings: {str(e)}")
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
    """Configure network interfaces for AP mode (wlan0 as AP, eth0 for local network)"""
    try:
        # Configure dhcpcd to assign static IPs to both interfaces on same subnet
        dhcpcd_config = '''
# Local Network Configuration
# Both interfaces on same subnet for unified network

# Static IP configuration for wlan0 (Wireless Access Point)
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant

# Static IP configuration for eth0 (Wired/Switch connection)
interface eth0
    static ip_address=192.168.4.1/24
'''
        
        # Backup existing dhcpcd.conf
        if os.path.exists(DHCPCD_CONF):
            backup_file = f"{DHCPCD_CONF}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(DHCPCD_CONF, backup_file)
            logging.info(f"Backed up dhcpcd.conf to {backup_file}")
        
        # Read existing dhcpcd.conf and remove old wlan0/eth0 configurations
        existing_lines = []
        if os.path.exists(DHCPCD_CONF):
            with open(DHCPCD_CONF, 'r') as f:
                skip = False
                for line in f:
                    if line.strip().startswith('interface wlan0') or line.strip().startswith('interface eth0'):
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


def enable_ip_forwarding():
    """Setup network bridging for unified local network (no internet routing)"""
    try:
        # Disable IP forwarding (no routing needed for local network)
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
        
        # Clear any existing NAT rules
        subprocess.run(['sudo', 'iptables', '-t', 'nat', '-F'], capture_output=True)
        subprocess.run(['sudo', 'iptables', '-F'], capture_output=True)
        
        logging.info("Configured for local network (no internet routing)")
        return True
    except Exception as e:
        logging.error(f"Error enabling IP forwarding: {str(e)}")
        return False


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

    hosts = read_dhcp_hosts()
    ap_config = read_ap_config()
    return render_template_string('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DHCP/DNS Dashboard</title>
    <style>
        html, body {
            height: 100%;
            margin: 0;
            padding: 0;
            font-family: Arial, sans-serif;
        }
        .page-container {
            display: flex;
            flex-direction: column;
            min-height: 100vh;
        }
        .content-wrap {
            flex: 1 0 auto;
            padding: 20px;
        }
        body { font-family: Arial, sans-serif; }
        input[type="text"] { width: 200px; margin-bottom: 10px; }
        .flash { padding: 10px; background-color: #f0f0f0; margin-bottom: 20px; white-space: pre-wrap; }
        .danger { background-color: #ffdddd; color: #f44336; }
        .form-container {
            background-color: #f2f2f2;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            width: 300px;
        }
        h2 { color: #333; margin-bottom: 1.5rem; }
        form { display: flex; flex-direction: column; }
        label { margin-bottom: 0.5rem; color: #555; }
        input[type="text"] {
            padding: 0.5rem;
            margin-bottom: 1rem;
            border: 1px solid #ddd;
            border-radius: 14px;
        }
        input[type="submit"] {
            background-color:#343f48;
            color: #ffd700;
            padding: 0.75rem;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1rem;
            transition: background-color 0.3s;
        }
        input[type="submit"]:hover { background-color: #45a049; }
        .footer {
            flex-shrink: 0;
            background-color: #505e6b;
            color: #ffffff;
            text-align: center;
            padding: 10px;
            font-size: 20px;
        }
        
        .form-container-wrapper {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            width: 100%;
            margin-left: 0;
        }

        .form-container {
            flex: 1; /* Makes both containers take up equal width */
            width: auto;
            background-color: #f2f2f2;
            padding: 2rem;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            box-sizing: border-box;
        }
        .form-container input[type="text"],
        .form-container input[type="password"],
        .form-container input[type="submit"] {
            width: 100%;
            padding: 0.5rem;
            margin-bottom: 1rem;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }

        @media (max-width: 650px) {
            .dhcp-hosts, .form-container-wrapper {
                grid-template-columns: 1fr;
            }
            
            .host-card, .form-container {
                max-width: none;
                width: 100%;
            }
        }
            .responsive-table {
        width: 100%;
        margin-bottom: 20px;
        overflow-x: auto;
        }
        .action-buttons {
            display: flex;
            gap: 5px;
        }
        .action-buttons input[type="submit"] {
            padding: 5px 10px;
            font-size: 0.9em;
        }
        
        @media screen and (max-width: 600px) {
            .responsive-table {
                overflow-x: scroll;
            }
            th, td {
                padding: 8px;
            }
            .action-buttons {
                flex-direction: column;
            }
        }
        
        .dhcp-hosts, .form-container-wrapper {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 20px;
            width: 100%;
            margin-bottom: 30px;
        }
    
            .host-card, .form-container {
            background-color: #f2f2f2;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            width: 100%;
            box-sizing: border-box;
        }
    
    .host-card h3 {
        margin-top: 0;
        color: #343f48;
        border-bottom: 2px solid #ffd700;
        padding-bottom: 10px;
        margin-bottom: 15px;
    }
    
    .host-info {
        margin-bottom: 20px;
    }
    
    .host-info strong {
        color: #343f48;
    }
    
        .host-actions {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            margin-top: 15px;
        }
        
        .host-actions form {
            flex: 1;
        }
        
        .host-actions input[type="submit"] {
            width: 100%;
            padding: 10px 15px;
            border: none;
            border-radius: 10px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }
        
        .host-actions input[type="submit"]:hover {
            opacity: 0.9;
        }
        
        .edit-button {
            background-color: #343f48;
            color: #ffd700;
        }
        
        .remove-button {
            background-color: #e74c3c;
            color: white;
        }
        
        .host-actions input[type="submit"].remove-button:hover {
            background-color: #ff0000;
            color: yellow;
        }
    
    .host-actions input[type="submit"]:hover {
            background-color: #45a049;
    
    @media screen and (max-width: 600px) {
        .dhcp-hosts {
            grid-template-columns: 1fr;
        }
    }
    
    /* Mobile dns management */
            .management-buttons {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                max-width: 800px;
                margin: 20px auto;
            }
            
            .management-buttons button {
                width: 100%;
                padding: 10px 15px;
                background-color: #343f48;
                color: #ffd700;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                transition: background-color 0.3s ease;
            }
            
            .management-buttons button:hover {
                background-color: #45a049;
                color: yellow;
            }
            
            @media (max-width: 600px) {
                .management-buttons {
                    grid-template-columns: 1fr;
                }
            }
    
    </style>
</head>
<body>
    <div class="page-container">
        <div class="content-wrap">
            <h1>DHCP/DNS Dashboard</h1>
            {% with messages = get_flashed_messages() %}
                {% if messages %}
                    {% for message in messages %}
                        <div class="flash">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            
            <h2>Current DHCP Hosts</h2>
            <div class="dhcp-hosts">
                {% for mac, hostname, ip in hosts %}
                <div class="host-card">
                    <h3>{{ hostname }}</h3>
                    <div class="host-info">
                        <p><strong>MAC Address:</strong> {{ mac }}</p>
                        <p><strong>IP Address:</strong> {{ ip if ip else 'Dynamic' }}</p>
                    </div>
                    <div class="host-actions">
                    <form method="get" action="{{ url_for('edit_host') }}">
                        <input type="hidden" name="mac" value="{{ mac }}" />
                        <input type="submit" value="Edit" class="edit-button" />
                    </form>
                    <form onsubmit="return confirmRemove('{{ hostname }}')" method="post" action="{{ url_for('remove_host') }}">
                        <input type="hidden" name="mac" value="{{ mac }}" />
                        <input type="submit" value="Remove" class="remove-button" />
                    </form>
                </div>
                </div>
                {% endfor %}
            </div>
            <br>
            <div class="form-container-wrapper">
                <div class="form-container">
                    <h2>Add New Host</h2>
                    <form method="post">
                        <input type="hidden" name="action" value="add" />
                        <label for="mac">MAC Address:</label>
                        <input type="text" id="mac" name="mac" required />
                        <label for="hostname">Hostname:</label>
                        <input type="text" id="hostname" name="hostname" required />
                        <label for="ip">IP Address (optional):</label>
                        <input type="text" id="ip" name="ip" />
                        <input type="submit" value="Add Host" />
                    </form>
                </div>
                
                <div class="form-container">
                    <h2>Wi-Fi Configuration</h2>
                    <form method="post">
                        <input type="hidden" name="action" value="wifi">
                        <label for="ssid">Wi-Fi SSID:</label>
                        <input type="text" id="ssid" name="ssid" required>
                        <label for="password">Wi-Fi Password:</label>
                        <input type="password" id="password" name="password" required>
                        <input type="submit" value="Update Wi-Fi Settings">
                    </form>
                </div>
                
                <div class="form-container">
                    <h2>Access Point Configuration</h2>
                    <form method="post">
                        <input type="hidden" name="action" value="configure_ap">
                        <label for="ap_ssid">AP SSID:</label>
                        <input type="text" id="ap_ssid" name="ap_ssid" value="{{ ap_config.ssid }}" required>
                        <label for="ap_password">AP Password (min 8 chars):</label>
                        <input type="password" id="ap_password" name="ap_password" value="{{ ap_config.password }}" required minlength="8">
                        <label for="ap_channel">Channel:</label>
                        <input type="text" id="ap_channel" name="ap_channel" value="{{ ap_config.channel }}" placeholder="6">
                        <input type="submit" value="Configure Access Point">
                    </form>
                </div>
            </div>
            
            <h2>Access Point Management</h2>
            <p><strong>Status:</strong> <span style="color: {{ 'green' if ap_config.enabled else 'red' }};">{{ 'Active' if ap_config.enabled else 'Inactive' }}</span></p>
            <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="start_ap" />
                <input type="submit" value="Start Access Point" style="background-color: #28a745;" />
            </form>
            <form method="post" style="display: inline; margin-left: 10px;">
                <input type="hidden" name="action" value="stop_ap" />
                <input type="submit" value="Stop Access Point" style="background-color: #dc3545;" />
            </form>
            <form method="post" style="display: inline; margin-left: 10px;">
                <input type="hidden" name="action" value="ap_status" />
                <input type="submit" value="Check AP Status" />
            </form>
            
            <h2>Connection History</h2>
            <div style="margin-bottom: 20px;">
                <p>Track all device connections (wired and wireless) with timestamps, MAC addresses, IP addresses, and hostnames.</p>
                <button onclick="loadConnections()" style="padding: 10px 20px; background-color: #343f48; color: #ffd700; border: none; border-radius: 5px; cursor: pointer; margin-right: 10px;">Refresh Connections</button>
                <button onclick="loadStats()" style="padding: 10px 20px; background-color: #17a2b8; color: white; border: none; border-radius: 5px; cursor: pointer;">View Statistics</button>
            </div>
            <div id="connectionHistory" style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; max-height: 400px; overflow-y: auto;">
                <p>Loading connection history...</p>
            </div>
            <div id="connectionStats" style="display: none; background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-top: 10px;">
            </div>
            
            <h2>DNSMASQ Management</h2>
            <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="restart" />
                <input type="submit" value="Restart DNSMASQ" />
            </form>
            <form method="post" style="display: inline; margin-left: 10px;">
                <input type="hidden" name="action" value="backup" />
                <input type="submit" value="Backup Configuration" />
            </form>
            <form method="post" style="display: inline; margin-left: 10px;">
                <input type="hidden" name="action" value="status" />
                <input type="submit" value="Check DNSMASQ Status" />
            </form>
                                              
            <h2>System Management</h2>
            <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="shutdown" />
                <input type="submit" value="Shutdown Raspberry Pi" class="danger" />
            </form>
        </div>
        
        <footer class="footer">
            <p>&copy; <span id="current-year"></span> JPHsystems. All rights reserved.</p>
        </footer>

        <script>
            document.getElementById('current-year').textContent = new Date().getFullYear();
                                  
            function confirmRemove(hostname) {
                return confirm(`Are you sure you want to remove the host "${hostname}"?`);
            }

            function loadConnections() {
                fetch('/api/connections?limit=50')
                    .then(response => response.json())
                    .then(data => {
                        const container = document.getElementById('connectionHistory');
                        if (data.connections && data.connections.length > 0) {
                            let html = '<h3>Recent Connections (Last 50)</h3>';
                            html += '<table style="width: 100%; border-collapse: collapse;">';
                            html += '<tr style="background-color: #343f48; color: #ffd700;">';
                            html += '<th style="padding: 10px; text-align: left;">Time</th>';
                            html += '<th style="padding: 10px; text-align: left;">Event</th>';
                            html += '<th style="padding: 10px; text-align: left;">MAC Address</th>';
                            html += '<th style="padding: 10px; text-align: left;">IP Address</th>';
                            html += '<th style="padding: 10px; text-align: left;">Hostname</th>';
                            html += '<th style="padding: 10px; text-align: left;">Interface</th>';
                            html += '</tr>';
                            
                            data.connections.forEach((conn, index) => {
                                const bgColor = index % 2 === 0 ? '#ffffff' : '#f2f2f2';
                                const eventColor = conn.event === 'connect' ? '#28a745' : '#dc3545';
                                const time = new Date(conn.timestamp).toLocaleString();
                                
                                html += `<tr style="background-color: ${bgColor};">`;
                                html += `<td style="padding: 8px;">${time}</td>`;
                                html += `<td style="padding: 8px; color: ${eventColor}; font-weight: bold;">${conn.event.toUpperCase()}</td>`;
                                html += `<td style="padding: 8px; font-family: monospace;">${conn.mac}</td>`;
                                html += `<td style="padding: 8px; font-family: monospace;">${conn.ip}</td>`;
                                html += `<td style="padding: 8px;">${conn.hostname}</td>`;
                                html += `<td style="padding: 8px;"><span style="background-color: ${conn.interface === 'wlan0' ? '#17a2b8' : '#6c757d'}; color: white; padding: 2px 8px; border-radius: 3px;">${conn.interface}</span></td>`;
                                html += '</tr>';
                            });
                            
                            html += '</table>';
                            html += `<p style="margin-top: 10px; color: #666;">Total connections in history: ${data.total}</p>`;
                            container.innerHTML = html;
                        } else {
                            container.innerHTML = '<p>No connection history available yet.</p>';
                        }
                    })
                    .catch(error => {
                        document.getElementById('connectionHistory').innerHTML = '<p style="color: red;">Error loading connections: ' + error + '</p>';
                    });
            }

            function loadStats() {
                fetch('/api/connections/stats')
                    .then(response => response.json())
                    .then(data => {
                        const container = document.getElementById('connectionStats');
                        let html = '<h3>Connection Statistics</h3>';
                        html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">';
                        
                        html += `<div style="background-color: white; padding: 15px; border-radius: 5px; text-align: center;">
                            <h4 style="margin: 0; color: #343f48;">Total Connections</h4>
                            <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #28a745;">${data.total_connections}</p>
                        </div>`;
                        
                        html += `<div style="background-color: white; padding: 15px; border-radius: 5px; text-align: center;">
                            <h4 style="margin: 0; color: #343f48;">Total Disconnections</h4>
                            <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #dc3545;">${data.total_disconnections}</p>
                        </div>`;
                        
                        html += `<div style="background-color: white; padding: 15px; border-radius: 5px; text-align: center;">
                            <h4 style="margin: 0; color: #343f48;">Wireless Connections</h4>
                            <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #17a2b8;">${data.wireless_connections}</p>
                        </div>`;
                        
                        html += `<div style="background-color: white; padding: 15px; border-radius: 5px; text-align: center;">
                            <h4 style="margin: 0; color: #343f48;">Wired Connections</h4>
                            <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #6c757d;">${data.wired_connections}</p>
                        </div>`;
                        
                        html += `<div style="background-color: white; padding: 15px; border-radius: 5px; text-align: center;">
                            <h4 style="margin: 0; color: #343f48;">Unique Devices</h4>
                            <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #ffc107;">${data.unique_devices}</p>
                        </div>`;
                        
                        html += `<div style="background-color: white; padding: 15px; border-radius: 5px; text-align: center;">
                            <h4 style="margin: 0; color: #343f48;">Currently Active</h4>
                            <p style="font-size: 24px; font-weight: bold; margin: 10px 0; color: #28a745;">${data.currently_active}</p>
                        </div>`;
                        
                        html += '</div>';
                        container.innerHTML = html;
                        container.style.display = 'block';
                    })
                    .catch(error => {
                        document.getElementById('connectionStats').innerHTML = '<p style="color: red;">Error loading statistics: ' + error + '</p>';
                        document.getElementById('connectionStats').style.display = 'block';
                    });
            }

            // Load connections on page load
            window.addEventListener('load', function() {
                loadConnections();
            });

        </script>
    </div>
</body>
</html>
    ''', hosts=hosts, ap_config=ap_config)


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
