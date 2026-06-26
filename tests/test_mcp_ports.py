"""Tests for MCP endpoint URL resolution from src.matcreator.ports.

These are static tests that require no Docker, no network, no services.
They verify the get_mcp_endpoint_url() function against its defaults and
environment variable overrides.
"""

from __future__ import annotations

import os

import pytest

from src.matcreator.ports import get_mcp_endpoint_url


from conftest import ALL_PORT_ENV_VARS, clear_port_env_vars  # noqa: F401


# ===================================================================
# Default endpoint URL tests
# ===================================================================


def test_mcp_database_default(monkeypatch) -> None:
    """get_mcp_endpoint_url('database') returns default URL."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("database") == "http://localhost:50001/sse"


def test_mcp_dpa_default(monkeypatch) -> None:
    """get_mcp_endpoint_url('dpa') returns default URL."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("dpa") == "http://localhost:50002/sse"


def test_mcp_abacus_default(monkeypatch) -> None:
    """get_mcp_endpoint_url('abacus') returns default URL."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("abacus") == "http://localhost:50003/sse"


def test_mcp_structure_default(monkeypatch) -> None:
    """get_mcp_endpoint_url('structure') returns default URL."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("structure") == "http://localhost:50004/sse"


def test_mcp_vasp_default(monkeypatch) -> None:
    """get_mcp_endpoint_url('vasp') returns default URL."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("vasp") == "http://localhost:50005/sse"


def test_mcp_mattergen_default(monkeypatch) -> None:
    """get_mcp_endpoint_url('mattergen') returns default URL."""
    clear_port_env_vars(monkeypatch)
    assert get_mcp_endpoint_url("mattergen") == "http://localhost:50006/sse"


# ===================================================================
# Environment variable override tests
# ===================================================================


def test_mcp_host_override(monkeypatch) -> None:
    """MATCREATOR_MCP_HOST and MATCREATOR_MCP_VASP_PORT override the vasp URL."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_MCP_HOST", "host.docker.internal")
    monkeypatch.setenv("MATCREATOR_MCP_VASP_PORT", "51005")
    assert get_mcp_endpoint_url("vasp") == "http://host.docker.internal:51005/sse"


def test_mcp_full_url_override(monkeypatch) -> None:
    """MATCREATOR_MCP_DATABASE_URL overrides host+port construction."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_MCP_DATABASE_URL", "http://custom:9999/sse")
    assert get_mcp_endpoint_url("database") == "http://custom:9999/sse"


def test_mcp_full_url_wins_over_port(monkeypatch) -> None:
    """Full URL env var takes precedence over individual port env var."""
    clear_port_env_vars(monkeypatch)
    monkeypatch.setenv("MATCREATOR_MCP_DATABASE_URL", "http://custom:9999/sse")
    monkeypatch.setenv("MATCREATOR_MCP_DATABASE_PORT", "59999")
    assert get_mcp_endpoint_url("database") == "http://custom:9999/sse"


# ===================================================================
# Error handling tests
# ===================================================================


def test_mcp_unknown_endpoint(monkeypatch) -> None:
    """Unknown endpoint name raises ValueError."""
    clear_port_env_vars(monkeypatch)
    with pytest.raises(ValueError):
        get_mcp_endpoint_url("unknown")
