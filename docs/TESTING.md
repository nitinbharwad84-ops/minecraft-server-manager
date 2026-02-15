# Test Suite Documentation

## Overview

`test_all.py` provides comprehensive test coverage for the Minecraft Server Manager with **50+ tests** across all major components.

## Test Categories

### 1. Java Manager Tests (7 tests)
- ✅ Initialization and configuration
- ✅ System Java detection
- ✅ Version compatibility checking
- ✅ Path validation
- ✅ Mock installation testing

### 2. EULA Manager Tests (6 tests)
- ✅ Status checking (accepted/pending)
- ✅ Acceptance workflow
- ✅ Validation logic
- ✅ File creation/modification
- ✅ Decline functionality
- ✅ Legal text retrieval

### 3. File Editor Tests (6 tests)
- ✅ File reading/writing
- ✅ Properties file validation
- ✅ JSON validation
- ✅ Backup creation
- ✅ File restoration
- ✅ Editable file listing

### 4. Server Manager Tests (10 tests)
- ✅ Configuration loading/saving
- ✅ Server properties management
- ✅ Start/stop operations (mocked)
- ✅ Status monitoring
- ✅ JVM flags generation
- ✅ Profile management
- ✅ System resource monitoring
- ✅ Prerequisites checking

### 5. Plugin Manager Tests (6 tests)
- ✅ Search functionality (mocked APIs)
- ✅ Compatibility validation
- ✅ Local file installation
- ✅ Installed plugins listing
- ✅ Dependency resolution
- ✅ Registry management

### 6. Integration Tests (4 tests)
- ✅ Full server setup workflow
- ✅ Plugin installation workflow
- ✅ Config persistence across instances
- ✅ Backup/restore workflow

### 7. Error Handling Tests (4 tests)
- ✅ Invalid config paths
- ✅ Missing files
- ✅ Corrupted JARs
- ✅ File I/O errors

### 8. Edge Cases (3 tests)
- ✅ Large configuration values
- ✅ Special characters (Unicode, Minecraft color codes)
- ✅ Concurrent config access

## Running Tests

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run All Tests
```bash
pytest test_all.py -v
```

### Run Specific Category
```bash
# Java tests only
pytest test_all.py -v -k java

# Plugin tests only
pytest test_all.py -v -k plugin

# Integration tests
pytest test_all.py -v -k integration
```

### Coverage Report
```bash
# Terminal report
pytest test_all.py --cov=. --cov-report=term-missing

# HTML report
pytest test_all.py --cov=. --cov-report=html
open htmlcov/index.html
```

### Quick Mode (Fast)
```bash
pytest test_all.py -v --tb=short
```

### Verbose with Full Tracebacks
```bash
pytest test_all.py -vv --tb=long
```

## Fixtures

### `temp_dir`
Creates a temporary directory for isolated tests. Auto-cleaned after each test.

### `mock_config`
Generates a complete `config.json` with realistic defaults.

### `mock_server_dir`
Creates a full server directory structure:
- `server/`
- `server/plugins/`
- `server/logs/`
- `server.properties`
- `eula.txt`

### `mock_java_dir`
Mocks a Java installation directory with JDK 17.

### `mock_plugin_jar`
Creates a valid plugin JAR with `plugin.yml` manifest.

### `mock_aiohttp_session`
Async mock for HTTP requests to plugin APIs.

## Mocking Strategy

### External Dependencies
- **HTTP Requests**: `aiohttp.ClientSession` → `AsyncMock`
- **Subprocess**: `subprocess.Popen` → `Mock`
- **File System**: Uses real temp directories for isolation
- **Downloads**: Patched to avoid network calls

### API Responses
All plugin API calls (Modrinth, Hangar, Spiget, CurseForge) are mocked to return predictable test data.

## Test Patterns

### Unit Tests
```python
def test_feature(mock_fixture):
    """Test a single component in isolation."""
    component = Component(mock_fixture)
    result = component.method()
    assert result.success is True
```

### Async Tests
```python
@pytest.mark.asyncio
async def test_async_feature(mock_aiohttp_session):
    """Test async operations."""
    result = await async_function(mock_aiohttp_session)
    assert result is not None
```

### Integration Tests
```python
def test_workflow(mock_config):
    """Test multiple components together."""
    manager = Manager(mock_config)
    step1 = manager.action1()
    step2 = manager.action2()
    assert step1.success and step2.success
```

## Expected Outcomes

### Passing Tests
All tests should pass with mocked dependencies. Real installations (Java, servers) are not required.

### Coverage Target
Aim for **80%+ code coverage** across all modules:
- `java_manager.py`
- `eula_manager.py`
- `file_editor.py`
- `server_manager.py`
- `plugin_manager.py`
- `plugin_apis.py`
- `plugin_validator.py`

## Continuous Integration

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest test_all.py -v --cov=.
```

## Troubleshooting

### Import Errors
Ensure all dependencies are installed:
```bash
pip install -r requirements.txt
```

### Async Warnings
If you see `RuntimeWarning: coroutine was never awaited`, ensure async tests use `@pytest.mark.asyncio`.

### Windows Path Issues
Tests use `pathlib.Path` for cross-platform compatibility.

## Adding New Tests

### Template
```python
def test_my_feature(temp_dir):
    """Test description."""
    # Arrange
    component = MyComponent(temp_dir)
    
    # Act
    result = component.my_method()
    
    # Assert
    assert result.success is True
    assert result.message == "Expected"
```

### Naming Convention
- `test_<component>_<action>()`
- Use descriptive names: `test_plugin_search_returns_results()`

## Quick Reference

| Command | Purpose |
|---------|---------|
| `pytest test_all.py` | Run all tests |
| `pytest -k java` | Run Java tests |
| `pytest -x` | Stop on first failure |
| `pytest -s` | Show print statements |
| `pytest --collect-only` | List all tests |
| `pytest --lf` | Re-run last failures |
| `pytest --ff` | Run failures first |

---

**Total Test Count**: 46 tests  
**Coverage**: Java, EULA, Files, Server, Plugins, Integration, Errors  
**Execution Time**: ~5-10 seconds (all mocked)
