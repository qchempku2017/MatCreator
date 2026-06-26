"""Port configuration layer for MatCreator.

Resolves port values with precedence:
    environment variables > ~/.matcreator/config.yaml > defaults

All functions are pure and side-effect-free at import time — values are resolved when
called, making the module easy to test without starting any services.

Config file integration
-----------------------
The config file is read from ``~/.matcreator/config.yaml`` by default.  Set the
``MATCREATOR_HOME`` environment variable to point at a different directory (the file
is assumed to be named ``config.yaml`` inside that directory).

The ``ports`` section of the YAML file is read:

.. code-block:: yaml

    ports:
      adk: 8100
      web: 8101
      frontend: 5174
      server_proxy: 8080
      worker_base: 9101
      mcp_host: localhost
      mcp:
        database: 51001
        dpa: 51002
        abacus: 51003
        structure: 51004
        vasp: 51005
        mattergen: 51006

Legacy alias
------------
``ADK_LOCAL_PORT`` is recognised as a legacy alias for ``MATCREATOR_ADK_PORT``.
When both are present, ``MATCREATOR_ADK_PORT`` takes precedence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Default port values
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, int | str] = {
    "adk": 8000,
    "web": 8001,
    "frontend": 5173,
    "server_proxy": 80,
    "worker_base": 9001,
    "mcp_host": "localhost",
    "mcp_database": 50001,
    "mcp_dpa": 50002,
    "mcp_abacus": 50003,
    "mcp_structure": 50004,
    "mcp_vasp": 50005,
    "mcp_mattergen": 50006,
}

# ---------------------------------------------------------------------------
# Environment variable name mapping (port names -> env var names)
# ---------------------------------------------------------------------------

_ENV_VAR_MAP: dict[str, str] = {
    "adk": "MATCREATOR_ADK_PORT",
    "web": "MATCREATOR_WEB_PORT",
    "frontend": "MATCREATOR_FRONTEND_PORT",
    "server_proxy": "MATCREATOR_SERVER_PROXY_PORT",
    "worker_base": "MATCREATOR_WORKER_BASE_PORT",
    "mcp_host": "MATCREATOR_MCP_HOST",
    "mcp_database": "MATCREATOR_MCP_DATABASE_PORT",
    "mcp_dpa": "MATCREATOR_MCP_DPA_PORT",
    "mcp_abacus": "MATCREATOR_MCP_ABACUS_PORT",
    "mcp_structure": "MATCREATOR_MCP_STRUCTURE_PORT",
    "mcp_vasp": "MATCREATOR_MCP_VASP_PORT",
    "mcp_mattergen": "MATCREATOR_MCP_MATTERGEN_PORT",
}

# Full URL overrides for MCP endpoints (endpoint name -> env var name)
_MCP_URL_ENV_MAP: dict[str, str] = {
    "database": "MATCREATOR_MCP_DATABASE_URL",
    "dpa": "MATCREATOR_MCP_DPA_URL",
    "abacus": "MATCREATOR_MCP_ABACUS_URL",
    "structure": "MATCREATOR_MCP_STRUCTURE_URL",
    "vasp": "MATCREATOR_MCP_VASP_URL",
    "mattergen": "MATCREATOR_MCP_MATTERGEN_URL",
}

# Legacy aliases: primary env var name -> legacy env var name
_LEGACY_ENV_MAP: dict[str, str] = {
    "MATCREATOR_ADK_PORT": "ADK_LOCAL_PORT",
}

# Mapping from MCP endpoint name to the port config attribute key
_MCP_NAME_TO_PORT_KEY: dict[str, str] = {
    "database": "mcp_database",
    "dpa": "mcp_dpa",
    "abacus": "mcp_abacus",
    "structure": "mcp_structure",
    "vasp": "mcp_vasp",
    "mattergen": "mcp_mattergen",
}


# ---------------------------------------------------------------------------
# Config file helpers
# ---------------------------------------------------------------------------

def _get_config_path() -> str:
    """Return the path to the YAML config file.

    Uses ``MATCREATOR_HOME`` env var if set and non-empty, otherwise defaults to
    ``~/.matcreator/config.yaml``.
    """
    matcreator_home = os.environ.get("MATCREATOR_HOME", "").strip()
    if matcreator_home:
        return os.path.join(matcreator_home, "config.yaml")
    return os.path.expanduser("~/.matcreator/config.yaml")


def _read_yaml_config() -> dict[str, Any]:
    """Read and parse the YAML config file.

    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    config_path = _get_config_path()
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except (FileNotFoundError, yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _get_config_file_value(key: str) -> Any:
    """Return a value from the ``ports`` section of the config file.

    *key* may be a dotted path such as ``"mcp.database"`` to reach nested dicts.
    Returns ``None`` when the key is absent.
    """
    cfg = _read_yaml_config()
    ports = cfg.get("ports")
    if not isinstance(ports, dict):
        return None

    parts = key.split(".", 1)
    if len(parts) == 1:
        return ports.get(key)
    else:
        section = ports.get(parts[0])
        if isinstance(section, dict):
            return section.get(parts[1])
        return None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_port(value: Any, name: str) -> int:
    """Validate that *value* is a valid TCP port number and return it as an int.

    Args:
        value: The raw value to validate (may be int, str, or other).
        name: Human-readable name used in error messages.

    Returns:
        The validated port number as an :class:`int`.

    Raises:
        ValueError: If the value is not a valid port (non-integer, < 1, or > 65535).
    """
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"Invalid port for {name!r}: {value!r}. "
            f"Port must be an integer between 1 and 65535."
        )
    if port < 1 or port > 65535:
        raise ValueError(
            f"Invalid port for {name!r}: {value!r}. "
            f"Port must be an integer between 1 and 65535."
        )
    return port


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

