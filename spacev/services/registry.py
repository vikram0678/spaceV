"""
SpaceV Services Subsystem: Pluggable Service & Adapter Registry.
Engineered from Langflow / LFX architecture for modular, swappable runtime components.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, Optional, Type, TypeVar

T = TypeVar("T")


class ServiceType(str, Enum):
    LLM = "llm"
    TTS = "tts"
    STT = "stt"
    VLM = "vlm"
    VECTOR = "vector"


class AdapterRegistry:
    """
    Thread-safe registry for swappable implementation adapters sharing the same protocol.
    """

    _registry: Dict[ServiceType, Dict[str, Type[Any]]] = {st: {} for st in ServiceType}
    _instances: Dict[ServiceType, Dict[str, Any]] = {st: {} for st in ServiceType}

    @classmethod
    def register(cls, service_type: ServiceType, key: str, adapter_cls: Type[T]) -> Type[T]:
        cls._registry[service_type][key.lower()] = adapter_cls
        return adapter_cls

    @classmethod
    def get_adapter_class(cls, service_type: ServiceType, key: str) -> Optional[Type[Any]]:
        return cls._registry[service_type].get(key.lower())

    @classmethod
    def get_instance(cls, service_type: ServiceType, key: str, **kwargs: Any) -> Optional[Any]:
        clean_key = key.lower()
        if clean_key not in cls._instances[service_type]:
            adapter_cls = cls.get_adapter_class(service_type, clean_key)
            if not adapter_cls:
                return None
            cls._instances[service_type][clean_key] = adapter_cls(**kwargs)
        return cls._instances[service_type][clean_key]

    @classmethod
    def list_adapters(cls, service_type: ServiceType) -> list[str]:
        return list(cls._registry[service_type].keys())

    @classmethod
    def clear(cls) -> None:
        for st in ServiceType:
            cls._registry[st].clear()
            cls._instances[st].clear()


def register_adapter(service_type: ServiceType, key: str):
    """Decorator to register a swappable adapter implementation."""

    def decorator(cls: Type[T]) -> Type[T]:
        AdapterRegistry.register(service_type, key, cls)
        return cls

    return decorator
