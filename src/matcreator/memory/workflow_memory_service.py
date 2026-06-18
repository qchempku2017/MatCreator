"""Workflow-specific memory service for PFD agent.

Stores workflow execution steps in a database with cleaner schema design.
Integrates with Google ADK's session system.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

from google.adk.memory.base_memory_service import BaseMemoryService, SearchMemoryResponse
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.sessions.session import Session
from google.adk.events.event import Event

from sqlalchemy import (
    Column, String, Integer, DateTime, JSON, ForeignKey,
    create_engine, select, and_, or_, desc
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class WorkflowSession(Base):
    """Metadata table - one row per workflow/session."""
    __tablename__ = 'workflow_sessions'
    
    # Primary key is the session_id (ADK session id)
    session_id = Column(String, primary_key=True)
    
    # Workflow metadata
    workflow_name = Column(String, nullable=False)  # pfd_finetune or pfd_distillation
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    
    # Optional fields from your current JSON structure
    planning_details = Column(String, nullable=True)
    material = Column(String, nullable=True)
    input_structure = Column(String, nullable=True)
    additional_metadata = Column(JSON, nullable=True)  # For flexibility
    
    # Relationship to steps
    steps = relationship("WorkflowStep", back_populates="session", cascade="all, delete-orphan")


class WorkflowStep(Base):
    """Steps table - cleaner, minimal columns."""
    __tablename__ = 'workflow_steps'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey('workflow_sessions.session_id'), nullable=False)
    
    # Core step information (mirrors your JSON structure)
    step_name = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False)  # completed, failed, running
    created_at = Column(DateTime, nullable=False, index=True)
    
    # Step data
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    notes = Column(String, nullable=True)
    
    # Derived fields for querying
    iteration = Column(Integer, nullable=True, index=True)  # PFD iteration number
    
    # Relationship back to session
    session = relationship("WorkflowSession", back_populates="steps")


class WorkflowMemoryService(BaseMemoryService):
    """Memory service for PFD workflow execution tracking.
    
    Usage:
        # Initialize with database URL
        memory = WorkflowMemoryService("sqlite:///workflows.db")
        
        # In your agent's after_tool_callback:
        await memory.add_workflow_step(
            session=tool_context.session,
            step_name="exploration_md",
            status="completed",
            input_data={"temperature": 700, "timestep": 0.5},
            output_data={"trajectory": "/path/to/traj.extxyz"}
        )
    """
    
    def __init__(self, db_url: str = "sqlite:///pfd_workflows.db", **kwargs):
        """Initialize the workflow memory service.
        
        Args:
            db_url: SQLAlchemy database URL. Defaults to SQLite file.
            **kwargs: Additional arguments for create_engine.
        """
        # For SQLite in-memory or file, use StaticPool for thread safety
        if db_url.startswith("sqlite"):
            kwargs.setdefault("connect_args", {"check_same_thread": False})
            kwargs.setdefault("poolclass", StaticPool)
        
        self.engine = create_engine(db_url, **kwargs)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    async def create_workflow_session(
        self,
        session: Session,
        workflow_name: str,
        planning_details: Optional[str] = None,
        **metadata
    ) -> WorkflowSession:
        """Create a new workflow session in the database.
        
        Call this when create_workflow_log is invoked.
        """
        with self.Session() as db_session:
            workflow_session = WorkflowSession(
                session_id=session.id,
                workflow_name=workflow_name,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                planning_details=planning_details,
                material=metadata.get('material'),
                input_structure=metadata.get('input_structure'),
                additional_metadata={k: v for k, v in metadata.items() 
                                    if k not in ['material', 'input_structure']}
            )
            db_session.add(workflow_session)
            db_session.commit()
            return workflow_session
    
    async def add_workflow_step(
        self,
        session: Session,
        step_name: str,
        status: str = "completed",
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> WorkflowStep:
        """Add a workflow step to the database.
        
        This is called from after_tool_callback.
        
        Args:
            session: ADK Session object
            step_name: Name of the workflow step (e.g., "exploration_md")
            status: "completed", "failed", or "running"
            input_data: Tool input parameters
            output_data: Tool output/results
            notes: Optional notes
        """
        with self.Session() as db_session:
            # Calculate iteration based on existing steps
            iteration = self._calculate_iteration(db_session, session.id, step_name)
            
            step = WorkflowStep(
                session_id=session.id,
                step_name=step_name,
                status=status,
                created_at=datetime.now(timezone.utc),
                input_data=input_data or {},
                output_data=output_data or {},
                notes=notes or "",
                iteration=iteration
            )
            db_session.add(step)
            
            # Update workflow session timestamp
            workflow_session = db_session.get(WorkflowSession, session.id)
            if workflow_session:
                workflow_session.updated_at = datetime.now(timezone.utc)
            
            db_session.commit()
            return step
    
    def _calculate_iteration(self, db_session, session_id: str, step_name: str) -> int:
        """Calculate which iteration this step belongs to."""
        # Count how many MD exploration steps have been completed
        # Each MD exploration marks the start of a new iteration
        if step_name == "exploration_md":
            count = db_session.query(WorkflowStep).filter(
                and_(
                    WorkflowStep.session_id == session_id,
                    WorkflowStep.step_name == "exploration_md",
                    WorkflowStep.status == "completed"
                )
            ).count()
            return count + 1
        else:
            # Use the current iteration (last MD exploration's iteration)
            last_md = db_session.query(WorkflowStep).filter(
                and_(
                    WorkflowStep.session_id == session_id,
                    WorkflowStep.step_name == "exploration_md"
                )
            ).order_by(desc(WorkflowStep.created_at)).first()
            
            return last_md.iteration if last_md else 1
    
    async def get_workflow_status(self, session_id: str) -> Dict[str, Any]:
        """Get current workflow status and progress.
        
        Returns summary suitable for agent consumption.
        """
        with self.Session() as db_session:
            workflow = db_session.get(WorkflowSession, session_id)
            if not workflow:
                return {"error": "Workflow session not found"}
            
            # Get all steps
            steps = db_session.query(WorkflowStep).filter(
                WorkflowStep.session_id == session_id
            ).order_by(WorkflowStep.created_at).all()
            
            # Analyze workflow state
            completed_iterations = max([s.iteration for s in steps], default=0)
            last_step = steps[-1] if steps else None
            
            # Check if current iteration is complete
            current_iter_steps = [s for s in steps if s.iteration == completed_iterations]
            expected_steps = ["exploration_md", "explore_filter_by_entropy", 
                            "labeling_*", "training"]  # Simplified
            
            return {
                "session_id": session_id,
                "workflow_name": workflow.workflow_name,
                "created_at": workflow.created_at.isoformat(),
                "current_iteration": completed_iterations,
                "total_steps": len(steps),
                "last_step": {
                    "name": last_step.step_name,
                    "status": last_step.status,
                    "timestamp": last_step.created_at.isoformat()
                } if last_step else None,
                "recent_steps": [
                    {
                        "name": s.step_name,
                        "status": s.status,
                        "iteration": s.iteration
                    } for s in steps[-5:]
                ]
            }
    
    async def get_step_history(
        self,
        session_id: str,
        step_name: Optional[str] = None,
        iteration: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Query workflow step history with filters."""
        with self.Session() as db_session:
            query = db_session.query(WorkflowStep).filter(
                WorkflowStep.session_id == session_id
            )
            
            if step_name:
                query = query.filter(WorkflowStep.step_name == step_name)
            if iteration is not None:
                query = query.filter(WorkflowStep.iteration == iteration)
            
            steps = query.order_by(desc(WorkflowStep.created_at)).limit(limit).all()
            
            return [
                {
                    "id": s.id,
                    "step_name": s.step_name,
                    "status": s.status,
                    "iteration": s.iteration,
                    "created_at": s.created_at.isoformat(),
                    "input_data": s.input_data,
                    "output_data": s.output_data,
                    "notes": s.notes
                } for s in steps
            ]
    
    # Implement required BaseMemoryService methods
    async def add_session_to_memory(self, session: Session):
        """Add session events to memory (ADK requirement)."""
        # For workflow memory, we don't store conversational events
        # Only workflow steps via add_workflow_step
        pass
    
    async def search_memory(
        self, *, app_name: str, user_id: str, query: str
    ) -> SearchMemoryResponse:
        """Search workflow memory (basic keyword search).
        
        Could be enhanced with vector embeddings for semantic search.
        """
        with self.Session() as db_session:
            # Find all sessions for this app/user (simplified - ADK sessions have user_id)
            # For now, do simple keyword matching in step names and notes
            query_lower = query.lower()
            
            steps = db_session.query(WorkflowStep).filter(
                or_(
                    WorkflowStep.step_name.contains(query_lower),
                    WorkflowStep.notes.contains(query_lower)
                )
            ).order_by(desc(WorkflowStep.created_at)).limit(20).all()
            
            memories = []
            for step in steps:
                # Create memory entry from workflow step
                from google.adk.events.content import Content, Part
                content = Content(parts=[
                    Part(text=f"Workflow step: {step.step_name} (iteration {step.iteration})\n"
                             f"Status: {step.status}\n"
                             f"Output: {step.output_data}\n"
                             f"Notes: {step.notes}")
                ])
                memories.append(
                    MemoryEntry(
                        content=content,
                        author="system",
                        timestamp=step.created_at.isoformat()
                    )
                )
            
            return SearchMemoryResponse(memories=memories)
