"""Strategy package for known ATS + generic DOM agent."""

from app.modules.form_fill_engine.strategies.generic_dom_agent import run_generic_dom_agent_strategy
from app.modules.form_fill_engine.strategies.greenhouse_strategy import run_greenhouse_strategy
from app.modules.form_fill_engine.strategies.lever_strategy import run_lever_strategy
from app.modules.form_fill_engine.strategies.workday_strategy import run_workday_strategy

__all__ = [
    "run_generic_dom_agent_strategy",
    "run_greenhouse_strategy",
    "run_lever_strategy",
    "run_workday_strategy",
]
