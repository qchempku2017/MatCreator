"""Execution agent for MatCreator - executes approved plans by delegating to domain agents."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import logging
from typing import Dict, Any, List
from google.adk.agents import LlmAgent, InvocationContext
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models.lite_llm import LiteLlm
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.adk.events import Event, EventActions
from google.genai.types import Content, Part
from .constants import (
    LLM_API_KEY, LLM_BASE_URL, 
    LLM_MODEL, 
    EXECUTION_ENABLE_WITHIN_INVOCATION_COMPACTION,
    EXECUTION_COMPACT_KEEP_TAIL,
    EXECUTION_COMPACT_EVERY_EVENTS,
)
from .callbacks import after_tool_callback
from .prompts.subagents import (
    SUBAGENTS,
)

_model_name = os.environ.get("LLM_MODEL", LLM_MODEL)
_model_api_key = os.environ.get("LLM_API_KEY", LLM_API_KEY)
_model_base_url = os.environ.get("LLM_BASE_URL", LLM_BASE_URL)
_EXECUTION_COMPACT_EVERY_EVENTS = int(os.environ.get("EXECUTION_COMPACT_EVERY_EVENTS", str(EXECUTION_COMPACT_EVERY_EVENTS)))
_EXECUTION_COMPACT_KEEP_TAIL = int(os.environ.get("EXECUTION_COMPACT_KEEP_TAIL", str(EXECUTION_COMPACT_KEEP_TAIL)))


def _env_flag(name: str, default: bool) -> bool:
    """Parse common truthy/falsey env var values with a safe default."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


_EXECUTION_ENABLE_WITHIN_INVOCATION_COMPACTION = _env_flag(
    "EXECUTION_ENABLE_WITHIN_INVOCATION_COMPACTION",
    EXECUTION_ENABLE_WITHIN_INVOCATION_COMPACTION,
)

logger = logging.getLogger()

_EXECUTION_INSTRUCTION = """
You are the execution agent. Your sole responsibility is to execute an approved plan by delegating to domain agents.

Plans: {detailed_steps}

Previous execution history: {summarize}
"""


def break_execution(tool_context: ToolContext) -> dict[str, str]:
    """If user want to stop execution immediately, call THIS to route control back to replanning."""
    tool_context.state["execution_complete"] = True
    tool_context.state["recommended_next_action"] = "replan"
    return {
        "status": "ok",
        "message": "Execution stopped. Control will return for replanning.",
    }


