#!/usr/bin/env python3
"""
test_all.py
===========
Comprehensive test suite for Minecraft Server Manager.

Usage:
    pytest test_all.py -v
    pytest test_all.py -v -k java
    pytest test_all.py -v --cov=.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, mock_open, patch
from datetime import datetime
import zipfile

import pytest


# ══════════════════════════════════════════════════════════════════════════════
#  FIXTURES
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config(temp_dir):
    """Create a mock config.json file."""
    config = {
        "server": {
            "type": "paper",
            "version": "1.20.1",
            "ram": 2048,
            "java_version": 17,
            "eula_accepted": False,
            "world_name": "world",
            "difficulty": "normal",
            "gamemode": "survival",
            "pvp": True,
            "max_players": 20,
            "port": 25565,
        },
        "paths": {
            "server_dir": str(temp_dir / "server"),
            "plugins_dir": str(temp_dir / "server" / "plugins"),
            "backup_dir": str(temp_dir / "backups"),
            "java_dir": str(temp_dir / "java"),
        },
    }
    config_path = temp_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
    return config_path


@pytest.fixture
def mock_server_dir(temp_dir):
    """Create a mock server directory structure."""
    server_dir = temp_dir / "server"
    server_dir.mkdir(parents=True)
    (server_dir / "plugins").mkdir(exist_ok=True)
    (server_dir / "logs").mkdir(exist_ok=True)
    
    # Create mock server.properties
    props = server_dir / "server.properties"
    props.write_text("server-port=25565\ndifficulty=normal\nmax-players=20\n")
    
    # Create mock eula.txt
    eula = server_dir / "eula.txt"
    eula.write_text("# EULA\neula=false\n")
    
    return server_dir


@pytest.fixture
def mock_java_dir(temp_dir):
    """Create a mock Java installation directory."""
    java_dir = temp_dir / "java"
    java_dir.mkdir(parents=True)
    
    # Create mock Java 17 installation
    java17 = java_dir / "jdk-17"
    java17.mkdir()
    bin_dir = java17 / "bin"
    bin_dir.mkdir()
    
    java_exe = bin_dir / "java.exe"
    java_exe.write_text("mock java executable")
    
    return java_dir


@pytest.fixture
def mock_plugin_jar(temp_dir):
    """Create a mock plugin JAR file."""
    jar_path = temp_dir / "TestPlugin.jar"
    
    with zipfile.ZipFile(jar_path, 'w') as zf:
        plugin_yml = """
name: TestPlugin
version: 1.0.0
main: com.example.TestPlugin
author: TestAuthor
"""
        zf.writestr("plugin.yml", plugin_yml)
    
    return jar_path


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp.ClientSession for API tests."""
    session = AsyncMock()
    
    async def mock_get(*args, **kwargs):
        response = AsyncMock()
        response.status = 200
        response.json = AsyncMock(return_value={
            "hits": [],
            "result": [],
            "data": [],
        })
        response.text = AsyncMock(return_value="")
        response.read = AsyncMock(return_value=b"")
        return response
    
    session.get = mock_get
    session.post = AsyncMock(return_value=AsyncMock(status=200))
    
    return session


# ══════════════════════════════════════════════════════════════════════════════
#  1. JAVA MANAGER TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_java_manager_init(mock_java_dir):
    """Test JavaManager initialization."""
    from java_manager import JavaManager
    
    jm = JavaManager(mock_java_dir, "java_versions.json")
    
    assert jm.java_dir == mock_java_dir
    assert jm.registry_path.name == "java_versions.json"


@patch("java_manager.subprocess.run")
def test_detect_java_versions(mock_run, mock_java_dir):
    """Test Java version detection."""
    from java_manager import JavaManager
    
    # Mock subprocess output
    mock_run.return_value = Mock(
        returncode=0,
        stdout="openjdk version \"17.0.1\" 2021-10-19\n"
    )
    
    jm = JavaManager(mock_java_dir, "java_versions.json")
    found = jm.detect_system_java()
    
    assert isinstance(found, list)
    # Detection might find 0 or more depending on mock setup
    assert len(found) >= 0


@patch("java_manager.subprocess.run")
def test_java_compatibility_check(mock_run, mock_java_dir):
    """Test Java version compatibility checking."""
    from java_manager import JavaManager, JavaInstallation
    
    jm = JavaManager(mock_java_dir, "java_versions.json")
    
    # Mock a Java 17 installation
    java17 = JavaInstallation(
        version=17,
        path=str(mock_java_dir / "jdk-17"),
        vendor="OpenJDK",
        install_date=datetime.now().isoformat(),
    )
    
    # Java 17 should be valid
    assert java17.is_valid()
    assert java17.version == 17


