import json
from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """Abstract base class for Fenrir tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    @abstractmethod
    def input_schema(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        pass

    def validate_input(self, kwargs: Dict[str, Any]) -> bool:
        required_fields = self.input_schema.get("required", [])
        for field in required_fields:
            if field not in kwargs:
                raise ValueError(f"Missing required parameter: {field}")
        return True

    def run(self, kwargs: Dict[str, Any]) -> str:
        try:
            self.validate_input(kwargs)
            result = self.execute(**kwargs)
            if not isinstance(result, str):
                return json.dumps(result, indent=2)
            return result
        except Exception as e:
            return f"Error executing tool '{self.name}': {str(e)}"
