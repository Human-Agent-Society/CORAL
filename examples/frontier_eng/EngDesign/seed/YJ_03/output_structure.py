from pydantic import BaseModel, Field

class ConfigFile(BaseModel):
    y_hat: list[list[float]] = Field(..., description="Optimized material layout.")
    K_y_hat: float = Field(..., description="Stress-intensity factor of the optimized material layout.")

# Define your desired output structure
class Response_structure(BaseModel):
    reasoning: str = Field(description="Detailed reasoning process to accomplish the task, please solve all the tasks step by step")
    config: ConfigFile
