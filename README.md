# ⛏️ Minecraft Server Manager

A powerful, terminal-based Minecraft server management tool built with [Textual](https://textual.textualize.io/) and [Rich](https://rich.readthedocs.io/). Designed to run seamlessly on **Google Colab**, **Google IDX**, and **local machines**.

---

## ✨ Features

- 🖥️ **Beautiful TUI Dashboard** – Full terminal UI with real-time server stats, logs, and controls
- ☕ **Java Version Manager** – Auto-detect, download, and switch between Java 8/11/17/21 (Adoptium)
- 🔌 **Plugin Manager** – Search, install, update, and validate plugins from Modrinth, Hangar & SpigotMC
- 📝 **File Editor** – Edit `server.properties`, configs, and YAML files directly in the terminal
- 📜 **EULA Manager** – One-click Minecraft EULA acceptance
- 🌐 **Remote Control** – Manage servers over SSH with Paramiko
- 🏗️ **Multi-Server Support** – Paper, Spigot, Purpur, Fabric, Forge, Vanilla, and more
- 🔄 **Auto-Environment Detection** – Detects Google Colab, IDX, or local and adjusts paths/behavior
- 💾 **Backup & Restore** – World and config backup management
- 📊 **System Monitoring** – CPU, RAM, disk, and network stats via psutil

---

## 📋 Supported Server Software

| Server Type | Description                        | Plugin Support |
|-------------|------------------------------------|----------------|
| **Paper**   | High-performance Spigot fork       | Bukkit/Spigot/Paper plugins |
| **Spigot**  | Optimized CraftBukkit              | Bukkit/Spigot plugins |
| **Purpur**  | Paper fork with extra features     | Bukkit/Spigot/Paper plugins |
| **Fabric**  | Lightweight modding platform       | Fabric mods |
| **Forge**   | Community modding platform         | Forge mods |
| **Vanilla** | Official Mojang server             | None |
| **Velocity**| Modern proxy server                | Velocity plugins |
| **BungeeCord** | Legacy proxy server             | BungeeCord plugins |

---

## 🎮 Supported Minecraft Versions

- **Java Edition**: 1.8.x – 1.21.x (latest)
- **Java Requirements**:
  - Java 8 → MC 1.8.x – 1.12.x
  - Java 11 → MC 1.12.x – 1.16.x
  - Java 17 → MC 1.17.x – 1.20.4
  - Java 21 → MC 1.20.5+

---

## 🚀 Installation

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/your-username/minecraft-server-manager.git
cd minecraft-server-manager

# Install dependencies
pip install -r requirements.txt

# Launch the manager
python main.py
```

### Google Colab

```python
# Run in a Colab cell
!git clone https://github.com/your-username/minecraft-server-manager.git
%cd minecraft-server-manager
!pip install -r requirements.txt
!python main.py --environment colab
```

### Google IDX

```bash
# In the IDX terminal
git clone https://github.com/your-username/minecraft-server-manager.git
cd minecraft-server-manager
pip install -r requirements.txt
python main.py --environment idx
```

---

## 🎯 Usage

### Basic Commands

```bash
# Launch with default settings
python main.py

# Specify server type and version
python main.py --type paper --version 1.20.4

# Force a specific environment
python main.py --environment colab

# Use a custom config file
python main.py --config /path/to/config.json

# Run in headless mode (no TUI)
python main.py --headless
```

### TUI Navigation

| Key           | Action                    |
|---------------|---------------------------|
| `Tab`         | Switch between panels     |
| `S`           | Start/Stop server         |
| `J`           | Open Java manager         |
| `P`           | Open Plugin manager       |
| `E`           | Open File editor          |
| `L`           | View server logs          |
| `B`           | Create backup             |
| `Q`           | Quit application          |
| `Ctrl+C`      | Force quit                |

---

## ⚙️ Configuration

Edit `config.json` to customize your server:

```json
{
  "server": {
    "type": "paper",
    "version": "1.20.4",
    "ram": 4096,
    "java_version": 21,
    "max_players": 50
  }
}
```

### JVM Flags

Pre-configured JVM flag profiles:

- **default** – Aikar's optimized G1GC flags (recommended for most servers)
- **low_memory** – Serial GC for constrained environments (Colab free tier)
- **high_performance** – ZGC for high-RAM dedicated servers

---

## 🗂️ Project Structure

```
minecraft_server_manager/
├── main.py                     # Application entry point & CLI argument parsing
├── server_manager.py           # Core server lifecycle management
├── server_types.py             # Server type definitions & download logic
├── java_manager.py             # Java version detection, download, switching
├── plugin_manager.py           # Plugin installation & management
├── plugin_validator.py         # Plugin compatibility validation
├── plugin_apis.py              # API clients for Modrinth, Hangar, SpigotMC
├── file_editor.py              # Server config file editing logic
├── eula_manager.py             # Minecraft EULA acceptance handling
├── ui/
│   ├── dashboard.py            # Main TUI dashboard layout
│   ├── java_panel.py           # Java manager panel
│   ├── plugin_panel.py         # Plugin manager panel
│   ├── file_editor_panel.py    # File editor panel
│   ├── widgets.py              # Reusable TUI widgets
│   └── styles.css              # Textual CSS styles
├── remote_controller.py        # SSH-based remote server management
├── config.json                 # Server configuration
├── installed_plugins.json      # Plugin registry
├── java_versions.json          # Java version registry
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License. See `LICENSE` for details.

---

## ⚠️ Disclaimer

This project is not affiliated with Mojang Studios or Microsoft. Minecraft is a trademark of Mojang Studios. By using this tool and accepting the EULA, you agree to the [Minecraft EULA](https://www.minecraft.net/en-us/eula).