def _resolve_env_var(env_name: str) -> str | None:
    """Return the value of *env_name* from the environment, checking legacy aliases.

    If the primary env var is set, its value is returned directly.  Otherwise, if a
    legacy alias exists and is set, the legacy value is returned.
    """
    value = os.environ.get(env_name)
    if value is not None:
        return value
    legacy = _LEGACY_ENV_MAP.get(env_name)
    if legacy is not None:
        return os.environ.get(legacy)
    return None


def _resolve_port_value(name: str, config_file_key: str) -> int:
    """Resolve a single port value using env > config file > default.

    Args:
        name: Internal key name (e.g. ``"adk"``, ``"mcp_database"``).
        config_file_key: Dotted key within the ``ports`` section of config.yaml
            (e.g. ``"mcp.database"``).

    Returns:
        The resolved port number as an :class:`int`.
    """
    # 1. Environment variable
    env_name = _ENV_VAR_MAP.get(name)
    if env_name:
        env_value = _resolve_env_var(env_name)
        if env_value is not None:
            return _validate_port(env_value, name)

    # 2. Config file
    config_value = _get_config_file_value(config_file_key)
    if config_value is not None:
        return _validate_port(config_value, name)

    # 3. Default
    default = _DEFAULTS.get(name)
    if default is not None:
        return _validate_port(default, name)

    raise ValueError(f"No default value defined for port {name!r}.")


