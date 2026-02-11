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
            
            # Check for public address
            # Log format varies, look for .gl.joinmc.link or similar
            if '.gl.joinmc.link' in clean_line or '.pl.local' in clean_line or 'tunnel address' in clean_line.lower():
                 pass # Currently playit might not print final address in clear text easily on new versions without claim

            # Keep looking for address in specialized format if updated
    
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
# SERVER RUNNER
# ============================================================================

def run_server(port=5000):
    """Run Flask server"""
    import os
    from threading import Thread

    is_colab = os.path.exists('/content')

    if is_colab:
        # Start Flask in background thread
        thread = Thread(
            target=lambda: app.run(host='127.0.0.1', port=port, debug=False, threaded=True),
            daemon=True
        )
        thread.start()

        import time, subprocess, re
        time.sleep(2)

        # Install cloudflared (free, no account needed)
        print("🔧 Setting up tunnel (free, no signup needed)...")
        subprocess.run(
            ["wget", "-q", "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64", "-O", "/usr/local/bin/cloudflared"],
            check=True, capture_output=True
        )
        subprocess.run(["chmod", "+x", "/usr/local/bin/cloudflared"], check=True, capture_output=True)

        # Start cloudflared tunnel
        proc = subprocess.Popen(
            ["/usr/local/bin/cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        # Wait for the public URL
        public_url = None
        for _ in range(30):
            line = proc.stderr.readline()
            match = re.search(r'(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)', line)
            if match:
                public_url = match.group(1)
                break
            time.sleep(0.5)

        if public_url:
            print("\n" + "=" * 60)
            print("✅ WEB UI IS READY!")
            print("=" * 60)
            print(f"\n🌐 OPEN THIS LINK IN YOUR BROWSER:\n")
            print(f"   {public_url}")
            print(f"\n📱 Works on phone too! Share with anyone!")
            print(f"\n⚠️  Keep this cell running!")
            print("=" * 60 + "\n")
        else:
            print(f"\n⚠️  Tunnel setup failed. Try: http://localhost:{port}")

        # Keep alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            proc.kill()
            print("\n👋 Server stopped.")
    else:
        print(f"\n🚀 Web UI: http://localhost:{port}\n")
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

if __name__ == '__main__':
    import sys
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 5000
    run_server(port=port)