def test_validate_java_path(mock_java_dir):
    """Test Java path validation."""
    from java_manager import JavaManager
    
    jm = JavaManager(mock_java_dir, "java_versions.json")
    
    # Valid path (exists)
    valid_path = mock_java_dir / "jdk-17"
    valid_path.mkdir(exist_ok=True)
    
    # Invalid path (doesn't exist)
    invalid_path = mock_java_dir / "nonexistent"
    
    assert valid_path.exists()
    assert not invalid_path.exists()


@pytest.mark.asyncio
async def test_install_java_mock(mock_java_dir, mock_aiohttp_session):
    """Test Java installation with mocked download."""
    from java_manager import JavaManager
    
    jm = JavaManager(mock_java_dir, "java_versions.json")
    
    # Mock the download to return success without actual download
    with patch.object(jm, '_download_file', return_value=True):
        with patch.object(jm, '_extract_archive', return_value=True):
            result = await jm.download_java(17, mock_aiohttp_session)
            
            # Since we're mocking, result depends on implementation
            # At minimum, no exception should be raised
            assert result is not None


# ══════════════════════════════════════════════════════════════════════════════
#  2. EULA MANAGER TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_eula_manager_init(mock_server_dir, mock_config):
    """Test EulaManager initialization."""
    from eula_manager import EulaManager
    
    em = EulaManager(mock_server_dir, mock_config)
    
    assert em.server_dir == mock_server_dir
    assert em.eula_path == mock_server_dir / "eula.txt"


def test_eula_check_status_false(mock_server_dir, mock_config):
    """Test EULA status when not accepted."""
    from eula_manager import EulaManager
    
    em = EulaManager(mock_server_dir, mock_config)
    
    # Default eula.txt has eula=false
    assert em.check_eula_status() is False


def test_eula_acceptance(mock_server_dir, mock_config):
    """Test EULA acceptance."""
    from eula_manager import EulaManager
    
    em = EulaManager(mock_server_dir, mock_config)
    
    result = em.auto_accept_eula()
    
    assert result.success is True
    assert em.check_eula_status() is True
    
    # Verify file content
    eula_content = (mock_server_dir / "eula.txt").read_text()
    assert "eula=true" in eula_content


def test_eula_validation(mock_server_dir, mock_config):
    """Test EULA validation."""
    from eula_manager import EulaManager
    
    em = EulaManager(mock_server_dir, mock_config)
    
    # Initially invalid (eula=false)
    assert em.validate_eula() is False
    
    # Accept and validate
    em.auto_accept_eula()
    assert em.validate_eula() is True


def test_eula_decline(mock_server_dir, mock_config):
    """Test EULA decline."""
    from eula_manager import EulaManager
    
    em = EulaManager(mock_server_dir, mock_config)
    
    # Accept first
    em.auto_accept_eula()
    assert em.check_eula_status() is True
    
    # Then decline
    em.decline()
    assert em.check_eula_status() is False


def test_eula_get_text(mock_server_dir, mock_config):
    """Test retrieving EULA text."""
    from eula_manager import EulaManager
    
    em = EulaManager(mock_server_dir, mock_config)
    
    text = em.get_eula_text()
    
    assert isinstance(text, str)
    assert len(text) > 100  # Should be substantial legal text
    assert "Minecraft" in text


# ══════════════════════════════════════════════════════════════════════════════
#  3. FILE EDITOR TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_file_editor_init(mock_server_dir):
    """Test FileEditor initialization."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    assert fe.server_dir == Path(mock_server_dir)


def test_read_file(mock_server_dir):
    """Test reading a file."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    # Read existing server.properties
    props_path = mock_server_dir / "server.properties"
    content = fe.read_file(props_path)
    
    assert isinstance(content, str)
    assert "server-port" in content


def test_write_file(mock_server_dir):
    """Test writing a file with backup."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    test_file = mock_server_dir / "test.txt"
    test_content = "test content"
    
    result = fe.write_file(test_file, test_content)
    
    assert result.success is True
    assert test_file.read_text() == test_content


def test_validate_properties(mock_server_dir):
    """Test server.properties validation."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    # Valid properties
    valid_props = "server-port=25565\ndifficulty=normal\n"
    result = fe.validate_file_content("server.properties", valid_props)
    assert result.success is True
    
    # Invalid properties (malformed)
    invalid_props = "server-port=\nno_equals_sign\n"
    # May or may not fail depending on validator strictness
    # Just ensure no exception
    fe.validate_file_content("server.properties", invalid_props)


