"""Integration layer for WorkflowMemoryService with PFD agent.

Shows how to control when workflow steps are logged to the database.
"""

from typing import Optional, Dict, Any, Iterable
from matcreator.memory.workflow_memory_service import WorkflowMemoryService


class WorkflowMemoryIntegration:
    """Handles integration between tool callbacks and WorkflowMemoryService.
    
    This class answers the question: "How do I control when add_workflow_step is executed?"
    
    Answer: Through the after_tool_callback, which YOU control via the allowed tools list.
    """
    
    def __init__(
        self, 
        memory_service: WorkflowMemoryService,
        allowed_tools: set[str],
        step_name_map: Optional[Dict[str, str]] = None
    ):
        """Initialize the integration.
        
        Args:
            memory_service: The WorkflowMemoryService instance
            allowed_tools: Set of tool names to log (YOU control this)
            step_name_map: Optional mapping of tool names to workflow step names
        """
        self.memory_service = memory_service
        self.allowed_tools = allowed_tools
        self.step_name_map = step_name_map or {}
    
    def create_after_tool_callback(
        self,
        include_input_keys: Optional[Iterable[str]] = None,
        include_output_keys: Optional[Iterable[str]] = None
    ):
        """Factory method to create the after_tool_callback function.
        
        This is what you pass to your agent's after_tool_callback parameter.
        """
        async def after_tool_callback(tool, args, tool_context, tool_response):
            """The actual callback that ADK calls after each tool execution.
            
            YOU CONTROL WHEN THIS EXECUTES via:
            1. The 'allowed_tools' set - only logs specified tools
            2. The agent configuration - which agents get this callback
            3. The tool_context.session - provides session context
            
            ADK runtime automatically calls this AFTER any tool execution,
            but we filter to only log workflow-critical tools.
            """
            tool_name = getattr(tool, 'name', None)
            
            # CONTROL POINT 1: Only log allowed tools
            if tool_name not in self.allowed_tools:
                return tool_response
            
            # CONTROL POINT 2: Only log if we have a valid session context
            if not tool_context or not hasattr(tool_context, 'session'):
                return tool_response
            
            try:
                # Map tool name to workflow step name
                step_name = self.step_name_map.get(tool_name, tool_name)
                
                # Extract input/output data (with optional filtering)
                input_data = self._extract_data(args, include_input_keys)
                output_data = self._extract_data(
                    self._parse_tool_response(tool_response),
                    include_output_keys
                )
                
                # Extract status from response
                status = output_data.get('status', 'completed') if isinstance(output_data, dict) else 'completed'
                
                # LOG TO DATABASE - This is where add_workflow_step is called
                await self.memory_service.add_workflow_step(
                    session=tool_context.session,
                    step_name=step_name,
                    status=status,
                    input_data=input_data,
                    output_data=output_data
                )
                
            except Exception as exc:
                # Never let logging break tool execution
                print(f"Warning: Failed to log workflow step: {exc}")
            
            return tool_response
        
        return after_tool_callback
    
    def _extract_data(self, data: Any, keys: Optional[Iterable[str]]) -> Dict[str, Any]:
        """Extract and filter data for logging."""
        if not isinstance(data, dict):
            return {}
        if not keys:
            return self._to_json_safe(data)
        return {k: self._to_json_safe(data.get(k)) for k in keys if k in data}
    
    def _parse_tool_response(self, tool_response) -> Dict[str, Any]:
        """Parse tool response to extract structured content."""
        try:
            # ADK tool responses have this structure
            return tool_response.get('structuredContent', {}).get('result', {})
        except (AttributeError, KeyError):
            return tool_response if isinstance(tool_response, dict) else {}
    
    def _to_json_safe(self, x: Any) -> Any:
        """Convert data to JSON-safe format."""
        from pathlib import Path
        if isinstance(x, Path):
            return str(x)
        if isinstance(x, dict):
            return {k: self._to_json_safe(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [self._to_json_safe(v) for v in x]
        return x


# Example usage in your agent.py:
"""
from matcreator.memory.workflow_memory_service import WorkflowMemoryService
from matcreator.memory.integration import WorkflowMemoryIntegration

# Initialize the memory service (do this once at module level or in agent init)
workflow_memory = WorkflowMemoryService("sqlite:///pfd_workflows.db")

# Configure which tools to log (YOU CONTROL THIS)
allowed_tools = {
    "abacus_prepare", 
    "abacus_calculation_scf", 
    "collect_abacus_scf_results",
    "training",
    "run_molecular_dynamics",
    "filter_by_entropy",
    "perturb_atoms"
}

step_name_map = {
    "abacus_prepare": "labeling_abacus_scf_preparation",
    "abacus_calculation_scf": "labeling_abacus_scf_calculation",  
    "collect_abacus_scf_results": "labeling_abacus_scf_collect_results",
    "run_molecular_dynamics": "exploration_md",
    "filter_by_entropy": "explore_filter_by_entropy"
}

# Create integration
integration = WorkflowMemoryIntegration(
    memory_service=workflow_memory,
    allowed_tools=allowed_tools,
    step_name_map=step_name_map
)

# Get the callback function
after_tool_callback = integration.create_after_tool_callback()

# Pass it to your agent
pfd_agent = LlmAgent(
    name='pfd_agent',
    model=...,
    tools=[...],
    after_tool_callback=after_tool_callback,  # <-- ADK calls this automatically
    sub_agents=[...]
)

# Also need to create workflow session when workflow starts
# Add this as a tool or in create_workflow_log:
async def on_workflow_created(session, workflow_name, **metadata):
    await workflow_memory.create_workflow_session(
        session=session,
        workflow_name=workflow_name,
        **metadata
    )
"""
