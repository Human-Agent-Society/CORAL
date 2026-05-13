from pydantic import BaseModel, Field
from typing import List

class Tuple3Int(BaseModel):
    t: int
    x: int
    y: int

class ConfigFile(BaseModel):
    robot_trajectory: List[Tuple3Int] = Field(description="Trajectory of the robot, represented as a list of tuples (t, x, y).")

# Define your desired output structure
class Response_structure(BaseModel):
    reasoning: str = Field(..., description="Detailed reasoning process to accomplish the task, please solve all the tasks step by step.")
    config: ConfigFile