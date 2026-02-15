# 🎯 COLAB USAGE GUIDE - Interactive CLI

## ✅ **SOLUTION: Use Interactive Menu**

Since the TUI doesn't work in Colab, use the **interactive CLI menu** instead!

---

## 🚀 **Run the Interactive CLI**

```bash
python cli_menu.py
```

This gives you a **numbered menu** where you can:
- ✅ Start/stop the server
- ✅ Install Java
- ✅ Accept EULA
- ✅ Change settings
- ✅ Manage plugins
- ✅ View logs

**Everything the TUI can do, but works in Colab!** 🎉

---

## 📋 **Quick Start Steps**

### Step 1: Accept EULA
```bash
python cli_menu.py
# Choose: 3 (EULA Management)
# Choose: 2 (Accept EULA)
# Type: yes
```

### Step 2: Install Java (if needed)
```bash
# In menu:
# Choose: 2 (Java Management)
# Choose: 3 (Install Java 17)
```

### Step 3: Start Server
```bash
# In menu:
# Choose: 4 (Server Control)
# Choose: 1 (Start server)
```

---

## 🐍 **Alternative: Direct Python Commands**

If you prefer Python code in Colab cells:

### Check Status
```python
from server_manager import ServerManager
sm = ServerManager('config.json')
print(sm.get_server_status())
```

### Accept EULA
```python
from server_manager import ServerManager
sm = ServerManager('config.json')
result = sm.eula_manager.accept_eula()
print(result.message)
```

### Install Java 17
```python
import asyncio
import aiohttp
from server_manager import ServerManager

async def install_java():
    sm = ServerManager('config.json')
    async with aiohttp.ClientSession() as session:
        result = await sm.java_manager.download_java(17, session)
        if result:
            sm.java_manager.set_active(17)
            print("✅ Java 17 installed!")
        else:
            print("❌ Installation failed")

asyncio.run(install_java())
```

### Start Server
```python
from server_manager import ServerManager
sm = ServerManager('config.json')
result = sm.start_server()
print(result)
```

### View Logs
```python
from server_manager import ServerManager
sm = ServerManager('config.json')
logs = sm.get_log_tail(20)
for line in logs:
    print(line)
```

### Send Command (while running)
```python
from server_manager import ServerManager
sm = ServerManager('config.json')
sm.send_command("say Hello from Colab!")
```

---

## 🎯 **Recommended Workflow for Colab**

### Option 1: Interactive Menu (Easiest)
```bash
python cli_menu.py
```
Navigate with numbers, everything is menu-driven.

### Option 2: Python Cells (Most Flexible)
Create separate Colab cells for each action:

**Cell 1: Setup**
```python
from server_manager import ServerManager
sm = ServerManager('config.json')
sm.eula_manager.accept_eula()
```

**Cell 2: Start Server**
```python
sm.start_server()
```

**Cell 3: View Status**
```python
print(sm.get_server_status())
```

**Cell 4: View Logs**
```python
for log in sm.get_log_tail(20):
    print(log)
```

**Cell 5: Stop Server**
```python
sm.stop_server()
```

---

## 📊 **Feature Comparison**

| Feature | TUI | CLI Menu | Python Code |
|---------|-----|----------|-------------|
| **Works in Colab** | ❌ | ✅ | ✅ |
| **Mouse clicks** | ✅ | ❌ | N/A |
| **Easy navigation** | ✅ | ✅ | ❌ |
| **Scriptable** | ❌ | ❌ | ✅ |
| **Visual** | ✅ | ⚠️ | ❌ |

---

## 🐛 **Troubleshooting**

### "Module not found"
```bash
pip install aiohttp aiofiles rich paramiko psutil python-dotenv
```

### "EULA not accepted"
Run CLI menu → Option 3 → Option 2 → Type "yes"

### "Java not found"
Run CLI menu → Option 2 → Option 3 (Install Java 17)

### "Server won't start"
1. Check EULA is accepted (Menu → 3 → 1)
2. Check Java is installed (Menu → 2 → 1)
3. View logs (Menu → 4 → 4)

---

## ✨ **Summary**

**Problem**: TUI doesn't work in Colab (no mouse, limited keyboard)

**Solution**: Use **`cli_menu.py`** - same features, menu-driven!

```bash
python cli_menu.py
```

**Or use Python code directly in Colab cells for automation!**

---

**Ready to use!** Run `python cli_menu.py` now! 🚀