class ExecutionAgent(LlmAgent):
    """Agent that executes approved plans by orchestrating domain agents."""

    @staticmethod
    def _is_compaction_event(event: Event) -> bool:
        return bool(event.actions and event.actions.compaction)

    @classmethod
    def _events_to_compact_for_current_invocation(
        cls,
        *,
        events: List[Event],
        invocation_id: str,
        keep_tail: int,
    ) -> List[Event]:
        """Pick raw events for mid-invocation compaction for a single invocation id."""
        raw_events = [
            event
            for event in events
            if event.invocation_id == invocation_id and not cls._is_compaction_event(event)
        ]
        if len(raw_events) <= keep_tail:
            return []

        last_compacted_end_ts = 0.0
        for event in events:
            if event.invocation_id != invocation_id:
                continue
            if not cls._is_compaction_event(event):
                continue
            compaction = event.actions.compaction
            if compaction and compaction.end_timestamp is not None:
                last_compacted_end_ts = max(last_compacted_end_ts, compaction.end_timestamp)

        new_raw_events = [e for e in raw_events if e.timestamp > last_compacted_end_ts]
        if len(new_raw_events) <= keep_tail:
            return []

        return new_raw_events[:-keep_tail]

    @classmethod
    async def _compact_invocation_context_events(
        cls,
        *,
        ctx: InvocationContext,
        invocation_id: str,
        summarizer: LlmEventSummarizer,
    ) -> bool:
        """Compact current invocation events and append a compaction event to the session."""
        keep_tail = max(2, _EXECUTION_COMPACT_KEEP_TAIL)
        session_events = ctx.session.events
        new_session_events=[]
        candidate_events = cls._events_to_compact_for_current_invocation(
            events=session_events,
            invocation_id=invocation_id,
            keep_tail=keep_tail,
        )
        logger.info(
            "Mid-invocation compaction check: invocation_id=%s total_session_events=%d candidates=%d",
            invocation_id,
            len(session_events),
            len(candidate_events),
        )
        if not candidate_events:
            return False

        compaction_event = await summarizer.maybe_summarize_events(events=candidate_events)
        if compaction_event is None:
            return False

        compaction_event.invocation_id = invocation_id
        compaction_event.branch = getattr(ctx, "branch", None)

        await ctx.session_service.append_event(session=ctx.session, event=compaction_event)

        new_compaction = compaction_event.actions.compaction if compaction_event.actions else None
        if not new_compaction:
            return False

        start_ts = new_compaction.start_timestamp
        end_ts = new_compaction.end_timestamp

        # Rebuild the in-memory session events to discard compacted raw events.
        # Keep non-target invocation events as-is, keep compaction events, and
        # for target invocation keep only raw events outside the compacted range.
        new_session_events: List[Event] = []
        for existing_event in session_events:
            if existing_event.invocation_id != invocation_id:
                new_session_events.append(existing_event)
                continue

            #if cls._is_compaction_event(existing_event):
            #    new_session_events.append(existing_event)
            #    continue

            if start_ts <= existing_event.timestamp <= end_ts:
                continue

            new_session_events.append(existing_event)

        # Ensure current compaction summary exists exactly once.
        has_same_range = any(
            cls._is_compaction_event(event)
            and event.actions
            and event.actions.compaction
            and event.invocation_id == invocation_id
            and event.actions.compaction.start_timestamp == start_ts
            and event.actions.compaction.end_timestamp == end_ts
            for event in new_session_events
        )
        if not has_same_range:
            new_session_events.append(compaction_event)

        # Replace the live list object in place so downstream code sees compacted context.
        #session_events[:] = new_session_events
        ctx.session.events = new_session_events
        logger.info(
            "Mid-invocation compaction completed: invocation_id=%s compacted_events=%d new_total_events=%d",
            invocation_id,
            len(candidate_events),
            len(ctx.session.events),
        )

        ctx.session.state["execution_mid_invocation_compactions"] = int(
            ctx.session.state.get("execution_mid_invocation_compactions", 0)
        ) + 1
        compaction_text = cls._extract_event_text(compaction_event)
        if compaction_text:
            ctx.session.state["execution_mid_invocation_last_summary"] = compaction_text
        return True

    @staticmethod
    def _extract_event_text(event: Event) -> str:
        """Extract plain text content from an ADK event."""
        content = getattr(event, "content", None)
        if content is None:
            return ""
        parts = getattr(content, "parts", None) or []
        chunks: List[str] = []
        for part in parts:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return "\n".join(chunks)

    @classmethod
    def _save_key_execution_event(cls, state: Dict[str, Any], event: Event) -> None:
        """Save key execution event text to state['execution_history'] as a list."""
        text = cls._extract_event_text(event)
        if not text:
            return

        author = getattr(event, "author", "")
        entry = f"[{author}] {text}" if author else text

        history = state.get("execution_history")
        if not isinstance(history, list):
            history = []

        if not history or history[-1] != entry:
            history.append(entry)

        if len(history) > 200:
            history = history[-200:]

        state["execution_history"] = history
        state["execution_last_output"] = entry
    
    async def _run_async_impl(self, ctx: InvocationContext):
        """Execute the approved plan step by step."""
        
        # Read plan and guidance from session state
        plan = ctx.session.state.get('plan')
        goal = ctx.session.state.get('goal', '')
        
        if not plan:
            logger.error("No plan found in session state")
            yield Event(
                content=Content(parts=[Part(text="❌ Error: No execution plan found. Please create a plan first.")]),
                author=self.name
            )
            return
        
        # Mark execution as started
        state_update = {
            "execution_history": [],
            "execution_last_output": "",
            "execution_mid_invocation_event_count": 0,
            "execution_mid_invocation_compactions": 0,
            "execution_mid_invocation_last_summary": "",
            "execution_within_invocation_compaction_enabled": _EXECUTION_ENABLE_WITHIN_INVOCATION_COMPACTION,
        }
        ctx.session.state.update(state_update)
        compaction_summarizer = LlmEventSummarizer(
            llm=LiteLlm(
                model=_model_name,
                base_url=_model_base_url,
                api_key=_model_api_key,
            )
        )
        current_invocation_id = ""
        event_action = EventActions(state_delta=state_update)
        start_event = Event(
            #content=Content(parts=[Part(text=f"🚀 Starting execution: {goal}")]),
            author=self.name,
            actions=event_action
        )
        self._save_key_execution_event(ctx.session.state, start_event)
        yield start_event
        
        logger.info(f"Starting execution of plan: {goal}")
        logger.info(
            "Within-invocation compaction enabled: %s",
            _EXECUTION_ENABLE_WITHIN_INVOCATION_COMPACTION,
        )
    
        try:
            async for event in super()._run_async_impl(ctx):
                self._save_key_execution_event(ctx.session.state, event)
                if not current_invocation_id and getattr(event, "invocation_id", None):
                    current_invocation_id = str(event.invocation_id)
                ctx.session.state["execution_mid_invocation_event_count"] = int(
                    ctx.session.state.get("execution_mid_invocation_event_count", 0)
                ) + 1
                event_count = int(ctx.session.state["execution_mid_invocation_event_count"])
                if (
                    _EXECUTION_ENABLE_WITHIN_INVOCATION_COMPACTION
                    and current_invocation_id
                    and event_count % max(4, _EXECUTION_COMPACT_EVERY_EVENTS) == 0
                ):
                    try:
                        did_compact = await self._compact_invocation_context_events(
                            ctx=ctx,
                            invocation_id=current_invocation_id,
                            summarizer=compaction_summarizer,
                        )
                        if did_compact:
                            logger.info(
                                "Mid-invocation compaction appended to session events "
                                f"(invocation_id={current_invocation_id}, event_count={event_count})"
                            )
                    except Exception as compaction_exc:
                        logger.warning(f"Mid-invocation compaction skipped: {compaction_exc}")
                yield event
            logger.info("Plan execution completed")
            
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            error_event = Event(
                content=Content(parts=[Part(text=f"❌ Execution error: {str(e)}")]),
                author=self.name
            )
            self._save_key_execution_event(ctx.session.state, error_event)
            yield error_event
        finally:
            logger.info("Execution agent finished (assessment agent will determine next steps)")