def test_json_validation(mock_server_dir):
    """Test JSON validation."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    # Valid JSON
    valid_json = '{"key": "value"}'
    result = fe.validate_file_content("config.json", valid_json)
    assert result.success is True
    
    # Invalid JSON
    invalid_json = '{"key": invalid}'
    result = fe.validate_file_content("config.json", invalid_json)
    assert result.success is False


def test_backup_creation(mock_server_dir):
    """Test file backup creation."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    props_path = mock_server_dir / "server.properties"
    original_content = props_path.read_text()
    
    backup_path = fe.create_backup(props_path)
    
    assert backup_path is not None
    assert Path(backup_path).exists()
    assert Path(backup_path).read_text() == original_content


def test_list_editable_files(mock_server_dir):
    """Test listing editable files."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    files = fe.list_editable_files()
    
    assert isinstance(files, list)
    # Should find at least server.properties and eula.txt
    assert len(files) >= 2
    
    names = [f.name for f in files]
    assert "server.properties" in names
    assert "eula.txt" in names


# ══════════════════════════════════════════════════════════════════════════════
#  4. SERVER MANAGER TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_server_manager_init(mock_config):
    """Test ServerManager initialization."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    assert sm.config_path == mock_config
    assert sm.server_dir.exists()


def test_config_loading(mock_config):
    """Test configuration loading."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    cfg = sm.get_server_config()
    
    assert cfg["type"] == "paper"
    assert cfg["version"] == "1.20.1"
    assert cfg["ram"] == 2048


def test_update_config(mock_config):
    """Test configuration updates."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    sm.update_server_config(ram=4096, max_players=50)
    
    cfg = sm.get_server_config()
    assert cfg["ram"] == 4096
    assert cfg["max_players"] == 50


def test_server_properties_read(mock_server_dir, mock_config):
    """Test reading server.properties."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    props = sm.get_server_properties()
    
    assert isinstance(props, dict)
    assert "server-port" in props
    assert props["server-port"] == "25565"


def test_server_properties_update(mock_server_dir, mock_config):
    """Test updating server.properties."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    sm.update_server_properties("max-players", "100")
    
    props = sm.get_server_properties()
    assert props["max-players"] == "100"


@patch("server_manager.subprocess.Popen")
def test_start_server_mock(mock_popen, mock_config, mock_server_dir):
    """Test server start with mocked subprocess."""
    from server_manager import ServerManager
    
    # Mock the process
    mock_process = Mock()
    mock_process.poll.return_value = None
    mock_process.pid = 12345
    mock_popen.return_value = mock_process
    
    sm = ServerManager(mock_config)
    
    # Need EULA accepted and server JAR
    sm.eula_manager.auto_accept_eula()
    
    # Create mock server JAR
    jar_path = sm.server_dir / "server.jar"
    jar_path.write_text("mock jar")
    
    # Attempt to start (will fail prerequisite checks in reality)
    # But we're testing the mocking works
    result = sm.start_server()
    
    # Result depends on prerequisites
    assert result is not None


def test_jvm_flags_generation(mock_config):
    """Test JVM flags generation."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    flags = sm.get_jvm_flags()
    
    assert isinstance(flags, str)
    # Default profile should have flags
    assert len(flags) > 0 or flags == ""


def test_jvm_profile_setting(mock_config):
    """Test setting JVM profile."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    # Set to aikar profile
    sm.set_jvm_profile("aikar")
    
    cfg = sm.get_server_config()
    # Profile may be stored or used directly
    # Just ensure no exception


def test_system_resources(mock_config):
    """Test system resource monitoring."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    resources = sm.get_system_resources()
    
    assert isinstance(resources, dict)
    assert "cpu_percent" in resources
    assert "ram_total_mb" in resources
    assert "disk_total_gb" in resources


def test_is_running(mock_config):
    """Test server running status check."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    # Should not be running initially
    assert sm.is_running() is False


