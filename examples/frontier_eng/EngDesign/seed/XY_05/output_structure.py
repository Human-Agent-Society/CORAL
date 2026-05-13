from pydantic import BaseModel, field_validator, Field
from typing import Dict, Union, List, Optional, Any

class ConfigFile(BaseModel):
    ports_table: Dict[str, Dict[str, str]]
    explanation: Dict[str, str]
    state_transitions: Dict[str, Dict[str, Any]]

class Response_structure(BaseModel):
    reasoning: str = Field(..., description="Detailedreasoning process to accomplish the task, please solve all the tasks step by step")
    config: ConfigFile