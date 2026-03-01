from google.adk.agents import LlmAgent, InvocationContext, LoopAgent, BaseAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.tools.function_tool import FunctionTool
from google.adk.events import Event, EventActions
from google.genai.types import Content,Part
import os
import logging
from enum import Enum
from .thinking_agent import thinking_agent
from .approval_agent import approval_agent
from .execution_agent import build_execution_agent
from .summarize_agent import summarize_agent
from .constants import LLM_MODEL, LLM_API_KEY, LLM_BASE_URL
from .callbacks import (
    set_session_metadata,
    get_session_context,
    get_session_metadata
)

AGENT_CARD_WELL_KNOWN_PATH=".well-known/agent-card.json"

model_name = os.environ.get("LLM_MODEL", LLM_MODEL)
model_api_key = os.environ.get("LLM_API_KEY", LLM_API_KEY)
model_base_url = os.environ.get("LLM_BASE_URL", LLM_BASE_URL)

logger = logging.getLogger(__name__)

description="""
You are the MatCreator Agent. You orchestrate computational materials science workflows through 
a structured thinking-execution cycle, ensuring user visibility and approval before expensive operations.
""" 

global_instruction = """
General rules for all agents:
- Only call tools that are available in your current context.
- Keep responses concise; include key artifacts with absolute paths and relevant metrics.
- When encountering errors, quote the exact error message and propose concrete solutions.
"""

# Root agent coordinates the phase-based thinking-execution workflow
root_instruction = """
You are the MatCreator orchestration agent. You coordinate computational materials science workflows 
through a phase-based thinking-execution cycle.

**Your role:**
You DO NOT execute tasks directly. You route work using the session phase:

1. **phase=thinking** → delegate to **thinking_agent**
2. **phase=execution** → delegate to **execution_agent**

**Your job:**
- Transfer to the appropriate agent based on phase only
- Let thinking_agent handle intent clarification, plan drafting, and plan approval handling
- Let execution_agent handle all approved task execution

**Critical rules:**
1. NEVER execute tasks yourself - always delegate to the appropriate agent
2. Trust the phase state variable (thinking/execution)
3. Keep your messages minimal - let the specialized agents communicate with users
4. If phase is invalid or missing, normalize to thinking
"""
class WorkflowStep(int,Enum):
    THINKING_PHASE=1
    APPROVAL_PAHSE=2
    EXECUTION_PAHSE=3
    SUMMARIZING_PHASE=4

class MatCreatorFlowAgent(BaseAgent):
    """Root agent with enforced phase-based routing."""

    workflow_step: WorkflowStep = WorkflowStep.THINKING_PHASE
    
    @staticmethod
    def _normalize_phase(state: dict) -> str:
        """Normalize phase from current state, using legacy flags as fallback."""
        phase = state.get("phase")
        if phase in {"thinking", "execution"}:
            return phase

        if state.get("execution_started", False) and not state.get("execution_complete", False):
            phase = "execution"
        else:
            phase = "thinking"

        state["phase"] = phase
        return phase
    
    async def _run_async_impl_tmp(self, ctx: InvocationContext):
        """Loop thinking/execution until approval check requests return."""
        
        
        while True:
            state = ctx.session.state
            print("[CHECKPOINT]",state["phase"])
            if state["phase"]=="thinking":
                print("[AGENT]: Runtime activated")
                async for event in thinking_agent.run_async(ctx):
                    yield event

            #if not ctx.session.state.get("approval", False):
            #    return


            if state['phase']=='execution':
                print("[AGENT]: Execution phase")
                _exec_agent = build_execution_agent(ctx.session.state.get("plan", {}))
                async for event in _exec_agent.run_async(ctx):
                    yield event

                state['phase']="thinking"
                async for event in summarize_agent.run_async(ctx):
                    yield event
            else:
                return
        
    async def _run_async_impl_cycle_tmp(self, ctx: InvocationContext):
        """Route to the correct workflow phase, persisting step in session.state."""
        state = ctx.session.state

        logger.info(f"[{self.name}]: step={self.workflow_step}")

        if self.workflow_step <= WorkflowStep.THINKING_PHASE:
            logger.info(f"[{self.name}]: Starting thinking")
            async for event in thinking_agent.run_async(ctx):
                yield event

            if state.get("approval", False):
                # thinking_agent presented a plan but user hasn't approved yet;
                # stay at THINKING_PHASE so next turn re-enters here.
                
                self.workflow_step = WorkflowStep.APPROVAL_PAHSE
                logger.info(f"[{self.name}]: Waiting for user approval.")
                return

            # thinking_agent set approval=True inline — advance to approval step
            #state["workflow_step"] = WorkflowStep.APPROVAL_PAHSE
            return

        if self.workflow_step <= WorkflowStep.APPROVAL_PAHSE:
            logger.info(f"[{self.name}]: Running approval inference")
            async for event in approval_agent.run_async(ctx):
                yield event

            if not state.get("approval", False):
                # User did not approve; approval_agent already reset phase/plan
                state["workflow_step"] = WorkflowStep.THINKING_PHASE
                logger.info(f"[{self.name}]: Approval denied → returning to thinking phase.")
                return

            state["workflow_step"] = WorkflowStep.EXECUTION_PAHSE

        if state.get("workflow_step",WorkflowStep.THINKING_PHASE) <= WorkflowStep.EXECUTION_PAHSE:
            logger.info(f"[{self.name}]: Execution phase")
            _exec_agent = build_execution_agent(state.get("plan", {}))
            async for event in _exec_agent.run_async(ctx):
                yield event
            state["workflow_step"] = WorkflowStep.SUMMARIZING_PHASE

        if state.get("workflow_step",WorkflowStep.THINKING_PHASE) <= WorkflowStep.SUMMARIZING_PHASE:
            logger.info(f"[{self.name}]: Summarizing result")
            async for event in summarize_agent.run_async(ctx):
                yield event

        # Workflow complete — reset for the next task
        state["workflow_step"] = WorkflowStep.THINKING_PHASE
        state["approval"] = False
        logger.info(f"[{self.name}] Workflow finished.")



    async def _run_async_impl_cycle(self, ctx: InvocationContext):
        """Route to the correct workflow phase, persisting step in session.state."""
        state = ctx.session.state
        logger.info(f"[{self.name}]: step={self.workflow_step}")


        if ctx.session.state["phase"]=="thinking":
            logger.info(f"[{self.name}]: Starting thinking")
            async for event in thinking_agent.run_async(ctx):
                yield event

            if not state.get("approval", False):
                return
            event_action = EventActions(state_delta={"phase":"execution"})
            event = Event(
                content=Content(parts=[Part(text=f"🚀 Starting execution")]),
                author=self.name,
                actions=event_action
        )
            yield event
            
        if ctx.session.state["phase"]=="execution":
            logger.info(f"[{self.name}]: Execution phase")
            _exec_agent = build_execution_agent(ctx.session.state.get("plan", {}))
            async for event in _exec_agent.run_async(ctx):
                yield event
                
            event_action = EventActions(state_delta={"phase":"summarize"})
            event = Event(
                content=Content(parts=[Part(text=f"Summarizing results")]),
                author=self.name,
                actions=event_action
        )
            yield event


        if ctx.session.state["phase"]=="summarize":
            logger.info(f"[{self.name}]: Summarizing result")
            async for event in summarize_agent.run_async(ctx):
                yield event
                
                
            event_action = EventActions(state_delta={"phase":"thinking"})
            event = Event(
                content=Content(parts=[Part(text=f"thinking...")]),
                author=self.name,
                actions=event_action
        )
            yield event


    async def _run_async_impl(self, ctx: InvocationContext):
        while True:
            async for event in self._run_async_impl_cycle(ctx):
                yield event
            if not ctx.session.state.get("approval",False):
                break
                
        
            

