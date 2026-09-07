"""Plugin infrastructure for MAIE.

The plugin model is intentionally lightweight and allows new collectors,
categories, analyzers, notifications, and future AI modules to register
without changing existing source files.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from abc import ABC
from typing import Any, Iterable


logger = logging.getLogger(__name__)


class PluginRegistry:
    """Registry for discoverable plugins across MAIE."""

    def __init__(self) -> None:
        self._plugins: dict[str, "BasePlugin"] = {}
        self._plugins_by_type: dict[str, list["BasePlugin"]] = {}

    def clear(self) -> None:
        self._plugins.clear()
        self._plugins_by_type.clear()

    def register(self, plugin: "BasePlugin | type[BasePlugin]") -> "BasePlugin | None":
        if plugin is None:
            return None

        if isinstance(plugin, type):
            if not issubclass(plugin, BasePlugin):
                return None
            if inspect.isabstract(plugin):
                return None
            plugin = plugin()

        plugin_name = getattr(plugin, "name", None) or plugin.__class__.__name__
        if not plugin_name:
            return None

        key = plugin_name.lower()
        self._plugins[key] = plugin

        plugin_type = getattr(plugin, "plugin_type", "generic") or "generic"
        plugins_for_type = self._plugins_by_type.setdefault(plugin_type, [])
        if plugin not in plugins_for_type:
            plugins_for_type.append(plugin)

        return plugin

    def get(self, name: str) -> "BasePlugin | None":
        if not name:
            return None
        return self._plugins.get(name.lower())

    def all(self) -> list["BasePlugin"]:
        return list(self._plugins.values())

    def get_collectors(self) -> list["BasePlugin"]:
        return self._get_by_type("collector")

    def get_categories(self) -> list["BasePlugin"]:
        return self._get_by_type("category")

    def get_analyzers(self) -> list["BasePlugin"]:
        return self._get_by_type("analyzer")

    def get_notifications(self) -> list["BasePlugin"]:
        return self._get_by_type("notification")

    def get_future_ai(self) -> list["BasePlugin"]:
        return self._get_by_type("future-ai")

    def _get_by_type(self, plugin_type: str) -> list["BasePlugin"]:
        return list(self._plugins_by_type.get(plugin_type, []))


class BasePlugin(ABC):
    """Base class for all MAIE plugins."""

    name: str = ""
    version: str = "0.1.0"
    author: str = ""
    description: str = ""
    dependencies: list[str] = []
    capabilities: list[str] = []
    plugin_type: str = "generic"

    def __new__(cls, *args: Any, **kwargs: Any) -> "BasePlugin":
        instance = super().__new__(cls)
        registry = kwargs.get("registry")
        instance._plugin_registry = registry or _get_default_registry()
        return instance

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        registry = kwargs.get("registry")
        if registry is not None:
            self._plugin_registry = registry
        self._plugin_registry.register(self)

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "dependencies": list(self.dependencies or []),
            "capabilities": list(self.capabilities or []),
            "plugin_type": self.plugin_type,
        }

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the plugin's main work."""
        return None


class CollectorPlugin(BasePlugin):
    """Plugin type for data collectors."""

    plugin_type = "collector"


class CategoryPlugin(BasePlugin):
    """Plugin type for classification and categorization."""

    plugin_type = "category"


class AnalyzerPlugin(BasePlugin):
    """Plugin type for scoring and enrichment analysis."""

    plugin_type = "analyzer"


class NotificationPlugin(BasePlugin):
    """Plugin type for outbound notification providers."""

    plugin_type = "notification"


class FutureAIPlugin(BasePlugin):
    """Plugin type for future AI modules."""

    plugin_type = "future-ai"


AIPlugin = FutureAIPlugin


class PluginLoader:
    """Discover plugin modules from Python packages."""

    def __init__(self, registry: PluginRegistry | None = None) -> None:
        self.registry = registry or _get_default_registry()
        self.discovery_errors: list[dict[str, str]] = []

    def discover(self, packages: Iterable[str] | None = None) -> list[BasePlugin]:
        discovered: list[BasePlugin] = []
        self.discovery_errors.clear()
        package_names = list(
            packages or ["collectors", "analysis", "categories", "alerts", "plugins"]
        )
        for package_name in package_names:
            discovered.extend(self._load_package(package_name))
        return discovered

    def _load_package(self, package_name: str) -> list[BasePlugin]:
        try:
            package = importlib.import_module(package_name)
        except Exception as exc:
            self._record_error(package_name, "import", exc)
            return []

        if not hasattr(package, "__path__"):
            return []

        previous_plugins = list(self.registry.all())
        for _, module_name, _ in pkgutil.iter_modules(
            package.__path__, package.__name__ + "."
        ):
            if module_name.endswith(".base") or module_name.endswith(".__init__"):
                continue
            try:
                importlib.import_module(module_name)
            except Exception as exc:
                self._record_error(module_name, "import", exc)
                continue
            try:
                self._discover_classes_from_module(module_name)
            except Exception as exc:
                self._record_error(module_name, "registration", exc)
                continue

        new_plugins = [
            plugin for plugin in self.registry.all() if plugin not in previous_plugins
        ]
        return new_plugins

    def load_module(self, module_name: str) -> list[BasePlugin]:
        try:
            return self._discover_classes_from_module(module_name)
        except Exception as exc:
            self._record_error(module_name, "registration", exc)
            return []

    def _record_error(self, module_name: str, stage: str, error: Exception) -> None:
        details = {"module": module_name, "stage": stage, "error": str(error)}
        self.discovery_errors.append(details)
        logger.warning(
            "Plugin discovery failed",
            extra={"plugin_discovery": details},
        )

    def _discover_classes_from_module(self, module_name: str) -> list[BasePlugin]:
        module = importlib.import_module(module_name)
        discovered: list[BasePlugin] = []
        for value in vars(module).values():
            if not inspect.isclass(value) or value is BasePlugin:
                continue
            if not issubclass(value, BasePlugin) or inspect.isabstract(value):
                continue
            if value in {
                CollectorPlugin,
                CategoryPlugin,
                AnalyzerPlugin,
                NotificationPlugin,
                FutureAIPlugin,
            }:
                continue
            if getattr(value, "__module__", None) != module_name:
                continue
            instance = self.registry.register(value)
            if instance is not None:
                discovered.append(instance)
        return discovered


_DEFAULT_REGISTRY = PluginRegistry()


def _get_default_registry() -> PluginRegistry:
    return _DEFAULT_REGISTRY


def get_default_registry() -> PluginRegistry:
    return _get_default_registry()


__all__ = [
    "AIPlugin",
    "AnalyzerPlugin",
    "BasePlugin",
    "CategoryPlugin",
    "CollectorPlugin",
    "FutureAIPlugin",
    "NotificationPlugin",
    "PluginLoader",
    "PluginRegistry",
    "get_default_registry",
]
