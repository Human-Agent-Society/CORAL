from pydantic import BaseModel, Field

class ConfigFile(BaseModel):
    vioblk_read: str = Field(description="The Python code snippet of the vioblk_read function.")
    vioblk_write: str = Field(description="The Python code snippet of the vioblk_write function.")

class Response_structure(BaseModel):
    reasoning: str = Field(..., description="Detailed reasoning process to accomplish the task, please solve all the tasks step by step.")
    config: ConfigFile
