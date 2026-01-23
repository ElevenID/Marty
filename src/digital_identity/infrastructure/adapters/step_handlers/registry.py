"""
Step Handler Registry

Concrete implementation of the StepHandlerRegistryPort.
Manages the registration and retrieval of step handlers for flow execution.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class StepHandlerRegistry:
    """
    Step Handler Registry implementation.
    
    Implements StepHandlerRegistryPort protocol from application/ports/outbound.py.
    Provides a simple dictionary-based registry for flow step handlers.
    """
    
    def __init__(self):
        self._handlers: dict[str, Callable] = {}
    
    def register_handler(self, step_name: str, handler: Any) -> None:
        """
        Register a handler for a specific step name.
        
        Args:
            step_name: Name of the step (e.g., "issue_credential", "deliver_credential")
            handler: Async callable that takes (FlowExecution) -> Any
        """
        if step_name in self._handlers:
            logger.warning(f"Overwriting existing handler for step: {step_name}")
        
        self._handlers[step_name] = handler
        logger.info(f"Registered handler for step: {step_name}")
    
    def get_handler(self, step_name: str) -> Any | None:
        """
        Get the handler for a specific step name.
        
        Args:
            step_name: Name of the step
        
        Returns:
            Handler callable if found, None otherwise
        """
        handler = self._handlers.get(step_name)
        if not handler:
            logger.debug(f"No handler found for step: {step_name}")
        return handler
    
    def unregister_handler(self, step_name: str) -> bool:
        """
        Unregister a handler.
        
        Args:
            step_name: Name of the step
        
        Returns:
            True if handler was removed, False if not found
        """
        if step_name in self._handlers:
            del self._handlers[step_name]
            logger.info(f"Unregistered handler for step: {step_name}")
            return True
        return False
    
    def list_registered_steps(self) -> list[str]:
        """Get list of all registered step names."""
        return list(self._handlers.keys())
    
    def clear(self) -> None:
        """Clear all registered handlers."""
        self._handlers.clear()
        logger.info("Cleared all step handlers")
