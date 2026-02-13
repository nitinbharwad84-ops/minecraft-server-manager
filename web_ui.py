"""
Web UI for Minecraft Server Manager
Modern Flask-based web interface
"""
from flask import Flask, render_template, jsonify, request
from server_manager import ServerManager
import asyncio
import aiohttp
from threading import Thread
import os

app = Flask(__name__)
sm = ServerManager('config.json')

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/')
def index():
    """Main dashboard"""
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    """Get server status"""
    try:
        status = sm.get_server_status()
        resources = sm.get_system_resources()
        config = sm.get_server_config()
        
        return jsonify({
            'success': True,
            'status': status,
            'resources': resources,
            'config': config
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/java/list')
def api_java_list():
    """List Java installations"""
    try:
        jm = sm.java_manager
        active = jm.get_active()
        installed = jm.list_installed()
        
        return jsonify({
            'success': True,
            'active': {
                'version': active.version if active else None,
                'path': str(active.path) if active else None
            },
            'installed': [
                {
                    'version': j.version,
                    'path': str(j.path),
                    'vendor': j.vendor,
                    'is_active': active and j.version == active.version
                }
                for j in installed
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/java/detect', methods=['POST'])
def api_java_detect():
    """Detect system Java"""
    try:
        found = sm.java_manager.detect_system_java()
        return jsonify({
            'success': True,
            'found': len(found),
            'versions': [
                {'version': j.version, 'path': str(j.path)}
                for j in found
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/java/install/<int:version>', methods=['POST'])
def api_java_install(version):
    """Install Java version"""
    try:
        async def _install():
            async with aiohttp.ClientSession() as session:
                result = await sm.java_manager.download_java(version, session)
                if result:
                    sm.java_manager.set_active(version)
                return result
        
        result = asyncio.run(_install())
        return jsonify({
            'success': result,
            'message': f'Java {version} installed!' if result else 'Installation failed'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/java/activate/<int:version>', methods=['POST'])
def api_java_activate(version):
    """Set active Java version"""
    try:
        result = sm.java_manager.set_active(version)
        return jsonify({
            'success': result,
            'message': f'Java {version} activated!' if result else 'Failed to activate'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/eula/status')
def api_eula_status():
    """Check EULA status"""
    try:
        # Use check_eula_status() which returns bool
        accepted = sm.eula_manager.check_eula_status()
        return jsonify({
            'success': True,
            'accepted': accepted
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/eula/accept', methods=['POST'])
def api_eula_accept():
    """Accept EULA"""
    try:
        # Use auto_accept_eula() which returns EulaResult
        result = sm.eula_manager.auto_accept_eula()
        return jsonify({
            'success': result.success,
            'message': result.message,
            'error': result.error
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/eula/decline', methods=['POST'])
def api_eula_decline():
    """Decline EULA"""
    try:
        # Use decline() which returns bool
        success = sm.eula_manager.decline()
        return jsonify({
            'success': success,
            'message': 'EULA declined' if success else 'Failed to decline EULA'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/start', methods=['POST'])
def api_server_start():
    """Start server"""
    try:
        result = sm.start_server()
        # Flask 3.1.0 handles dataclasses, but let's be safe
        return jsonify({
            'success': result.success,
            'message': result.message,
            'error': result.error,
            'details': result.details
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/download', methods=['POST'])
def api_server_download():
    """Download server JAR"""
    try:
        # Use asyncio to run the async download method
        import asyncio
        async def _download():
            async with aiohttp.ClientSession() as session:
                return await sm.download_server(session)
        
        success = asyncio.run(_download())
        return jsonify({
            'success': success,
            'message': 'Server JAR downloaded successfully' if success else 'Failed to download server JAR'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/stop', methods=['POST'])
def api_server_stop():
    """Stop server"""
    try:
        result = sm.stop_server()
        return jsonify({
            'success': result.success,
            'message': result.message,
            'error': result.error,
            'details': result.details
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/restart', methods=['POST'])
def api_server_restart():
    """Restart server"""
    try:
        result = sm.restart_server()
        return jsonify({
            'success': result.success,
            'message': result.message,
            'error': result.error,
            'details': result.details
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/command', methods=['POST'])
def api_server_command():
    """Send server command"""
    try:
        data = request.json
        cmd = data.get('command', '')
        if not cmd:
            return jsonify({'success': False, 'error': 'No command provided'}), 400
        
        result = sm.send_command(cmd)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/logs')
def api_server_logs():
    """Get server logs"""
    try:
        lines = int(request.args.get('lines', 50))
        logs = sm.get_log_tail(lines)
        return jsonify({
            'success': True,
            'logs': logs
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/backup', methods=['POST'])
def api_server_backup():
    """Create backup"""
    try:
        result = sm.backup_world()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/get')
def api_settings_get():
    """Get all settings"""
    try:
        config = sm.get_server_config()
        return jsonify({
            'success': True,
            'config': config
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/update', methods=['POST'])
def api_settings_update():
    """Update settings"""
    try:
        data = request.json
        sm.update_server_config(**data)
        return jsonify({
            'success': True,
            'message': 'Settings updated!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# TUNNEL MANAGER (Playit.gg)
# ============================================================================

class TunnelManager:
    def __init__(self):
        self.process = None
        self.claim_url = None
        self.public_address = None
        self.log_lines = []
    
    def start_tunnel(self):
        """Start playit.gg tunnel"""
        if self.process and self.process.poll() is None:
            return {'success': True, 'message': 'Tunnel already running', 'address': self.public_address, 'claim_url': self.claim_url}

        import subprocess
        import threading
        
        # Download playit if missing
        if not os.path.exists('playit'):
            print("Downloading playit...")
            subprocess.run(['wget', '-q', 'https://github.com/playit-cloud/playit-agent/releases/download/v0.15.26/playit-linux-amd64', '-O', 'playit'], check=True)
            subprocess.run(['chmod', '+x', 'playit'], check=True)

        # Start playit
        self.process = subprocess.Popen(
            ['./playit'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Start log monitor
        threading.Thread(target=self._monitor_output, daemon=True).start()
        
        return {'success': True, 'message': 'Tunnel started. Wait for address...'}

    def _monitor_output(self):
        """Read playit logs to find URL and address"""
        if not self.process: return
            
        for line in iter(self.process.stdout.readline, ''):
            clean_line = line.strip()
            self.log_lines.append(clean_line)
            if len(self.log_lines) > 50: self.log_lines.pop(0)

            # Check for claim URL
            if 'claim details' in clean_line.lower() or 'visit link' in clean_line.lower():
                # Extract URL
                import re
                match = re.search(r'https://playit\.gg/claim/[a-zA-Z0-9]+', clean_line)
                if match:
                    self.claim_url = match.group(0)
            
            # Check for generic success message with address
            # Example: "tunnel running at: grand-mountain.gl.joinmc.link"
            # Example: "public address: ... details ..."
            lower_line = clean_line.lower()
            
            # Pattern 1: Standard playit domains
            import re
            domain_match = re.search(r'([a-z0-9-]+\.(?:gl\.joinmc\.link|ply\.gg|playit\.gg|gl\.at\.ply\.gg))', clean_line)
            if domain_match:
                self.public_address = domain_match.group(1)
                print(f"🎯 FOUND ADDRESS: {self.public_address}") # Print to visible console for debugging

            # Pattern 2: "tunnel address: <ADDRESS>"
            if "tunnel address" in lower_line:
                parts = clean_line.split("address")
                if len(parts) > 1:
                    candidate = parts[1].strip().strip(":").strip()
                    if "." in candidate:
                        self.public_address = candidate
            
    def get_status(self):
        return {
            'running': self.process is not None and self.process.poll() is None,
            'claim_url': self.claim_url,
            'public_address': self.public_address,
            'logs': self.log_lines[-10:]
        }

tunnel_mgr = TunnelManager()

@app.route('/api/tunnel/start', methods=['POST'])
def api_tunnel_start():
    return jsonify(tunnel_mgr.start_tunnel())

@app.route('/api/tunnel/status')
def api_tunnel_status():
    return jsonify(tunnel_mgr.get_status())

# ============================================================================
# FILE MANAGER API
# ============================================================================

def safe_join(path):
    """Ensure path is within server directory"""
    # Create server dir if not explicitly existing to avoid errors, though it should
    if not os.path.exists("server"):
        os.makedirs("server")
    base = os.path.abspath("server")
    # Handle empty path as root
    if not path or path == '.' or path == '/':
        target = base
    else:
        target = os.path.abspath(os.path.join(base, path.strip("/")))
    
    if not target.startswith(base):
        raise ValueError("Access denied: Path outside server directory")
    return target

@app.route('/api/files/list')
def api_files_list():
    try:
        path_param = request.args.get('path', '')
        full_path = safe_join(path_param)
        
        if not os.path.exists(full_path):
            return jsonify({'success': False, 'error': 'Path does not exist'})
            
        items = []
        for entry in os.scandir(full_path):
            stat = entry.stat()
            items.append({
                'name': entry.name,
                'is_dir': entry.is_dir(),
                'size': stat.st_size,
                'modified': stat.st_mtime
            })
            
        # Sort: directories first, then alphabetical
        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))
        
        return jsonify({'success': True, 'items': items, 'path': path_param})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/files/content')
def api_files_content():
    try:
        path_param = request.args.get('path', '')
        full_path = safe_join(path_param)
        
        if not os.path.isfile(full_path):
            return jsonify({'success': False, 'error': 'File not found'})
            
        # Check size (limit to 1MB for editing)
        if os.path.getsize(full_path) > 1024 * 1024:
            return jsonify({'success': False, 'error': 'File too large to edit'})
            
        with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            
        return jsonify({'success': True, 'content': content})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/files/save', methods=['POST'])
def api_files_save():
    try:
        data = request.json
        path_param = data.get('path', '')
        content = data.get('content', '')
        full_path = safe_join(path_param)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/files/delete', methods=['POST'])
def api_files_delete():
    try:
        data = request.json
        path_param = data.get('path', '')
        full_path = safe_join(path_param)
        
        if os.path.isdir(full_path):
            import shutil
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/files/upload', methods=['POST'])
def api_files_upload():
    try:
        path_param = request.form.get('path', '')
        file = request.files.get('file')
        
        if not file:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        # Ensure path exists
        upload_dir = safe_join(path_param)
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
            
        full_path = os.path.join(upload_dir, file.filename)
        file.save(full_path)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/files/create_folder', methods=['POST'])
def api_files_create_folder():
    try:
        path_param = request.json.get('path', '')
        name = request.json.get('name', '')
        if not name:
             return jsonify({'success': False, 'error': 'Folder name required'})

        parent_dir = safe_join(path_param)
        full_path = os.path.join(parent_dir, name)
        
        os.makedirs(full_path, exist_ok=True)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============================================================================
# SERVER RUNNER
# ============================================================================

# ============================================================================
# UNIVERSAL LAUNCHER
# ============================================================================

# ============================================================================
# UNIVERSAL LAUNCHER (CLOUDFLARE TUNNEL MODE)
# ============================================================================

def run_server(port=5000):
    """
    Universal runner that ALWAYS uses Cloudflare Tunnel to provide a public URL.
    Works on: Local, Colab, Codespaces, IDX, Replit, Docker, VPS.
    """
    import os
    import sys
    from threading import Thread
    import time
    
    # allow disabling tunnel via env var if really needed
    if os.environ.get('NO_TUNNEL'):
        print(f"\n🚀 Running Locally (Tunnel Disabled)")
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
        return

    print(f"\n🚀 Initializing Server Manager...")
    
    # 1. Start Flask in background thread
    print("   -> Starting Web Server on port", port)
    Thread(target=lambda: app.run(host='127.0.0.1', port=port, debug=False, threaded=True), daemon=True).start()
    
    # Give it a moment to bind
    time.sleep(2)
    
    # 2. Start Cloudflare Tunnel
    start_cloudflared_tunnel(port)
    
    # 3. Keep main thread alive
    keep_alive()

def start_cloudflared_tunnel(port):
    """Downloads and starts cloudflared for free tunneling"""
    import subprocess
    import re
    import time
    import platform
    import shutil
    
    print("   -> Setting up Cloudflare Tunnel...")
    
    # Determine binary name
    system = platform.system()
    binary_name = "cloudflared.exe" if system == "Windows" else "cloudflared"
    
    # Download if missing
    if not os.path.exists(binary_name) and not shutil.which(binary_name):
        print("      Downloading cloudflared...")
        if system == "Windows":
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
            subprocess.run(["curl", "-L", url, "-o", binary_name], check=True)
        elif system == "Darwin": # Mac
             url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64"
             subprocess.run(["curl", "-L", url, "-o", binary_name], check=True)
             subprocess.run(["chmod", "+x", binary_name], check=True)
        else: # Linux
            url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" 
            subprocess.run(["wget", "-q", url, "-O", binary_name], check=True)
            subprocess.run(["chmod", "+x", binary_name], check=True)

    # Use local binary or system binary
    cmd = f"./{binary_name}" if os.path.exists(binary_name) else binary_name

    # Start Tunnel
    try:
        proc = subprocess.Popen(
            [cmd, "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
    except Exception as e:
        print(f"❌ Failed to start cloudflared: {e}")
        return
    
    print("   -> Connecting to Cloudflare network...")
    public_url = None
    
    # Read stderr for the URL (it prints there)
    # We read line by line until we find it
    start_time = time.time()
    while time.time() - start_time < 30: # 30s timeout
        line = proc.stderr.readline()
        if not line:
            if proc.poll() is not None: break
            continue
            
        # Extract URL: https://<random>.trycloudflare.com
        match = re.search(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)', line)
        if match:
            public_url = match.group(1)
            break
            
    if public_url:
        print("\n" + "=" * 60)
        print("✅ SERVER MANAGER IS ONLINE!")
        print("=" * 60)
        print(f"\n🌐 DASHBOARD URL:  {public_url}")
        print(f"\n📱 Share this link to manage the server from anywhere!")
        print("=" * 60 + "\n")
    else:
        print("❌ Could not get Cloudflare URL. Check connectivity.")

def keep_alive():
    """Keep the script running"""
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Stopping...")

if __name__ == '__main__':
    import sys
    # Allow port override
    port = 5000
    if len(sys.argv) > 1:
        for i, arg in enumerate(sys.argv):
            if arg == '--port' and i + 1 < len(sys.argv):
                port = int(sys.argv[i+1])
                
    run_server(port)