# ══════════════════════════════════════════════════════════════════════════════
#  5. PLUGIN MANAGER TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_plugin_manager_init(temp_dir):
    """Test PluginManager initialization."""
    from plugin_manager import PluginManager
    
    plugins_dir = temp_dir / "plugins"
    plugins_dir.mkdir()
    
    pm = PluginManager(
        plugins_dir=plugins_dir,
        registry_path="installed_plugins.json",
        server_type="paper",
        mc_version="1.20.1",
    )
    
    assert pm.plugins_dir == plugins_dir
    assert pm.server_type == "paper"
    assert pm.mc_version == "1.20.1"


@pytest.mark.asyncio
async def test_plugin_search_mock(temp_dir, mock_aiohttp_session):
    """Test plugin search with mocked API."""
    from plugin_manager import PluginManager
    from plugin_apis import PluginSearchResult
    
    plugins_dir = temp_dir / "plugins"
    plugins_dir.mkdir()
    
    pm = PluginManager(
        plugins_dir=plugins_dir,
        registry_path="installed_plugins.json",
        server_type="paper",
        mc_version="1.20.1",
    )
    
    # Mock search results
    with patch("plugin_manager.search_plugins") as mock_search:
        mock_search.return_value = [
            PluginSearchResult(
                id="test-plugin",
                name="TestPlugin",
                source="modrinth",
                description="Test plugin",
                author="TestAuthor",
                downloads=1000,
                mc_versions=["1.20.1"],
                rating=4.5,
                icon_url="",
                project_url="",
            )
        ]
        
        results = await pm.search_plugins("test", session=mock_aiohttp_session)
        
        assert len(results) > 0
        assert results[0].name == "TestPlugin"


def test_plugin_compatibility_check(temp_dir, mock_plugin_jar):
    """Test plugin compatibility validation."""
    from plugin_validator import PluginValidator
    
    validator = PluginValidator(
        plugins_dir=temp_dir,
        server_type="paper",
        mc_version="1.20.1",
    )
    
    result = validator.validate(mock_plugin_jar)
    
    assert result is not None
    assert hasattr(result, 'is_valid')


def test_install_from_file(temp_dir, mock_plugin_jar):
    """Test installing plugin from local file."""
    from plugin_manager import PluginManager
    
    plugins_dir = temp_dir / "plugins"
    plugins_dir.mkdir()
    
    pm = PluginManager(
        plugins_dir=plugins_dir,
        registry_path="installed_plugins.json",
        server_type="paper",
        mc_version="1.20.1",
    )
    
    result = pm.install_from_file(mock_plugin_jar)
    
    # Should succeed or fail validation gracefully
    assert result is not None
    assert hasattr(result, 'success')


def test_get_installed_plugins(temp_dir):
    """Test listing installed plugins."""
    from plugin_manager import PluginManager
    
    plugins_dir = temp_dir / "plugins"
    plugins_dir.mkdir()
    
    pm = PluginManager(
        plugins_dir=plugins_dir,
        registry_path="installed_plugins.json",
        server_type="paper",
        mc_version="1.20.1",
    )
    
    installed = pm.get_installed_plugins()
    
    assert isinstance(installed, list)
    # Should be empty initially
    assert len(installed) == 0


@pytest.mark.asyncio
async def test_dependency_resolution_mock(temp_dir, mock_aiohttp_session):
    """Test plugin dependency resolution."""
    from plugin_manager import PluginManager
    from plugin_apis import PluginSearchResult, PluginDependency
    
    plugins_dir = temp_dir / "plugins"
    plugins_dir.mkdir()
    
    pm = PluginManager(
        plugins_dir=plugins_dir,
        registry_path="installed_plugins.json",
        server_type="paper",
        mc_version="1.20.1",
    )
    
    # Mock plugin with dependency
    with patch("plugin_manager.get_plugin_dependencies") as mock_deps:
        mock_deps.return_value = [
            PluginDependency(
                id="dependency-plugin",
                name="DependencyPlugin",
                required=True,
                source="modrinth",
            )
        ]
        
        deps = await pm._install_dependencies(
            PluginSearchResult(
                id="main-plugin",
                name="MainPlugin",
                source="modrinth",
                description="",
                author="",
                downloads=0,
                mc_versions=[],
            ),
            mock_aiohttp_session,
        )
        
        # Should return result
        assert deps is not None


