from __future__ import annotations

import os
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from src.matcreator.ports import (
    PortsConfig,
    get_adk_port,
    get_frontend_port,
    get_local_adk_command,
    get_mcp_endpoint_url,
    get_server_proxy_port,
    get_web_port,
    get_worker_base_port,
    load_ports_config,
)

from conftest import ALL_PORT_ENV_VARS, clear_port_env_vars  # noqa: F401


def _write_config_yaml(config_dir: Path, ports: dict) -> Path:
    """Write a ``config.yaml`` file under *config_dir* and return its path."""
    config_path = config_dir / "config.yaml"
    config_path.write_text(
        yaml.dump({"ports": ports}, default_flow_style=False),
        encoding="utf-8",
    )
    return config_path


# ===================================================================
# Default values
# ===================================================================


def test_default_adk_port(monkeypatch, tmp_path: Path) -> None:
    """ADK default port is 8000."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_HOME", str(tmp_path))
    assert get_adk_port() == 8000


def test_default_web_port(monkeypatch) -> None:
    """Web default port is 8001."""
    clear_port_env_vars(monkeypatch)
    assert get_web_port() == 8001


def test_default_frontend_port(monkeypatch) -> None:
    """Frontend default port is 5173."""
    clear_port_env_vars(monkeypatch)
    assert get_frontend_port() == 5173


def test_default_server_proxy_port(monkeypatch) -> None:
    """Server proxy default port is 80."""
    clear_port_env_vars(monkeypatch)
    assert get_server_proxy_port() == 80


def test_default_worker_base_port(monkeypatch) -> None:
    """Worker base default port is 9001."""
    clear_port_env_vars(monkeypatch)
    assert get_worker_base_port() == 9001


def test_default_mcp_ports(monkeypatch) -> None:
    """MCP default ports: database=50001, dpa=50002, abacus=50003,
    structure=50004, vasp=50005, mattergen=50006."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("database") == "http://localhost:50001/sse"
    assert get_mcp_endpoint_url("dpa") == "http://localhost:50002/sse"
    assert get_mcp_endpoint_url("abacus") == "http://localhost:50003/sse"
    assert get_mcp_endpoint_url("structure") == "http://localhost:50004/sse"
    assert get_mcp_endpoint_url("vasp") == "http://localhost:50005/sse"
    assert get_mcp_endpoint_url("mattergen") == "http://localhost:50006/sse"


# ===================================================================
# Environment variable overrides
# ===================================================================


def test_env_override_adk_port(monkeypatch) -> None:
    """MATCREATOR_ADK_PORT env var overrides default."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "8100")
    assert get_adk_port() == 8100


def test_env_override_web_port(monkeypatch) -> None:
    """MATCREATOR_WEB_PORT env var overrides default."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_WEB_PORT", "8101")
    assert get_web_port() == 8101


def test_env_override_frontend_port(monkeypatch) -> None:
    """MATCREATOR_FRONTEND_PORT env var overrides default."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_FRONTEND_PORT", "5180")
    assert get_frontend_port() == 5180


def test_env_override_server_proxy_port(monkeypatch) -> None:
    """MATCREATOR_SERVER_PROXY_PORT env var overrides default."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_SERVER_PROXY_PORT", "8080")
    assert get_server_proxy_port() == 8080


def test_env_override_worker_base_port(monkeypatch) -> None:
    """MATCREATOR_WORKER_BASE_PORT env var overrides default."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_WORKER_BASE_PORT", "9100")
    assert get_worker_base_port() == 9100


def test_env_override_mcp_ports(monkeypatch) -> None:
    """MCP port env vars override defaults."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_MCP_DATABASE_PORT", "51001")
    monkeypatch.setenv("MATCREATOR_MCP_DPA_PORT", "51002")
    monkeypatch.setenv("MATCREATOR_MCP_ABACUS_PORT", "51003")
    monkeypatch.setenv("MATCREATOR_MCP_STRUCTURE_PORT", "51004")
    monkeypatch.setenv("MATCREATOR_MCP_VASP_PORT", "51005")
    monkeypatch.setenv("MATCREATOR_MCP_MATTERGEN_PORT", "51006")

    assert get_mcp_endpoint_url("database") == "http://localhost:51001/sse"
    assert get_mcp_endpoint_url("dpa") == "http://localhost:51002/sse"
    assert get_mcp_endpoint_url("abacus") == "http://localhost:51003/sse"
    assert get_mcp_endpoint_url("structure") == "http://localhost:51004/sse"
    assert get_mcp_endpoint_url("vasp") == "http://localhost:51005/sse"
    assert get_mcp_endpoint_url("mattergen") == "http://localhost:51006/sse"


