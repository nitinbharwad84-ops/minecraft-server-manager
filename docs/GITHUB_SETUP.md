# 🚀 Complete GitHub Codespaces Setup Guide

This guide will walk you through setting up the Minecraft Server Manager from scratch on **GitHub Codespaces**.

## **Step 1: Create Your Repository**
You need your own copy of the code on GitHub first.

1. **Go to GitHub**: Log in to your account.
2. **Create New Repository**:
   - Click the **+** icon in the top right -> **New repository**.
   - Name it: `minecraft-server-manager`.
   - Choose: **Public** or **Private**.
   - Click **Create repository**.

## **Step 2: Launch a Codespace**
Now let's start a virtual computer (Codespace) for this repo.

1. inside your new repository, click the green **Code** button.
2. Go to the **Codespaces** tab.
3. Click **Create codespace on main**.
   *(It will take 1-2 minutes to build the container).*

## **Step 3: Setup the Server Manager**
Once the VS Code editor loads in your browser, look for the **Terminal** at the bottom.

If you don't see a terminal, press `Ctrl + ~` (tilde) to open it.

**Run these commands ONE BY ONE:**

### 1. 📥 Clone the Code
*(If your repo is empty, you need to pull the code. If you already see the files on the left, skip this step!)*

```bash
git clone https://github.com/nitinbharwad84-ops/minecraft-server-manager.git .
```
*(Note the dot `.` at the end - this clones into the current folder!)*

### 2. 📦 Install Requirements
Install Python dependencies.

```bash
pip install -r requirements.txt
```

### 3. ✅ Verify Installation (Optional)
Check if everything is ready.

```bash
python main.py --headless
```
*(If you see a server status table, you are good to go!)*

---

## **Step 4: Run the Web UI**
Now start the web dashboard.

1. **Run the command:**
   ```bash
   python web_ui.py
   ```

2. **Wait for the Link:**
   The terminal will show something like this:
   ```
   🚀 Initializing Server Manager...
      -> Starting Web Server on port 5000
      -> Setting up Cloudflare Tunnel...
      -> Connecting to Cloudflare network...
   
   ============================================================
   ✅ SERVER MANAGER IS ONLINE!
   ============================================================
   
   🌐 DASHBOARD URL:  https://your-random-name.trycloudflare.com
   ```

3. **Click the URL**:
   - Hold **Ctrl** (or Cmd on Mac) and click the `https://...` link.
   - Or copy-paste it into a new tab.

---

## **Step 5: Start the Minecraft Server**
You are now in the Dashboard!

1. Go to the **Connect** tab.
2. Click **🚀 Start Playit.gg Tunnel**.
3. Wait for the **Public Server Address** (e.g., `magma-cube.gl.joinmc.link`).
4. **Copy this address** and use it in your Minecraft client (Multiplayer > Direct Connect).

---

## **Need to Stop?**
- To stop the Web UI: Go to the terminal and press `Ctrl + C`.
- To restart: Just run `python web_ui.py` again.

**Enjoy your free 24/7 server on GitHub Codespaces!** 🎮