# Module-level cache: plan fingerprint -> ExecutionAgent instance
_execution_agent_cache: dict[str, "ExecutionAgent"] = {}


def _plan_fingerprint(plan: dict) -> str:
    """Stable hash of the sorted agent names referenced in a plan."""
    steps = plan.get("steps", []) if isinstance(plan, dict) else []
    names = sorted({step["agent"] for step in steps if isinstance(step, dict) and "agent" in step})
    return hashlib.md5(json.dumps(names).encode()).hexdigest()


def _clone_agent(agent: LlmAgent) -> LlmAgent:
    """Return a shallow Pydantic copy of *agent* with its parent reference cleared.

    ADK enforces a single-parent constraint; cloning lets the same logical
    sub-agent be attached to multiple ExecutionAgent instances without collision.
    """
    cloned = agent.model_copy(deep=False)
    object.__setattr__(cloned, "_parent_agent", None)
    return cloned


def clear_execution_agent_cache() -> None:
    """Flush the cached execution agents (e.g. after hot-reloading sub-agents)."""
    _execution_agent_cache.clear()
    logger.info("[ExecutorFactory] Execution agent cache cleared.")


def build_execution_agent(plan: dict) -> ExecutionAgent:
    """Factory that instantiates an ExecutionAgent scoped to the agents named in *plan*.

    The set of required domain agents is derived from the ``agent`` field of each
    ``PlanStep`` in *plan*. Only agents present in the global SUBAGENTS registry are
    attached; unknown names are logged as warnings. If the plan is empty or malformed
    every registered sub-agent is attached as a safe fallback.

    Results are cached by plan fingerprint so the same ExecutionAgent instance is
    reused for identical agent sets, avoiding ADK's single-parent constraint.
    """
    fingerprint = _plan_fingerprint(plan)
    if fingerprint in _execution_agent_cache:
        logger.info(f"[ExecutorFactory] Reusing cached execution agent ({fingerprint[:8]})")
        return _execution_agent_cache[fingerprint]

    steps = plan.get("steps", []) if isinstance(plan, dict) else []
    needed_names: set[str] = {step["agent"] for step in steps if isinstance(step, dict) and "agent" in step}

    if needed_names:
        unknown = needed_names - SUBAGENTS.keys()
        if unknown:
            logger.warning(f"[ExecutorFactory] Plan references unknown agents: {unknown} — they will be skipped.")
        sub_agents = [_clone_agent(SUBAGENTS[name]) for name in needed_names if name in SUBAGENTS]
        logger.info(f"[ExecutorFactory] Attaching sub-agents: {[a.name for a in sub_agents]}")
    else:
        # Fallback: attach all registered agents when plan provides no agent names
        logger.warning("[ExecutorFactory] No agent names found in plan steps — attaching all sub-agents as fallback.")
        sub_agents = [_clone_agent(a) for a in SUBAGENTS.values()]

    agent = ExecutionAgent(
        name="execution_agent",
        model=LiteLlm(
            model=_model_name,
            base_url=_model_base_url,
            api_key=_model_api_key,
        ),
        description="Executes approved plans by delegating to domain-specific agents in sequence.",
        instruction=_EXECUTION_INSTRUCTION,
        after_tool_callback=after_tool_callback,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        tools=[FunctionTool(break_execution)],
        sub_agents=sub_agents,
    )

    _execution_agent_cache[fingerprint] = agent
    logger.info(f"[ExecutorFactory] Created and cached execution agent ({fingerprint[:8]})")
    return agent


# Export helpers
__all__ = [
    "build_execution_agent",
    "clear_execution_agent_cache",
]
