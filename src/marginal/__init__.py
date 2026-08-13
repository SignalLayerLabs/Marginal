"""MARGINAL: economically disciplined compute allocation for AI agents."""

from .adapters import (
    ActionDenied,
    BudgetedCallable,
    FailureUsageExtractor,
    async_budgeted_call,
    async_funded_call,
    budgeted_call,
    extract_common_llm_usage,
    extract_common_token_usage,
    funded_call,
)
from .budget import BudgetExceeded, BudgetLedger, BudgetLimits, BudgetOverrun, BudgetUsage
from .controls import (
    DiminishingReturnConfig,
    DiminishingReturnDetector,
    DiminishingReturnSignal,
    GovernanceTracker,
)
from .estimator import EstimatorIdentity, ValueEstimate, ValueEstimator
from .killer_demo import run_killer_demo
from .ledger import (
    LEDGER_SCHEMA_VERSION,
    DecisionLedgerContext,
    JsonlDecisionLedger,
    export_decision_ledger,
    read_decision_ledger,
    summarize_decision_ledger,
)
from .models import Action, Allocation, Cost, Decision, TokenUsage
from .modes import ExecutionMode
from .outcomes import Outcome
from .policy import MarginalPolicy, PolicyConfig, PolicyIdentity
from .privacy import (
    FIELD_CLASSIFICATION,
    LocalPseudonymizer,
    PrivacyClass,
    PrivacyConfig,
    PrivacyProfile,
    aggregate_ledger_records,
    classify_field,
    generate_local_identifier,
    load_or_create_privacy_key,
    sanitize_ledger_record,
    validate_safe_telemetry_record,
)
from .profiles import PolicyProfile, build_policy, policy_config_for_profile
from .protocol import (
    PROTOCOL_VERSION,
    AgentAction,
    AgentCapabilities,
    AgentDecision,
    AgentDirective,
    AgentEvent,
    AgentEventType,
    DeduplicationScope,
)
from .registry import EstimatorRegistry
from .replay import ReplayResult, render_replay_report, replay_ledger
from .runtime import UniversalRuntime
from .schema import available_schemas, load_schema
from .trace import CompositeTraceSink, JsonlTraceSink
from .treasury import AuthorizationRequired, Treasury

__all__ = [
    "FIELD_CLASSIFICATION",
    "LEDGER_SCHEMA_VERSION",
    "PROTOCOL_VERSION",
    "Action",
    "ActionDenied",
    "AgentAction",
    "AgentCapabilities",
    "AgentDecision",
    "AgentDirective",
    "AgentEvent",
    "AgentEventType",
    "Allocation",
    "AuthorizationRequired",
    "BudgetExceeded",
    "BudgetLedger",
    "BudgetLimits",
    "BudgetOverrun",
    "BudgetUsage",
    "BudgetedCallable",
    "CompositeTraceSink",
    "Cost",
    "Decision",
    "DecisionLedgerContext",
    "DeduplicationScope",
    "DiminishingReturnConfig",
    "DiminishingReturnDetector",
    "DiminishingReturnSignal",
    "EstimatorIdentity",
    "EstimatorRegistry",
    "ExecutionMode",
    "FailureUsageExtractor",
    "GovernanceTracker",
    "JsonlDecisionLedger",
    "JsonlTraceSink",
    "LocalPseudonymizer",
    "MarginalPolicy",
    "Outcome",
    "PolicyConfig",
    "PolicyIdentity",
    "PolicyProfile",
    "PrivacyClass",
    "PrivacyConfig",
    "PrivacyProfile",
    "ReplayResult",
    "TokenUsage",
    "Treasury",
    "UniversalRuntime",
    "ValueEstimate",
    "ValueEstimator",
    "aggregate_ledger_records",
    "async_budgeted_call",
    "async_funded_call",
    "available_schemas",
    "budgeted_call",
    "build_policy",
    "classify_field",
    "export_decision_ledger",
    "extract_common_llm_usage",
    "extract_common_token_usage",
    "funded_call",
    "generate_local_identifier",
    "load_or_create_privacy_key",
    "load_schema",
    "policy_config_for_profile",
    "read_decision_ledger",
    "render_replay_report",
    "replay_ledger",
    "run_killer_demo",
    "sanitize_ledger_record",
    "summarize_decision_ledger",
    "validate_safe_telemetry_record",
]

__version__ = "0.3.2"
