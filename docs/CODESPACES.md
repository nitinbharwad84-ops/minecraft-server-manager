# GitHub Codespaces Setup Guide

## 🚀 Quick Start (1 Command!)

Open this repo in GitHub Codespaces, and everything will be auto-configured:

1. Click **Code** → **Codespaces** → **Create codespace on main**
2. Wait ~2 minutes for auto-setup
3. Run: `python main.py`

That's it! ✅

---

## 🎯 What Auto-Installs

The `.devcontainer/devcontainer.json` automatically sets up:

✅ **Python 3.11** with pip  
✅ **Java 17** (for Minecraft server)  
✅ **All dependencies** from `requirements.txt`  
✅ **VS Code extensions** (Python, Pylance, Black formatter)  
✅ **Port forwarding** for Minecraft server (25565)

---

## 🧪 Running Tests on Codespaces

```bash
# Run all tests
python -m pytest test_all.py -v

# Run with coverage
python -m pytest test_all.py --cov=. --cov-report=html

# Open coverage report
python -m http.server 8000 -d htmlcov
```

**Expected result**: ~45/46 tests passing (vs 32/46 on Windows)

---

## 🖥️ Running the TUI

```bash
# Start the Textual UI
python main.py

# Or headless mode
python main.py --headless
```

The Textual interface will look **much better** on Codespaces due to proper terminal support!

---

## 🔧 Why Codespaces > Windows

| Feature | Windows | Codespaces (Linux) |
|---------|---------|-------------------|
| **Test Pass Rate** | 70% (32/46) | ~98% (45/46) |
| **Temp Files** | ❌ Permission errors | ✅ Works perfectly |
| **Terminal UI** | ⚠️ Limited colors | ✅ Full 24-bit color |
| **File Locking** | ❌ WinError 32 | ✅ No issues |
| **Setup Time** | ~10 minutes | ~2 minutes (auto) |

---

## 🌐 Port Forwarding

The Minecraft server port (25565) is automatically forwarded. When you start a server:

1. Codespaces will show a notification: "Your application running on port 25565 is available"
2. Click **Open in Browser** or **Make Public**
3. Get a public URL like: `https://<random>-25565.app.github.dev`

Players can connect using this URL!

---

## 📊 CI/CD with GitHub Actions

Every push/PR automatically:

1. ✅ Runs all 46 tests on Python 3.10, 3.11, 3.12
2. 📈 Generates coverage reports
3. 🚀 Uploads to Codecov (if configured)

See: `.github/workflows/tests.yml`

---

## 🐛 Debugging

```bash
# Check Python version
python --version

# Check Java version
java -version

# List installed packages
pip list

# Run single test
python -m pytest test_all.py::test_eula_acceptance -v

# Debug mode
python -m pytest test_all.py -vv --tb=long
```

---

## 💡 Pro Tips

### 1. **Use Split Terminal**
- Terminal 1: `python main.py` (TUI)
- Terminal 2: File editing
- Terminal 3: Testing

### 2. **Environment Variables**
Create `.env` file:
```bash
# .env
CURSEFORGE_API_KEY=your_key_here
```

Auto-loaded by `python-dotenv` ✅

### 3. **Quick Restart**
```bash
# Stop server: Ctrl+C
# Restart: ↑ (up arrow) + Enter
```

### 4. **File Watching**
```bash
# Auto-run tests on file change
pip install pytest-watch
ptw test_all.py -- -v
```

---

## 📦 Customizing Your Codespace

Edit `.devcontainer/devcontainer.json`:

```json
{
  "features": {
    "ghcr.io/devcontainers/features/java:1": {
      "version": "21"  // Use Java 21 instead
    },
    "ghcr.io/devcontainers/features/docker-in-docker:2": {}  // Add Docker
  }
}
```

---

## 🚨 Troubleshooting

### Tests Failing?
```bash
# Check if dependencies installed
pip install -r requirements.txt

# Re-run post-create command
pip install --upgrade pip && pip install -r requirements.txt
```

### Java Not Found?
```bash
# Check Java
which java
java -version

# Install manually if needed
sudo apt-get update && sudo apt-get install -y openjdk-17-jdk
```

### Port 25565 Already in Use?
```bash
# Kill existing process
sudo lsof -ti:25565 | xargs kill -9
```

---

## 📚 Additional Resources

- **Codespaces Docs**: https://docs.github.com/en/codespaces
- **Textual Docs**: https://textual.textualize.io/
- **pytest Docs**: https://docs.pytest.org/

---

## ✨ Benefits Summary

| What | Impact |
|------|--------|
| **No local setup** | Start coding in 2 minutes |
| **Consistent environment** | Everyone uses same Linux setup |
| **Better test coverage** | 98% vs 70% on Windows |
| **Perfect terminal** | Full Textual UI support |
| **Auto CI/CD** | Tests run on every commit |
| **Port forwarding** | Share server with friends instantly |

**Bottom line**: Codespaces is the **recommended** way to develop and run this project! 🎉