# ===================================================================
# Config file fallback
# ===================================================================


def test_config_yaml_fallback(tmp_path: Path, monkeypatch) -> None:
    """Config file values used when env vars not set."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_HOME", str(tmp_path))

    _write_config_yaml(
        tmp_path,
        {
            "adk": 8100,
            "web": 8101,
            "frontend": 5180,
            "server_proxy": 8080,
            "worker_base": 9100,
            "mcp_host": "config.host",
            "mcp": {
                "database": 51001,
                "dpa": 51002,
            },
        },
    )

    config = load_ports_config()
    assert config.adk == 8100
    assert config.web == 8101
    assert config.frontend == 5180
    assert config.server_proxy == 8080
    assert config.worker_base == 9100
    assert config.mcp_host == "config.host"
    assert config.mcp_database == 51001
    assert config.mcp_dpa == 51002


# ===================================================================
# Precedence: env > config.yaml > defaults
# ===================================================================


def test_precedence_env_over_config(monkeypatch, tmp_path: Path) -> None:
    """Env vars override config.yaml values."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_HOME", str(tmp_path))

    _write_config_yaml(tmp_path, {"adk": 8100})
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "8200")

    assert get_adk_port() == 8200


def test_precedence_full_chain(monkeypatch, tmp_path: Path) -> None:
    """Full precedence: env > config.yaml > defaults."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_HOME", str(tmp_path))

    # Config file sets adk to 8100, but no env var for adk
    _write_config_yaml(tmp_path, {"adk": 8100})
    # Env var for web overrides config
    monkeypatch.setenv("MATCREATOR_WEB_PORT", "8201")
    # Neither env nor config for frontend -> defaults

    assert get_adk_port() == 8100  # from config
    assert get_web_port() == 8201  # from env (overrides config default)
    assert get_frontend_port() == 5173  # default


# ===================================================================
# Legacy alias
# ===================================================================


def test_legacy_adk_local_port(monkeypatch) -> None:
    """ADK_LOCAL_PORT works as legacy alias."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("ADK_LOCAL_PORT", "8200")
    assert get_adk_port() == 8200


def test_new_port_wins_over_legacy(monkeypatch) -> None:
    """MATCREATOR_ADK_PORT wins over ADK_LOCAL_PORT when both set."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "8100")
    monkeypatch.setenv("ADK_LOCAL_PORT", "8200")
    assert get_adk_port() == 8100


# ===================================================================
# Invalid port rejection
# ===================================================================


def test_invalid_port_non_integer(monkeypatch) -> None:
    """Non-integer port raises ValueError."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "abc")
    with pytest.raises(ValueError):
        get_adk_port()


def test_invalid_port_zero(monkeypatch) -> None:
    """Port 0 raises ValueError."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "0")
    with pytest.raises(ValueError, match="between 1 and 65535"):
        get_adk_port()


def test_invalid_port_negative(monkeypatch) -> None:
    """Negative port raises ValueError."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "-1")
    with pytest.raises(ValueError):
        get_adk_port()


