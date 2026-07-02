from typing import Callable, TypeVar, Type, Any, Dict

T = TypeVar("T")

class Container:
    \"\"\"
    A modern, lightweight Dependency Injection container.
    For request-scoped dependencies, use FastAPI's Depends().
    This container is for global singletons (e.g. background daemons, OMS state).
    \"\"\"
    def __init__(self):
        self._providers: Dict[Type, Callable[[], Any]] = {}
        self._singletons: Dict[Type, Any] = {}

    def register_singleton(self, interface: Type[T], instance: T):
        \"\"\"Register a pre-built instance.\"\"\"
        self._singletons[interface] = instance

    def register_factory(self, interface: Type[T], factory: Callable[[], T]):
        \"\"\"Register a factory for transient resolution.\"\"\"
        self._providers[interface] = factory

    def resolve(self, interface: Type[T]) -> T:
        \"\"\"Resolve an dependency.\"\"\"
        if interface in self._singletons:
            return self._singletons[interface]
        if interface in self._providers:
            return self._providers[interface]()
        raise KeyError(f"No provider registered for {interface}")

# Global instance for app lifecycle
container = Container()
