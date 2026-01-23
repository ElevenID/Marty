"""
Approval Strategy Adapters for Digital Identity Flows

Concrete implementations of approval strategies for flow execution.
"""

from __future__ import annotations

import logging
from typing import Any

from digital_identity.domain.entities import FlowExecution
from digital_identity.domain.events import FlowExecutionAwaitingApproval

logger = logging.getLogger(__name__)


class ManualApprovalStrategy:
    """
    Manual approval strategy - requires human review.
    
    When invoked, this strategy:
    1. Returns a pending status requiring manual action
    2. Emits a FlowExecutionAwaitingApproval event
    3. Provides context for the approval queue UI
    
    The flow execution will pause until approve() or reject()
    is called on the FlowService.
    """
    
    def __init__(self, event_publisher: Any = None):
        """
        Initialize manual approval strategy.
        
        Args:
            event_publisher: Optional event publisher for notifications
        """
        self._event_publisher = event_publisher
    
    async def evaluate(
        self,
        execution: FlowExecution,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Evaluate approval request - returns pending status for manual review.
        
        Args:
            execution: The flow execution awaiting approval
            context: Additional context data from the execution
            
        Returns:
            Dictionary with:
            - pending: True (requires manual action)
            - requires: "manual_review"
            - context: Relevant context for the reviewer
        """
        logger.info(
            f"Manual approval required for flow execution {execution.id} "
            f"(flow: {execution.flow_id}, step: {execution.current_step})"
        )
        
        # Emit event for notification systems
        if self._event_publisher:
            event = FlowExecutionAwaitingApproval(
                flow_id=execution.flow_id,
                execution_id=execution.id,
                step_name=execution.current_step or "unknown",
            )
            try:
                await self._event_publisher.publish(event)
            except Exception as e:
                logger.warning(f"Failed to publish approval event: {e}")
        
        # Return pending status with context
        return {
            "pending": True,
            "requires": "manual_review",
            "context": {
                "flow_id": execution.flow_id,
                "execution_id": execution.id,
                "current_step": execution.current_step,
                "step_index": execution.current_step_index,
                "step_results": execution.step_results,
                "context_data": context,
            },
        }
