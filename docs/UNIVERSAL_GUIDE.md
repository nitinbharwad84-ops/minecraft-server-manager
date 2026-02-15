# 🌍 Universal Usage Guide

This Minecraft Server Manager is designed to run **anywhere**.

## 🚀 Supported Environments

### 1. GitHub Codespaces (Recommended)
**Best for:** Development, Testing, Temporary usage.
1. Open your repo in a Codespace.
2. Run: `python web_ui.py`
3. Wait for the **Cloudflare URL** in the terminal (e.g., `https://example.trycloudflare.com`).
4. Click the link to open the Dashboard.

### 2. Google Colab
**Best for:** Free high-performance (CPU/RAM) hosting.
1. Upload `web_ui.py` and other files to Colab.
2. Run the script.
3. Click the **Cloudflare URL** printed in the output.
4. **Important**: Keep the Colab tab open to keep the server running.

### 3. Google IDX / Replit
**Best for:** Quick web-based development.
1. Run `python web_ui.py`.
2. Access the Web UI via the **Cloudflare URL** in the console.

### 4. Local PC / VPS
**Best for:** 24/7 Hosting, Perfomance.
1. Run `python web_ui.py`.
2. Access via `http://localhost:5000` OR the **Cloudflare URL** (for remote access).

---

## 🎮 How to Connect Friends (Multiplayer)
The Web UI tunnel (`trycloudflare.com`) is only for **managing** the server.
To let friends join the game:

1. Open the **Dashboard**.
2. Go to the **Connect** tab.
3. Click **🚀 Start Playit.gg Tunnel**.
4. Give the generated **Public IP** (e.g., `lime-cafe.gl.joinmc.link`) to your friends.

---

## 📂 File Manager
Manage your server files directly from the browser:
- **Upload**: Drag & drop plugins/mods.
- **Edit**: Modify `server.properties` or standard configs.
- **Delete**: Remove unwanted files.

---

## ⚡ Troubleshooting
- **Tunnel not starting?**
  - Check your internet connection.
  - Restart the script.
- **Server laggy?**
  - Colab/Codespaces have limited resources. Allocate less RAM (e.g., 4GB) in the Settings tab.
