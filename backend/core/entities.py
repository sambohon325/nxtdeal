from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class Entity:
    id: str
    entity_type: str
    attributes: Dict[str, Any]