"""FastAPI REST, SSE, and Dual-Transport MCP API package."""

from smartrx_safety_agents.api.mcp_server import SmartRxMCPServer, attach_mcp_routes
from smartrx_safety_agents.api.server import create_app

__all__ = ["SmartRxMCPServer", "attach_mcp_routes", "create_app"]
