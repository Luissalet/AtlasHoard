"""API routers: one per area, the agent contract and the PWA files."""

from .ach import router as ach_router
from .agent import router as agent_router
from .analysis import router as analysis_router
from .cases import router as cases_router
from .enrich import router as enrich_router
from .entities import router as entities_router
from .health import router as health_router
from .history import router as history_router
from .pwa import router as pwa_router
from .relations import router as relations_router
from .reports import router as reports_router
from .settings import router as settings_router
from .sources import router as sources_router

ROUTERS = [health_router, cases_router, sources_router, entities_router, relations_router, analysis_router, ach_router,
           enrich_router, reports_router, history_router, settings_router, agent_router, pwa_router]
