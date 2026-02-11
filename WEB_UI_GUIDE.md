# 🌐 WEB UI USAGE GUIDE

## ✅ **BEST SOLUTION FOR COLAB!**

The web UI is the **perfect solution** for Colab, Codespaces, and remote servers. It provides a beautiful, modern dashboard that works in any browser!

---

## 🚀 **Quick Start**

### Step 1: Install Dependencies
```bash
pip install flask pyngrok
```

### Step 2: Run the Web UI

**For Colab (Public URL):**
```bash
python web_ui.py --public
```

**For Local/Codespaces (Localhost only):**
```bash
python web_ui.py
```

---

## 🌐 **Accessing the Dashboard**

### On Colab:
When you run with `--public`, you'll see:
```
🌐 Public URL: https://abc123.ngrok-free.app
   Share this URL to access from anywhere!

🚀 Starting web server on http://localhost:5000
```

Click the ngrok URL to open the dashboard! ✨

### On Local Machine:
Open your browser to:
```
http://localhost:5000
```

### On Codespaces:
GitHub Codespaces will automatically detect port 5000 and show a notification:
- Click "Open in Browser"
- Or use the Ports panel to see the forwarded URL

---

## 🎨 **Features**

### 📊 Dashboard Tab
- **Real-time stats**: TPS, Players, CPU, RAM
- **Server control**: Start, Stop, Restart buttons
- **Send commands**: Execute server commands
- **System resources**: Visual progress bars
- **Auto-backup**: One-click world backup

### ☕ Java Tab
- **View installed versions**: See all Java installations
- **Detect system Java**: Auto-find Java on system
- **Install Java**: Download Java 17 or 21 with one click
- **Set active version**: Change which Java to use

### 📜 EULA Tab
- **Check status**: See if EULA is accepted
- **Accept/Decline**: One-click EULA management
- **Direct link**: Read full EULA on Mojang's site

### ⚙️ Settings Tab
- **Server type**: Change between Vanilla, Paper, Spigot, etc.
- **MC version**: Update Minecraft version
- **RAM allocation**: Adjust memory
- **Max players**: Set player limit
- **Difficulty & gamemode**: Configure gameplay

### 📋 Logs Tab
- **Real-time logs**: View last 50 log lines
- **Auto-refresh**: Updates every 5 seconds
- **Manual refresh**: Update on demand

---

## 🔧 **How It Works**

The web UI consists of:
1. **Flask backend** (`web_ui.py`) - REST API for all operations
2. **HTML dashboard** (`templates/index.html`) - Beautiful modern UI
3. **Auto-refresh** - Updates every 3 seconds
4. **AJAX calls** - Smooth, no-reload interactions

---

## 📱 **Mobile Friendly**

The UI is **responsive** and works on:
- ✅ Desktop browsers (Chrome, Firefox, Safari, Edge)
- ✅ Mobile phones (iOS, Android)
- ✅ Tablets (iPad, etc.)

---

## 🎯 **Usage Examples**

### Example 1: First Time Setup
1. Open web UI
2. Go to **EULA** tab → Click "Accept EULA"
3. Go to **Java** tab → Click "Install Java 17"
4. Go to **Dashboard** tab → Click "Start Server"
5. Done! ✅

### Example 2: Change Server Settings
1. Go to **Settings** tab
2. Change "Server Type" to "Paper"
3. Change "RAM" to "4096"
4. Click "Save Settings"
5. Restart server from **Dashboard**

### Example 3: Send Commands
1. Go to **Dashboard** tab
2. Type in Command box: `say Hello World!`
3. Click "Send" or press Enter
4. Go to **Logs** tab to see output

---

## 🐛 **Troubleshooting**

### Port 5000 already in use
```bash
# Change to different port
python web_ui.py --port 8080
```

Then open `http://localhost:8080`

### pyngrok not working in Colab
```bash
# Install pyngrok
pip install pyngrok

# You may need to sign up for free ngrok account
# Visit: https://ngrok.com/
```

### Can't access from browser
Check that:
1. Server is running (look for "Starting web server...")
2. URL is correct (localhost:5000 or ngrok URL)
3. Firewall isn't blocking the port

### UI not updating
- Press Ctrl+F5 to hard refresh
- Check browser console for errors (F12)
- Make sure JavaScript is enabled

---

## 🔐 **Security Notes**

### For Public Access (Colab with --public):
⚠️ **WARNING**: The `--public` flag makes your server accessible to ANYONE with the URL!

**Recommendations**:
1. Only use `--public` when needed
2. Don't share the ngrok URL publicly
3. Stop the server when done
4. For production, add authentication (not included)

### For Local Use:
✅ Safe - only accessible from your machine

---

## 🎨 **Customize the UI**

The UI is in `templates/index.html`. You can:
- Change colors (search for `#667eea` and `#764ba2`)
- Add more features
- Customize layout
- Add charts/graphs

---

## 📊 **Comparison: Web UI vs TUI vs CLI**

| Feature | Web UI | TUI | CLI Menu |
|---------|--------|-----|----------|
| **Works in Colab** | ✅ Perfect | ❌ No mouse | ✅ Basic |
| **Visual appeal** | ✅ Beautiful | ✅ Good | ❌ Plain |
| **Real-time updates** | ✅ Auto | ✅ Auto | ❌ Manual |
| **Mouse clicks** | ✅ Yes | ❌ Keyboard only | ❌ Keyboard only |
| **Mobile friendly** | ✅ Yes | ❌ No | ❌ No |
| **Shareable** | ✅ Yes (ngrok) | ❌ No | ❌ No |
| **Multiple users** | ✅ Yes | ❌ No | ❌ No |

**Winner for Colab: Web UI! 🏆**

---

## 🚀 **Advanced Usage**

### Custom Port
```bash
python web_ui.py --port 8080
```

### Run in Background
```bash
# Linux/Mac/Colab
nohup python web_ui.py --public > webui.log 2>&1 &

# Windows
start /B python web_ui.py
```

### Access from Other Devices
If running on your local network:
```bash
python web_ui.py
# Then access from other devices:
# http://YOUR_IP_ADDRESS:5000
```

---

## 💡 **Pro Tips**

1. **Keep the tab open** - Real-time updates only work when browser tab is open
2. **Use Chrome/Firefox** - Best compatibility
3. **Check logs regularly** - Go to Logs tab to troubleshoot
4. **Backup before updates** - Use the Backup button before changing settings
5. **Multiple tabs work** - Open dashboard in multiple browser tabs (all update independently)

---

## 📚 **API Endpoints**

The web UI exposes REST API at:
- `GET /api/status` - Server status
- `POST /api/server/start` - Start server
- `POST /api/server/stop` - Stop server
- `GET /api/java/list` - List Java versions
- `POST /api/eula/accept` - Accept EULA
- And more...

You can use these programmatically with curl/Python!

---

## ✨ **Summary**

**Problem**: TUI doesn't work in Colab  
**Solution**: Beautiful web UI with ngrok public URL!

**Run it now:**
```bash
python web_ui.py --public
```

**Then open the ngrok URL in your browser! 🎉**

---

**Enjoy your beautiful Minecraft Server Manager dashboard!** 🌐⛏️
