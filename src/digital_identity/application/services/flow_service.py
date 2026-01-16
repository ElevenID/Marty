"""
Flow Service

Application service for Flow management and execution.
Implements the FlowServicePort interface.

This service handles:
- Flow CRUD operations
- Flow execution orchestration
- Approval management
- Hook management
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import Flow, FlowExecution
from digital_identity.domain.events import (
    FlowCreatedEvent,
    FlowUpdatedEvent,
    FlowDeletedEvent,
    FlowStartedEvent,
    FlowStepCompletedEvent,
    FlowAwaitingApprovalEvent,
    FlowApprovedEvent,
    FlowRejectedEvent,
    FlowCompletedEvent,
    FlowFailedEvent,
    FlowCancelledEvent,
)
from digital_identity.domain.value_objects import (
    FlowType,
    FlowStatus,
    ApprovalStrategy,
    FLOW_STEPS,
)
from digital_identity.application.ports.outbound import (
    FlowRepositoryPort,
    FlowExecutionRepositoryPort,
    EventPublisherPort,
    StepHandlerRegistryPort,
    ApprovalStrategyPort,
)

logger = logging.getLogger(__name__)


class FlowService:
    """
    Service for Flow management and execution.
    
    Orchestrates the full flow lifecycle including:
    - Creating and configuring flows
    - Starting flow executions
    - Managing approvals
    - Executing step handlers with hooks
    """
    
    def __init__(
        self,
        flow_repository: FlowRepositoryPort,
        execution_repository: FlowExecutionRepositoryPort,
        event_publisher: EventPublisherPort | None = None,
        step_registry: StepHandlerRegistryPort | None = None,
        approval_strategies: dict[ApprovalStrategy, ApprovalStrategyPort] | None = None,
    ):
        self._flow_repository = flow_repository
        self._execution_repository = execution_repository
        self._event_publisher = event_publisher
        self._step_registry = step_registry
        self._approval_strategies = approval_strategies or {}
    
    # =========================================================================
    # Flow CRUD
    # =========================================================================
    
    async def create(
        self,
        name: str,
        flow_type: FlowType,
        description: str | None = None,
        trust_profile_id: str | None = None,
        credential_template_id: str | None = None,
        presentation_policy_id: str | None = None,
        deployment_profile_ids: list[str] | None = None,
        approval_strategy: ApprovalStrategy = ApprovalStrategy.AUTO,
        **kwargs: Any,
    ) -> Flow:
        """Create a new Flow."""
        # Check for duplicate name
        existing = await self._flow_repository.get_by_name(name)
        if existing:
            raise ValueError(f"Flow with name '{name}' already exists")
        
        # Create entity
        flow = Flow(
            name=name,
            flow_type=flow_type,
            description=description,
            trust_profile_id=trust_profile_id,
            credential_template_id=credential_template_id,
            presentation_policy_id=presentation_policy_id,
            deployment_profile_ids=deployment_profile_ids or [],
            approval_strategy=approval_strategy,
            **kwargs,
        )
        
        # Save
        saved = await self._flow_repository.save(flow)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                FlowCreatedEvent(
                    flow_id=saved.id,
                    name=saved.name,
                    flow_type=saved.flow_type,
                )
            )
        
        logger.info(f"Created Flow: {saved.id} ({saved.name})")
        return saved
    
    async def get(self, flow_id: str) -> Flow | None:
        """Get a Flow by ID."""
        return await self._flow_repository.get(flow_id)
    
    async def get_by_name(self, name: str) -> Flow | None:
        """Get a Flow by name."""
        return await self._flow_repository.get_by_name(name)
    
    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
        flow_type: FlowType | None = None,
        enabled: bool | None = None,
    ) -> list[Flow]:
        """List Flows with optional filters."""
        return await self._flow_repository.list(
            skip=skip,
            limit=limit,
            flow_type=flow_type,
            enabled=enabled,
        )
    
    async def update(
        self,
        flow_id: str,
        **updates: Any,
    ) -> Flow | None:
        """Update a Flow."""
        flow = await self._flow_repository.get(flow_id)
        if not flow:
            return None
        
        # Track changes for event
        changes = {}
        
        # Apply updates
        for key, value in updates.items():
            if hasattr(flow, key):
                old_value = getattr(flow, key)
                if old_value != value:
                    setattr(flow, key, value)
                    changes[key] = {"old": str(old_value), "new": str(value)}
        
        if changes:
            flow.touch()
            saved = await self._flow_repository.save(flow)
            
            # Publish event
            if self._event_publisher:
                await self._event_publisher.publish(
                    FlowUpdatedEvent(
                        flow_id=saved.id,
                        changes=changes,
                    )
                )
            
            logger.info(f"Updated Flow: {saved.id}")
            return saved
        
        return flow
    
    async def delete(self, flow_id: str) -> bool:
        """Delete a Flow."""
        if not await self._flow_repository.exists(flow_id):
            return False
        
        result = await self._flow_repository.delete(flow_id)
        
        if result and self._event_publisher:
            await self._event_publisher.publish(
                FlowDeletedEvent(flow_id=flow_id)
            )
        
        logger.info(f"Deleted Flow: {flow_id}")
        return result
    
    # =========================================================================
    # Flow Execution
    # =========================================================================
    
    async def start_execution(
        self,
        flow_id: str,
        context_data: dict[str, Any] | None = None,
    ) -> FlowExecution:
        """Start a new flow execution."""
        flow = await self._flow_repository.get(flow_id)
        if not flow:
            raise ValueError(f"Flow {flow_id} not found")
        
        if not flow.enabled:
            raise ValueError(f"Flow {flow_id} is not enabled")
        
        # Get the steps for this flow type
        steps = flow.get_steps()
        if not steps:
            raise ValueError(f"No steps defined for flow type {flow.flow_type}")
        
        # Create execution
        execution = FlowExecution(
            flow_id=flow_id,
            context_data=context_data or {},
            current_step=steps[0].name if steps else None,
        )
        execution.start()
        
        # Save
        saved = await self._execution_repository.save(execution)
        
        # Publish event
        if self._event_publisher:
            await self._event_publisher.publish(
                FlowStartedEvent(
                    execution_id=saved.id,
                    flow_id=flow_id,
                    flow_type=flow.flow_type,
                    context_data=context_data or {},
                )
            )
        
        logger.info(f"Started execution {saved.id} for flow {flow_id}")
        
        # Begin executing steps
        await self._execute_steps(flow, saved)
        
        return saved
    
    async def _execute_steps(self, flow: Flow, execution: FlowExecution) -> None:
        """Execute flow steps sequentially."""
        steps = flow.get_steps()
        
        while execution.current_step_index < len(steps):
            step = steps[execution.current_step_index]
            execution.current_step = step.name
            
            try:
                # Run pre-hooks
                pre_hooks = flow.get_pre_hooks(step.name)
                for hook in pre_hooks:
                    await self._run_hook(hook, execution)
                
                # Check if this is an approval step
                if step.extensible and step.name == "approval_decision":
                    # Handle approval based on strategy
                    approval_result = await self._handle_approval(flow, execution)
                    
                    if approval_result.get("pending"):
                        # Save state and wait for approval
                        execution.await_approval()
                        await self._execution_repository.save(execution)
                        
                        if self._event_publisher:
                            await self._event_publisher.publish(
                                FlowAwaitingApprovalEvent(
                                    execution_id=execution.id,
                                    flow_id=flow.id,
                                    step_name=step.name,
                                    context_data=execution.context_data,
                                )
                            )
                        return  # Exit and wait for approval callback
                    
                    if not approval_result.get("approved"):
                        # Rejected
                        execution.reject(approval_result.get("reason"))
                        await self._execution_repository.save(execution)
                        return
                
                # Execute step handler
                result = await self._execute_step_handler(step.name, execution)
                
                # Run post-hooks
                post_hooks = flow.get_post_hooks(step.name)
                for hook in post_hooks:
                    await self._run_hook(hook, execution)
                
                # Record step completion
                execution.complete_step(step.name, result)
                
                if self._event_publisher:
                    await self._event_publisher.publish(
                        FlowStepCompletedEvent(
                            execution_id=execution.id,
                            flow_id=flow.id,
                            step_name=step.name,
                            step_index=execution.current_step_index - 1,
                            result=result,
                        )
                    )
                
            except Exception as e:
                logger.exception(f"Step {step.name} failed: {e}")
                execution.fail(str(e))
                await self._execution_repository.save(execution)
                
                if self._event_publisher:
                    await self._event_publisher.publish(
                        FlowFailedEvent(
                            execution_id=execution.id,
                            flow_id=flow.id,
                            flow_type=flow.flow_type,
                            error=str(e),
                            step_name=step.name,
                        )
                    )
                return
        
        # All steps completed
        execution.complete()
        await self._execution_repository.save(execution)
        
        if self._event_publisher:
            await self._event_publisher.publish(
                FlowCompletedEvent(
                    execution_id=execution.id,
                    flow_id=flow.id,
                    flow_type=flow.flow_type,
                    result=execution.step_results,
                )
            )
        
        logger.info(f"Completed execution {execution.id}")
    
    async def _execute_step_handler(
        self,
        step_name: str,
        execution: FlowExecution,
    ) -> Any:
        """Execute the handler for a step."""
        if self._step_registry:
            handler = self._step_registry.get_handler(step_name)
            if handler:
                return await handler(execution)
        
        # Default: no-op handler
        logger.debug(f"No handler for step {step_name}, using no-op")
        return {"status": "completed"}
    
    async def _run_hook(
        self,
        hook_config: dict[str, Any],
        execution: FlowExecution,
    ) -> None:
        """Run a hook callback."""
        # Hook execution is extensible - can be webhook, function call, etc.
        logger.debug(f"Running hook: {hook_config}")
    
    async def _handle_approval(
        self,
        flow: Flow,
        execution: FlowExecution,
    ) -> dict[str, Any]:
        """Handle approval based on strategy."""
        strategy = self._approval_strategies.get(flow.approval_strategy)
        
        if strategy:
            return await strategy.evaluate(execution, execution.context_data)
        
        # Default strategies
        if flow.approval_strategy == ApprovalStrategy.AUTO:
            return {"approved": True, "reason": "Auto-approved"}
        elif flow.approval_strategy == ApprovalStrategy.MANUAL:
            return {"pending": True}
        else:
            return {"pending": True}
    
    async def get_execution(self, execution_id: str) -> FlowExecution | None:
        """Get a flow execution by ID."""
        return await self._execution_repository.get(execution_id)
    
    async def list_executions(
        self,
        flow_id: str | None = None,
        status: FlowStatus | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[FlowExecution]:
        """List flow executions with optional filters."""
        return await self._execution_repository.list(
            flow_id=flow_id,
            status=status,
            skip=skip,
            limit=limit,
        )
    
    async def approve_execution(
        self,
        execution_id: str,
        approved_by: str | None = None,
        reason: str | None = None,
    ) -> FlowExecution | None:
        """Approve a pending execution."""
        execution = await self._execution_repository.get(execution_id)
        if not execution:
            return None
        
        if execution.status != FlowStatus.AWAITING_APPROVAL:
            raise ValueError(f"Execution {execution_id} is not awaiting approval")
        
        execution.approve()
        await self._execution_repository.save(execution)
        
        if self._event_publisher:
            await self._event_publisher.publish(
                FlowApprovedEvent(
                    execution_id=execution_id,
                    flow_id=execution.flow_id,
                    approved_by=approved_by,
                    reason=reason,
                )
            )
        
        logger.info(f"Approved execution {execution_id}")
        
        # Resume execution
        flow = await self._flow_repository.get(execution.flow_id)
        if flow:
            # Move past the approval step
            execution.current_step_index += 1
            execution.status = FlowStatus.RUNNING
            await self._execute_steps(flow, execution)
        
        return execution
    
    async def reject_execution(
        self,
        execution_id: str,
        rejected_by: str | None = None,
        reason: str | None = None,
    ) -> FlowExecution | None:
        """Reject a pending execution."""
        execution = await self._execution_repository.get(execution_id)
        if not execution:
            return None
        
        if execution.status != FlowStatus.AWAITING_APPROVAL:
            raise ValueError(f"Execution {execution_id} is not awaiting approval")
        
        execution.reject(reason)
        await self._execution_repository.save(execution)
        
        if self._event_publisher:
            await self._event_publisher.publish(
                FlowRejectedEvent(
                    execution_id=execution_id,
                    flow_id=execution.flow_id,
                    rejected_by=rejected_by,
                    reason=reason,
                )
            )
        
        logger.info(f"Rejected execution {execution_id}")
        return execution
    
    async def cancel_execution(
        self,
        execution_id: str,
        cancelled_by: str | None = None,
        reason: str | None = None,
    ) -> FlowExecution | None:
        """Cancel an execution."""
        execution = await self._execution_repository.get(execution_id)
        if not execution:
            return None
        
        if execution.status in (FlowStatus.COMPLETED, FlowStatus.FAILED, FlowStatus.CANCELLED):
            raise ValueError(f"Execution {execution_id} cannot be cancelled (status: {execution.status})")
        
        execution.cancel()
        await self._execution_repository.save(execution)
        
        if self._event_publisher:
            await self._event_publisher.publish(
                FlowCancelledEvent(
                    execution_id=execution_id,
                    flow_id=execution.flow_id,
                    cancelled_by=cancelled_by,
                    reason=reason,
                )
            )
        
        logger.info(f"Cancelled execution {execution_id}")
        return execution
    
    # =========================================================================
    # Hook Management
    # =========================================================================
    
    async def add_hook(
        self,
        flow_id: str,
        step_name: str,
        hook_type: str,
        hook_config: dict[str, Any],
    ) -> Flow | None:
        """Add a hook to a flow step."""
        flow = await self._flow_repository.get(flow_id)
        if not flow:
            return None
        
        if hook_type == "pre":
            flow.add_pre_hook(step_name, hook_config)
        elif hook_type == "post":
            flow.add_post_hook(step_name, hook_config)
        else:
            raise ValueError(f"Invalid hook type: {hook_type}")
        
        saved = await self._flow_repository.save(flow)
        logger.info(f"Added {hook_type} hook for step {step_name} on flow {flow_id}")
        return saved
    
    async def remove_hook(
        self,
        flow_id: str,
        step_name: str,
        hook_type: str,
        hook_index: int,
    ) -> Flow | None:
        """Remove a hook from a flow step."""
        flow = await self._flow_repository.get(flow_id)
        if not flow:
            return None
        
        key = f"{hook_type}_{step_name}"
        if key in flow.hooks and 0 <= hook_index < len(flow.hooks[key]):
            flow.hooks[key].pop(hook_index)
            flow.touch()
            saved = await self._flow_repository.save(flow)
            logger.info(f"Removed {hook_type} hook at index {hook_index} for step {step_name}")
            return saved
        
        return flow
