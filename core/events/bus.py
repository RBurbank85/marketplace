import asyncio
import inspect
import logging
from collections import defaultdict
from typing import Any, Callable, Type, Union

from core.events.base import Event

logger = logging.getLogger(__name__)

Handler = Union[Callable[[Any], None], Callable[[Any], asyncio.Future]]

class EventBus:
    """
    Lightweight in-process Event Bus.
    Supports synchronous and asynchronous handlers.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._instance._handlers = defaultdict(list)
        return cls._instance

    def subscribe(self, event_type: Type[Event], handler: Handler, priority: int = 0):
        """
        Subscribe a handler to an event type.
        Handlers are executed in order of priority (higher first).
        """
        self._handlers[event_type].append((priority, handler))
        self._handlers[event_type].sort(key=lambda x: x[0], reverse=True)
        logger.debug(f"Subscribed {handler.__name__} to {event_type.__name__} with priority {priority}")

    def unsubscribe(self, event_type: Type[Event], handler: Handler):
        """Unsubscribe a handler from an event type."""
        self._handlers[event_type] = [
            (p, h) for p, h in self._handlers[event_type] if h != handler
        ]

    async def publish(self, event: Event):
        """
        Publish an event to all subscribers.
        Automatically handles sync and async handlers.
        """
        event_type = type(event)
        logger.info(f"Publishing event: {event_type.__name__} ({event.event_id})")
        
        # Get handlers for this specific event type and its base classes (if any)
        handlers_to_run = []
        for registered_type, handlers in self._handlers.items():
            if isinstance(event, registered_type):
                handlers_to_run.extend(handlers)
        
        # Sort by priority again in case we merged multiple lists
        handlers_to_run.sort(key=lambda x: x[0], reverse=True)

        for _, handler in handlers_to_run:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.exception(f"Error in handler {handler.__name__} for event {event_type.__name__}: {e}")

# Global bus instance
bus = EventBus()
