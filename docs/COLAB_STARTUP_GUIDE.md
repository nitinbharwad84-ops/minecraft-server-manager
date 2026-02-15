# 🚀 Google Colab Startup Guide

To run the Minecraft Server Manager on Google Colab with **Google Drive Persistence**, use this script.

## 📋 Instructions
1. Open [Google Colab](https://colab.research.google.com/).
2. Create a **New Notebook**.
3. Copy the code below into the first cell.
4. Run the cell (Play button).
5. Authorize Google Drive access when prompted.
6. Click the **Cloudflare URL** (e.g., `https://...trycloudflare.com`) to manage your server!

## 💻 The Magic Script
*(Copy and paste this entire block)*

```python
# @title 🚀 Launch Minecraft Server (with Google Drive Backup)
# @markdown This script will auto-mount Drive and start the Server Manager.

from google.colab import drive
import os

# 1. Mount Drive
print("📂 Mounting Google Drive...")
drive.mount('/content/drive')

# 2. Clone/Update Code
if not os.path.exists('/content/minecraft-server-manager'):
    print("📥 Cloning repository...")
    !git clone https://github.com/nitinbharwad84-ops/minecraft-server-manager.git
    %cd /content/minecraft-server-manager
else:
    print("🔄 Updating repository...")
    %cd /content/minecraft-server-manager
    !git pull

# 3. Install Dependencies
print("📦 Installing dependencies...")
!pip install -q -r requirements.txt

# 4. Run Server
print("🚀 Starting Server Manager...")
# The script itself handles the symlinking to Drive automatically now!
!python web_ui.py
```

## ⚠️ Important Notes
- **Keep the tab open**: The server runs as long as the Colab tab is open.
- **Persistence**: All your world data is saved to `/content/drive/MyDrive/MinecraftServer`.
- **Restarting**: If you close the tab, just re-open Colab and run this script again. Your world will be exactly where you left it! 