def test_invalid_port_too_large(monkeypatch) -> None:
    """Port 65536 raises ValueError."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "65536")
    with pytest.raises(ValueError):
        get_adk_port()


# ===================================================================
# get_mcp_endpoint_url
# ===================================================================


def test_mcp_endpoint_url_defaults(monkeypatch) -> None:
    """Default MCP endpoint URLs."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("database") == "http://localhost:50001/sse"
    assert get_mcp_endpoint_url("dpa") == "http://localhost:50002/sse"
    assert get_mcp_endpoint_url("abacus") == "http://localhost:50003/sse"
    assert get_mcp_endpoint_url("structure") == "http://localhost:50004/sse"
    assert get_mcp_endpoint_url("vasp") == "http://localhost:50005/sse"
    assert get_mcp_endpoint_url("mattergen") == "http://localhost:50006/sse"


def test_mcp_endpoint_url_with_custom_host(monkeypatch) -> None:
    """MATCREATOR_MCP_HOST env var changes host in all URLs."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_MCP_HOST", "host.docker.internal")
    assert get_mcp_endpoint_url("vasp") == "http://host.docker.internal:50005/sse"


def test_mcp_endpoint_url_with_custom_port(monkeypatch) -> None:
    """Individual port env var overrides port in URL."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_MCP_VASP_PORT", "51005")
    assert get_mcp_endpoint_url("vasp") == "http://localhost:51005/sse"


def test_mcp_endpoint_url_full_override(monkeypatch) -> None:
    """Full URL env var overrides host+port construction."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_MCP_DATABASE_URL", "http://custom:9999/sse")
    assert get_mcp_endpoint_url("database") == "http://custom:9999/sse"


def test_mcp_endpoint_url_unknown_name(monkeypatch) -> None:
    """Unknown endpoint name raises ValueError."""
    clear_port_env_vars(monkeypatch)
    with pytest.raises(ValueError):
        get_mcp_endpoint_url("nonexistent")


# ===================================================================
# get_local_adk_command
# ===================================================================


def test_local_adk_command_default(monkeypatch, tmp_path: Path) -> None:
    """Default local ADK command."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_HOME", str(tmp_path))
    cmd = get_local_adk_command()
    assert cmd == ["matcreator", "api-server", "--host", "127.0.0.1", "--port", "8000"]


def test_local_adk_command_custom_port(monkeypatch) -> None:
    """Custom ADK port in command."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_ADK_PORT", "8100")
    cmd = get_local_adk_command()
    assert "--port" in cmd
    assert "8100" in cmd


def test_local_adk_command_custom_host(monkeypatch) -> None:
    """Custom host in command."""
    clear_port_env_vars(monkeypatch)
    cmd = get_local_adk_command("0.0.0.0")
    assert "--host" in cmd
    assert "0.0.0.0" in cmd


# ===================================================================
# PortsConfig dataclass
# ===================================================================


def test_ports_config_dataclass(monkeypatch, tmp_path: Path) -> None:
    """PortsConfig is frozen and has all expected fields."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_HOME", str(tmp_path))
    config = load_ports_config()
    assert config.adk == 8000
    assert config.web == 8001
    assert config.frontend == 5173
    assert config.server_proxy == 80
    assert config.worker_base == 9001
    assert config.mcp_host == "localhost"
    assert config.mcp_database == 50001
    assert config.mcp_dpa == 50002
    assert config.mcp_abacus == 50003
    assert config.mcp_structure == 50004
    assert config.mcp_vasp == 50005
    assert config.mcp_mattergen == 50006

    # Verify frozen — assignment must raise FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        config.adk = 9000  # type: ignore[misc]


# ===================================================================
# Config path via MATCREATOR_HOME
# ===================================================================


def test_config_path_from_matcreator_home(tmp_path: Path, monkeypatch) -> None:
    """MATCREATOR_HOME env var changes config path."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_HOME", str(tmp_path))

    _write_config_yaml(
        tmp_path,
        {
            "adk": 8300,
            "web": 8301,
            "mcp_host": "remote.host",
        },
    )

    config = load_ports_config()
    assert config.adk == 8300
    assert config.web == 8301
    assert config.mcp_host == "remote.host"
    # Fields not in config fall back to defaults
    assert config.frontend == 5173
