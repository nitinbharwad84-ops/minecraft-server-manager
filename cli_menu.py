#!/usr/bin/env python3
"""
Interactive CLI Menu for Minecraft Server Manager
Works perfectly in Colab and terminals without TUI support
"""
import asyncio
from server_manager import ServerManager
import aiohttp

def print_header():
    print("\n" + "="*60)
    print("⛏️  MINECRAFT SERVER MANAGER - INTERACTIVE CLI")
    print("="*60 + "\n")

def print_menu():
    print("\n📋 MAIN MENU:")
    print("  1. 📊 Show Server Status")
    print("  2. ☕ Java Management")
    print("  3. 📜 EULA Management")
    print("  4. 🚀 Server Control")
    print("  5. ⚙️  Settings")
    print("  6. 🧩 Plugin Management")
    print("  0. ❌ Exit")
    print()

def java_menu(sm):
    """Java management submenu"""
    print("\n☕ JAVA MANAGEMENT:")
    print("  1. List installed Java versions")
    print("  2. Detect system Java")
    print("  3. Install Java 17")
    print("  4. Install Java 21")
    print("  5. Set active Java version")
    print("  0. Back to main menu")
    
    choice = input("\nChoice: ").strip()
    
    if choice == "1":
        jm = sm.java_manager
        active = jm.get_active()
        print(f"\n✅ Active: {active.version if active else 'None (system default)'}")
        print("\n📦 Installed versions:")
        for java in jm.list_installed():
            status = "✓ ACTIVE" if active and java.version == active.version else ""
            print(f"  - Java {java.version}: {java.path} {status}")
    
    elif choice == "2":
        print("\n🔍 Detecting system Java...")
        found = sm.java_manager.detect_system_java()
        print(f"✅ Found {len(found)} Java installation(s)")
        for java in found:
            print(f"  - Java {java.version}: {java.path}")
    
    elif choice == "3":
        print("\n⬇️  Installing Java 17...")
        asyncio.run(_install_java(sm, 17))
    
    elif choice == "4":
        print("\n⬇️  Installing Java 21...")
        asyncio.run(_install_java(sm, 21))
    
    elif choice == "5":
        ver = input("Enter Java version to activate (17/21): ").strip()
        try:
            if sm.java_manager.set_active(int(ver)):
                print(f"✅ Java {ver} set as active")
            else:
                print("❌ Failed to set active version")
        except ValueError:
            print("❌ Invalid version")

async def _install_java(sm, version):
    """Install Java asynchronously"""
    async with aiohttp.ClientSession() as session:
        result = await sm.java_manager.download_java(version, session)
        if result:
            sm.java_manager.set_active(version)
            print(f"✅ Java {version} installed and activated!")
        else:
            print(f"❌ Failed to install Java {version}")

def eula_menu(sm):
    """EULA management submenu"""
    print("\n📜 EULA MANAGEMENT:")
    print("  1. Check EULA status")
    print("  2. Accept EULA")
    print("  3. Decline EULA")
    print("  0. Back to main menu")
    
    choice = input("\nChoice: ").strip()
    
    if choice == "1":
        result = sm.eula_manager.check_eula()
        if result.success and result.data.get('accepted'):
            print("\n✅ EULA is ACCEPTED")
        else:
            print("\n❌ EULA is NOT accepted")
            print("\n📄 Minecraft End User License Agreement:")
            print("By accepting, you agree to Mojang's EULA at:")
            print("https://www.minecraft.net/en-us/eula")
    
    elif choice == "2":
        confirm = input("\nAccept Minecraft EULA? (yes/no): ").strip().lower()
        if confirm == "yes":
            result = sm.eula_manager.accept_eula()
            if result.success:
                print("✅ EULA accepted!")
            else:
                print(f"❌ Error: {result.error}")
        else:
            print("❌ EULA not accepted")
    
    elif choice == "3":
        result = sm.eula_manager.decline_eula()
        print("❌ EULA declined")

