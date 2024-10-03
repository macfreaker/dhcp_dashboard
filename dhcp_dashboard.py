import flask
from flask import Flask, request, render_template_string, flash, redirect, url_for
import subprocess
import re
import shutil
from datetime import datetime
import logging
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a real secret key

DNSMASQ_CONF = '/etc/dnsmasq.conf'

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
                <html>
                <head>
                    <title>Confirm Shutdown</title>
                    <style>
                        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
                        .warning { color: red; font-weight: bold; }

                        h1 { color: #343f48}

                        input[type=button], input[type=submit], input[type=reset] {
                        background-color: #343f48;
                        font-size: 14px;
                        border: none; border-radius: 10px;
                        color: white;
                        padding: 10px 10px;
                        text-decoration: none;
                        margin: 4px 2px;
                        cursor: pointer;
                    }

                    </style>
                </head>
                <body>
                    <h1>Confirm Shutdown</h1>
                    <p class="warning">Are you sure you want to shut down the Raspberry Pi?</p>
                    <p>This will terminate all services and you won't be able to access the device remotely until it's manually restarted.</p>
                    <form method="post">
                        <input type="hidden" name="action" value="confirm_shutdown">
                        <input type="submit" value="Yes, Shut Down">
                    </form><br>
                    <a href="{{ url_for('dashboard') }}">Cancel</a>
                </body>
                </html>
            ''')
        elif action == 'confirm_shutdown':
            flash("Shutting down the Raspberry Pi...")
            shutdown_pi()
    
    hosts = read_dhcp_hosts()
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
        table { border-collapse: collapse; width: 50%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: center; }
        th { background-color: #f2f2f2; }
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
            <table>
                <tr>
                    <th>MAC Address</th>
                    <th>Hostname</th>
                    <th>IP Address</th>
                    <th>Action</th>
                </tr>
                {% for mac, hostname, ip in hosts %}
                <tr>
                    <td>{{ mac }}</td>
                    <td>{{ hostname }}</td>
                    <td>{{ ip if ip else 'Dynamic' }}</td>
                    <td>
                        <form method="get" action="{{ url_for('edit_host') }}" style="display: inline;">
                            <input type="hidden" name="mac" value="{{ mac }}" />
                            <input type="submit" value="Edit" />
                        </form>
                        <form onsubmit="return confirmRemove('{{ hostname }}')" method="post" action="{{ url_for('remove_host') }}" style="display: inline;">
                            <input type="hidden" name="mac" value="{{ mac }}" />
                            <input type="submit" value="Remove" />
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </table><br>
            
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

        </script>
    </div>
</body>
</html>
    ''', hosts=hosts)

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
