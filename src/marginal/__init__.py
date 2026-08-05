"""MARGINAL: fund only the next agent action worth taking."""

from .adapters import (
    ActionDenied,
    BudgetedCallable,
    async_budgeted_call,
    async_funded_call,
    budgeted_call,
    extract_common_llm_usage,
    funded_call,
)
from .budget import BudgetExceeded, BudgetLedger, BudgetLimits, BudgetOverrun, BudgetUsage
from .estimator import ValueEstimator
from .killer_demo import run_killer_demo
from .models import Action, Allocation, Cost, Decision
from .policy import MarginalPolicy, PolicyConfig
from .trace import JsonlTraceSink
from .treasury import AuthorizationRequired, Treasury

__all__ = [
    "Action",
    "ActionDenied",
    "Allocation",
    "AuthorizationRequired",
    "BudgetExceeded",
    "BudgetLedger",
    "BudgetLimits",
    "BudgetOverrun",
    "BudgetUsage",
    "BudgetedCallable",
    "Cost",
    "Decision",
    "JsonlTraceSink",
    "MarginalPolicy",
    "PolicyConfig",
    "Treasury",
    "ValueEstimator",
    "async_budgeted_call",
    "async_funded_call",
    "budgeted_call",
    "extract_common_llm_usage",
    "funded_call",
    "run_killer_demo",
]

__version__ = "0.1.0"