def server_control_menu(sm):
    """Server control submenu"""
    status = sm.get_server_status()
    is_running = status.get('running', False)
    
    print(f"\n🚀 SERVER CONTROL (Status: {'🟢 Running' if is_running else '🔴 Stopped'}):")
    if not is_running:
        print("  1. ▶️  Start server")
    else:
        print("  1. ⏹️  Stop server")
        print("  2. 🔄 Restart server")
        print("  3. 💬 Send command")
    print("  4. 📋 View logs (last 20 lines)")
    print("  5. 💾 Create backup")
    print("  0. Back to main menu")
    
    choice = input("\nChoice: ").strip()
    
    if choice == "1":
        if not is_running:
            # Check EULA first
            eula_result = sm.eula_manager.check_eula()
            if not eula_result.success or not eula_result.data.get('accepted'):
                print("\n❌ Cannot start server: EULA not accepted!")
                print("Go to EULA Management to accept the EULA first.")
                return
            
            print("\n▶️  Starting server...")
            result = sm.start_server()
            if result.get('success'):
                print("✅ Server started!")
            else:
                print(f"❌ Error: {result.get('error')}")
        else:
            print("\n⏹️  Stopping server...")
            result = sm.stop_server()
            if result.get('success'):
                print("✅ Server stopped!")
            else:
                print(f"❌ Error: {result.get('error')}")
    
    elif choice == "2" and is_running:
        print("\n🔄 Restarting server...")
        result = sm.restart_server()
        if result.get('success'):
            print("✅ Server restarted!")
        else:
            print(f"❌ Error: {result.get('error')}")
    
    elif choice == "3" and is_running:
        cmd = input("Enter command (e.g., 'say Hello'): ").strip()
        if cmd:
            result = sm.send_command(cmd)
            if result.get('success'):
                print(f"✅ Command sent: {cmd}")
            else:
                print(f"❌ Error: {result.get('error')}")
    
    elif choice == "4":
        logs = sm.get_log_tail(20)
        print("\n📋 Last 20 log lines:")
        print("-" * 60)
        for line in logs:
            print(line)
        print("-" * 60)
    
    elif choice == "5":
        print("\n💾 Creating backup...")
        result = sm.backup_world()
        if result.get('success'):
            print(f"✅ Backup created: {result.get('backup_path')}")
        else:
            print(f"❌ Error: {result.get('error')}")

def settings_menu(sm):
    """Settings submenu"""
    print("\n⚙️  SETTINGS:")
    print("  1. View current settings")
    print("  2. Change server type")
    print("  3. Change MC version")
    print("  4. Change RAM allocation")
    print("  5. Change max players")
    print("  0. Back to main menu")
    
    choice = input("\nChoice: ").strip()
    
    cfg = sm.get_server_config()
    
    if choice == "1":
        print("\n📊 Current Settings:")
        for key, value in cfg.items():
            print(f"  {key}: {value}")
    
    elif choice == "2":
        print("\nServer types: vanilla, paper, spigot, purpur, fabric, forge")
        new_type = input("Enter server type: ").strip()
        sm.update_server_config(type=new_type)
        print(f"✅ Server type changed to: {new_type}")
    
    elif choice == "3":
        new_ver = input("Enter MC version (e.g., 1.20.1): ").strip()
        sm.update_server_config(version=new_ver)
        print(f"✅ MC version changed to: {new_ver}")
    
    elif choice == "4":
        ram = input("Enter RAM in MB (e.g., 2048): ").strip()
        try:
            sm.update_server_config(ram=int(ram))
            print(f"✅ RAM changed to: {ram} MB")
        except ValueError:
            print("❌ Invalid RAM value")
    
    elif choice == "5":
        players = input("Enter max players: ").strip()
        try:
            sm.update_server_config(max_players=int(players))
            print(f"✅ Max players changed to: {players}")
        except ValueError:
            print("❌ Invalid number")

def show_status(sm):
    """Show detailed server status"""
    status = sm.get_server_status()
    resources = sm.get_system_resources()
    cfg = sm.get_server_config()
    
    print("\n📊 SERVER STATUS:")
    print(f"  Status: {'🟢 Running' if status.get('running') else '🔴 Stopped'}")
    print(f"  Type: {cfg.get('type')} {cfg.get('version')}")
    print(f"  Java: {cfg.get('java_version')}")
    print(f"  EULA: {'✅ Accepted' if cfg.get('eula_accepted') else '❌ Not Accepted'}")
    print(f"  Players: {status.get('player_count', 0)}/{cfg.get('max_players')}")
    
    print("\n💻 SYSTEM RESOURCES:")
    print(f"  CPU: {resources.get('cpu_percent', 0)}%")
    print(f"  RAM: {resources.get('ram_used_mb', 0)} / {resources.get('ram_total_mb', 0)} MB")
    print(f"  Disk: {resources.get('disk_used_gb', 0)} / {resources.get('disk_total_gb', 0)} GB")

def main():
    """Main CLI loop"""
    print_header()

    # Google Drive persistence (Colab only, no-op elsewhere)
    try:
        from web_ui import setup_colab_persistence
        setup_colab_persistence()
    except Exception:
        pass

    print("Loading server manager...")
    sm = ServerManager('config.json')
    print("✅ Server manager loaded!")
    
    while True:
        print_menu()
        choice = input("Enter choice: ").strip()
        
        if choice == "0":
            print("\n👋 Goodbye!")
            break
        elif choice == "1":
            show_status(sm)
        elif choice == "2":
            java_menu(sm)
        elif choice == "3":
            eula_menu(sm)
        elif choice == "4":
            server_control_menu(sm)
        elif choice == "5":
            settings_menu(sm)
        elif choice == "6":
            print("\n🧩 Plugin management coming soon...")
        else:
            print("\n❌ Invalid choice!")
        
        input("\nPress Enter to continue...")

if __name__ == '__main__':
    main()
