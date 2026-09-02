"""Agent Safety Gateway API endpoints.

Re-export facade: routes are split into agent_api_core (Kill Switch,
Circuit Breaker, Budget, Journal) and agent_api_governance (Approval Gate,
Scope Fence, Auto-Approve, Tool Classification, Undo, Anomaly, Audit).
"""

from quart import Blueprint

bp = Blueprint("agent_api", __name__)

# Register all routes from sub-modules onto this single blueprint
from routes.agent_api_core import register_routes as _register_core
from routes.agent_api_governance import register_routes as _register_governance

_register_core(bp)
_register_governance(bp)