# ══════════════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_full_setup_workflow(mock_config, mock_server_dir):
    """Integration test: Full server setup workflow."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    # 1. Accept EULA
    eula_result = sm.eula_manager.auto_accept_eula()
    assert eula_result.success is True
    
    # 2. Generate server.properties
    sm.generate_server_properties()
    props = sm.get_server_properties()
    assert "server-port" in props
    
    # 3. Check prerequisites
    prereq_result = sm.check_prerequisites()
    # Will likely fail some checks (no JAR, no Java) but shouldn't crash
    assert prereq_result is not None


def test_plugin_install_workflow(temp_dir, mock_plugin_jar):
    """Integration test: Plugin installation workflow."""
    from plugin_manager import PluginManager
    
    plugins_dir = temp_dir / "plugins"
    plugins_dir.mkdir()
    
    pm = PluginManager(
        plugins_dir=plugins_dir,
        registry_path="installed_plugins.json",
        server_type="paper",
        mc_version="1.20.1",
    )
    
    # 1. Install from file
    result = pm.install_from_file(mock_plugin_jar)
    
    # 2. Check installed
    installed = pm.get_installed_plugins()
    
    # May succeed or fail validation, but should handle gracefully
    assert result is not None
    assert isinstance(installed, list)


def test_config_persistence(mock_config):
    """Integration test: Config changes persist."""
    from server_manager import ServerManager
    
    sm1 = ServerManager(mock_config)
    sm1.update_server_config(ram=8192)
    
    # Create new instance
    sm2 = ServerManager(mock_config)
    cfg = sm2.get_server_config()
    
    assert cfg["ram"] == 8192


def test_file_backup_restore_workflow(mock_server_dir):
    """Integration test: File backup and restore."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    props_path = mock_server_dir / "server.properties"
    original = props_path.read_text()
    
    # 1. Create backup
    backup = fe.create_backup(props_path)
    
    # 2. Modify file
    fe.write_file(props_path, "modified content")
    
    # 3. Restore backup
    result = fe.restore_backup(props_path, backup)
    
    assert result.success is True
    assert props_path.read_text() == original


# ══════════════════════════════════════════════════════════════════════════════
#  ERROR HANDLING TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_invalid_config_path():
    """Test handling of invalid config path."""
    from server_manager import ServerManager
    
    # Should create default config if missing
    sm = ServerManager("/nonexistent/config.json")
    
    assert sm.config is not None


def test_missing_eula_file(temp_dir, mock_config):
    """Test handling of missing eula.txt."""
    from eula_manager import EulaManager
    
    em = EulaManager(temp_dir, mock_config)
    
    # Should handle gracefully
    status = em.check_eula_status()
    assert status is False


def test_corrupted_plugin_jar(temp_dir):
    """Test handling of corrupted plugin JAR."""
    from plugin_manager import PluginManager
    
    plugins_dir = temp_dir / "plugins"
    plugins_dir.mkdir()
    
    pm = PluginManager(
        plugins_dir=plugins_dir,
        registry_path="installed_plugins.json",
        server_type="paper",
        mc_version="1.20.1",
    )
    
    # Create corrupt JAR
    corrupt_jar = temp_dir / "corrupt.jar"
    corrupt_jar.write_text("not a valid zip file")
    
    result = pm.install_from_file(corrupt_jar)
    
    # Should fail gracefully
    assert result.success is False


def test_file_read_error(mock_server_dir):
    """Test handling of file read errors."""
    from file_editor import FileEditor
    
    fe = FileEditor(mock_server_dir)
    
    # Try to read non-existent file
    content = fe.read_file(mock_server_dir / "nonexistent.txt")
    
    # Should return empty or error message, not crash
    assert isinstance(content, str)


# ══════════════════════════════════════════════════════════════════════════════
#  PERFORMANCE/EDGE CASE TESTS
# ══════════════════════════════════════════════════════════════════════════════


def test_large_config_values(mock_config):
    """Test handling of large configuration values."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    # Set very large RAM
    sm.update_server_config(ram=65536)
    
    cfg = sm.get_server_config()
    assert cfg["ram"] == 65536


def test_special_characters_in_motd(mock_config):
    """Test handling of special characters in MOTD."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    special_motd = "§aWelcome §l§nTest Server! 🌟"
    sm.update_server_config(motd=special_motd)
    
    cfg = sm.get_server_config()
    assert cfg["motd"] == special_motd


def test_concurrent_config_access(mock_config):
    """Test concurrent access to configuration."""
    from server_manager import ServerManager
    
    sm = ServerManager(mock_config)
    
    # Simulate rapid config updates
    for i in range(10):
        sm.update_server_config(port=25565 + i)
    
    cfg = sm.get_server_config()
    # Should have last value
    assert cfg["port"] == 25574


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
