import subprocess
import yaml
import logging
from pathlib import Path

log = logging.getLogger(__name__)
CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "mcp_permissions.yaml"


class MCPGateway:
    """Manages MCP server subprocesses and enforces per-agent permissions."""

    def __init__(self, config_path: str = None):
        self.config_path = config_path or str(CONFIG_PATH)
        self.config = self._load_config()
        self.processes: dict[str, subprocess.Popen] = {}

    def _load_config(self) -> dict:
        try:
            with open(self.config_path) as f:
                return yaml.safe_load(f) or {}
        except FileNotFoundError:
            log.warning(f"MCP config not found at {self.config_path}, MCP disabled.")
            return {}

    def get_allowed_servers(self, agent_id: str) -> list[str]:
        perms = self.config.get("agent_permissions", {}).get(agent_id, {})
        return perms.get("allowed", [])

    def start_server(self, server_name: str) -> subprocess.Popen | None:
        if server_name in self.processes:
            return self.processes[server_name]

        servers = self.config.get("mcp_servers", {})
        server_config = servers.get(server_name)
        if not server_config:
            log.warning(f"MCP server '{server_name}' not defined in config.")
            return None

        try:
            proc = subprocess.Popen(
                server_config["command"].split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.processes[server_name] = proc
            log.info(f"Started MCP server: {server_name}")
            return proc
        except Exception as e:
            log.error(f"Failed to start MCP server '{server_name}': {e}")
            return None

    def stop_all(self):
        for name, proc in self.processes.items():
            proc.terminate()
            log.info(f"Stopped MCP server: {name}")
        self.processes.clear()