def before_agent_callback_root(callback_context: CallbackContext):
    """Set environment variables and initialize session state for MatCreator agent."""
    session_id = callback_context._invocation_context.session.id
    user_id = callback_context._invocation_context.session.user_id
    app_name = callback_context._invocation_context.session.app_name
    
    # Set environment variables for session context
    os.environ["CURRENT_SESSION_ID"] = session_id
    os.environ["CURRENT_USER_ID"] = user_id
    os.environ["CURRENT_APP_NAME"] = app_name
    
    # Initialize session state variables if not present
    state = callback_context._invocation_context.session.state
    if 'phase' not in state:
        callback_context.state['phase']='thinking'

    # Legacy state defaults kept temporarily for migration compatibility
    if 'plan' not in state:
        callback_context.state['plan'] = None
        
    if 'detailed_steps' not in state:
        callback_context.state['detailed_steps'] = None
        
    if 'goal' not in state:
        callback_context.state['goal'] = None
    
    if 'approval' not in state:
        callback_context.state['approval'] = False
        
    if 'summarize' not in state:
        callback_context.state['summarize'] = None
        
    if 'skills' not in state:
        callback_context.state['skills'] = None
    
    if 'execution_started' not in state:
        callback_context.state['execution_started'] = False
    
    if 'execution_complete' not in state:
        callback_context.state['execution_complete'] = False

    if 'execution_history' not in state:
        callback_context.state['execution_history'] = []

    if 'execution_last_output' not in state:
        callback_context.state['execution_last_output'] = ""
    
    if 'goal_achieved' not in state:
        callback_context.state['goal_achieved'] = False
    
    if 'needs_replanning' not in state:
        callback_context.state['needs_replanning'] = False

    if 'workflow_step' not in state:
        callback_context.state['workflow_step'] = WorkflowStep.THINKING_PHASE
    
    # Initialize session metadata in database if not already exists
    try:
        from .callbacks import get_session_metadata
        existing_metadata = get_session_metadata(session_id)
        if not existing_metadata:
            set_session_metadata(
                session_id=session_id,
                additional_metadata={"initialized_by": "root_agent"}
            )
    except Exception as e:
        print(f"Warning: Failed to initialize session metadata: {e}")
    
    return None


tools = [
    set_session_metadata, 
    get_session_context,
    get_session_metadata
    ]

remote_a2a_url="http://localhost:8001/"
structure_builder_agent = RemoteA2aAgent(
    name="structure_builder_agent",
    description="",
    agent_card=f"{remote_a2a_url}{AGENT_CARD_WELL_KNOWN_PATH}",
)


_root_agent = MatCreatorFlowAgent(
    name='MatCreator_agent',
    #model=LiteLlm(
    #    model=model_name,
    #    base_url=model_base_url,
    #    api_key=model_api_key
    #),
    #description=description,
    #instruction=root_instruction, 
    #global_instruction=global_instruction,
    before_agent_callback=before_agent_callback_root,
    #tools=[set_session_metadata, get_session_context, get_session_metadata],
    sub_agents=[
        thinking_agent,
        approval_agent,
        # execution_agent is built dynamically by build_execution_agent() at runtime
    ]
    )


app = App(
    name="MatCreator",
    root_agent=_root_agent,
    resumability_config=ResumabilityConfig(
        is_resumable=True,
    ),
    # Optionally include App-level features:
    # plugins, context_cache_config, resumability_config
)