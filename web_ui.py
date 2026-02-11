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
        result = sm.eula_manager.check_eula()
        return jsonify({
            'success': result.success,
            'accepted': result.data.get('accepted', False) if result.success else False
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/eula/accept', methods=['POST'])
def api_eula_accept():
    """Accept EULA"""
    try:
        result = sm.eula_manager.accept_eula()
        return jsonify({
            'success': result.success,
            'message': result.message
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/eula/decline', methods=['POST'])
def api_eula_decline():
    """Decline EULA"""
    try:
        result = sm.eula_manager.decline_eula()
        return jsonify({
            'success': result.success,
            'message': result.message
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/start', methods=['POST'])
def api_server_start():
    """Start server"""
    try:
        result = sm.start_server()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/stop', methods=['POST'])
def api_server_stop():
    """Stop server"""
    try:
        result = sm.stop_server()
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/server/restart', methods=['POST'])
def api_server_restart():
    """Restart server"""
    try:
        result = sm.restart_server()
        return jsonify(result)
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

def run_server(port=5000):
    """Run Flask server"""
    import os
    from threading import Thread

    is_colab = os.path.exists('/content')

    if is_colab:
        # Start Flask in a background thread so the cell doesn't block
        thread = Thread(target=lambda: app.run(host='0.0.0.0', port=port, debug=False, threaded=True), daemon=True)
        thread.start()

        import time
        time.sleep(2)  # Wait for server to start

        # Use Colab's built-in proxy
        from google.colab import output
        print("\n" + "=" * 60)
        print("✅ WEB UI IS READY!")
        print("=" * 60)
        print(f"\n🌐 Opening dashboard in a new tab...\n")
        output.serve_kernel_port_as_window(port, path='/')
        print(f"📱 If the window didn't open, click this link:")
        print(f"   https://localhost:{port}")
        print(f"\n💡 Or run this in a NEW cell to open it:")
        print(f'   from google.colab import output')
        print(f'   output.serve_kernel_port_as_window({port})')
        print("\n⚠️  Keep THIS cell running! Stopping it kills the server.")
        print("=" * 60)

        # Keep the cell alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n👋 Server stopped.")
    else:
        print(f"\n🚀 Starting web server on http://localhost:{port}")
        print(f"   Open this URL in your browser!\n")
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

if __name__ == '__main__':
    import sys
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 5000
    run_server(port=port)