def _resolve_string_value(name: str, config_file_key: str) -> str:
    """Resolve a string config value (e.g. ``mcp_host``) using env > config > default."""
    # 1. Environment variable
    env_name = _ENV_VAR_MAP.get(name)
    if env_name:
        env_value = _resolve_env_var(env_name)
        if env_value is not None:
            return str(env_value)

    # 2. Config file
    config_value = _get_config_file_value(config_file_key)
    if config_value is not None:
        return str(config_value)

    # 3. Default
    default = _DEFAULTS.get(name)
    return str(default) if default is not None else "localhost"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PortsConfig:
    """Immutable snapshot of all resolved port configuration values.

    Every port field is a validated integer in the range 1–65535
    (``mcp_host`` is a string).
    """

    adk: int
    """ADK API server port (default: 8000)."""

    web: int
    """FastAPI web / control-plane port (default: 8001)."""

    frontend: int
    """Vite frontend dev-server port (default: 5173)."""

    server_proxy: int
    """Nginx server-proxy port (default: 80)."""

    worker_base: int
    """Worker base port for host-port allocation (default: 9001)."""

    mcp_host: str
    """Hostname or IP used to construct MCP endpoint URLs (default: localhost)."""

    mcp_database: int
    """Database MCP server port (default: 50001)."""

    mcp_dpa: int
    """DPA MCP server port (default: 50002)."""

    mcp_abacus: int
    """ABACUS MCP server port (default: 50003)."""

    mcp_structure: int
    """Structure MCP server port (default: 50004)."""

    mcp_vasp: int
    """VASP MCP server port (default: 50005)."""

    mcp_mattergen: int
    """MatterGen MCP server port (default: 50006)."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_ports_config() -> PortsConfig:
    """Resolve all port values and return a frozen :class:`PortsConfig`.

    Precedence: environment variables > config.yaml > defaults.

    Every integer port is validated to be in the range 1–65535.
    """
    return PortsConfig(
        adk=_resolve_port_value("adk", "adk"),
        web=_resolve_port_value("web", "web"),
        frontend=_resolve_port_value("frontend", "frontend"),
        server_proxy=_resolve_port_value("server_proxy", "server_proxy"),
        worker_base=_resolve_port_value("worker_base", "worker_base"),
        mcp_host=_resolve_string_value("mcp_host", "mcp_host"),
        mcp_database=_resolve_port_value("mcp_database", "mcp.database"),
        mcp_dpa=_resolve_port_value("mcp_dpa", "mcp.dpa"),
        mcp_abacus=_resolve_port_value("mcp_abacus", "mcp.abacus"),
        mcp_structure=_resolve_port_value("mcp_structure", "mcp.structure"),
        mcp_vasp=_resolve_port_value("mcp_vasp", "mcp.vasp"),
        mcp_mattergen=_resolve_port_value("mcp_mattergen", "mcp.mattergen"),
    )


def get_adk_port() -> int:
    """Return the resolved ADK API server port."""
    return _resolve_port_value("adk", "adk")


def get_web_port() -> int:
    """Return the resolved web (FastAPI) server port."""
    return _resolve_port_value("web", "web")


def get_frontend_port() -> int:
    """Return the resolved frontend (Vite) dev-server port."""
    return _resolve_port_value("frontend", "frontend")


def get_server_proxy_port() -> int:
    """Return the resolved server proxy (nginx) port."""
    return _resolve_port_value("server_proxy", "server_proxy")


def get_worker_base_port() -> int:
    """Return the resolved worker base port."""
    return _resolve_port_value("worker_base", "worker_base")


def get_mcp_endpoint_url(name: str) -> str:
    """Build the SSE endpoint URL for a named MCP server.

    Supported names: ``database``, ``dpa``, ``abacus``, ``structure``, ``vasp``,
    ``mattergen``.

    If a full URL override environment variable (e.g.
    ``MATCREATOR_MCP_DATABASE_URL``) is set, that value is returned directly.
    Otherwise the URL is constructed as ``http://{host}:{port}/sse`` using the
    resolved host and port values.

    Args:
        name: The MCP endpoint name (case-sensitive).

    Returns:
        The full SSE endpoint URL string.

    Raises:
        ValueError: If *name* is not a recognised MCP endpoint.
    """
    if name not in _MCP_NAME_TO_PORT_KEY:
        raise ValueError(
            f"Unknown MCP endpoint name {name!r}. "
            f"Expected one of: {', '.join(sorted(_MCP_NAME_TO_PORT_KEY))}."
        )

    # Full URL override via env var takes highest precedence
    url_env = _MCP_URL_ENV_MAP.get(name)
    if url_env:
        url_value = os.environ.get(url_env)
        if url_value is not None:
            return url_value

    # Construct URL from host + port
    host = _resolve_string_value("mcp_host", "mcp_host")
    port_key = _MCP_NAME_TO_PORT_KEY[name]
    port = _resolve_port_value(port_key, f"mcp.{name}")
    return f"http://{host}:{port}/sse"


def get_local_adk_command(host: str = "127.0.0.1") -> list[str]:
    """Return the command list for starting the ADK API server locally.

    Args:
        host: The binding host address.  Defaults to ``127.0.0.1``.

    Returns:
        A list of command-line tokens, e.g.
        ``["matcreator", "api-server", "--host", "127.0.0.1", "--port", "8000"]``.
    """
    port = get_adk_port()
    return ["matcreator", "api-server", "--host", host, "--port", str(port)]
