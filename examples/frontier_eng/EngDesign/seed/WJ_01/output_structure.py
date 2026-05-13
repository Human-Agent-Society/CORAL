from pydantic import BaseModel, Field


class ConfigFile(BaseModel):
    denoising_strategy: str = Field(
        description=(
            "Analysis of the noise type(s), it or their characteristics, and denoising strategy. "
        )
    )

    filter_sequence: list[str] = Field(
        description=(
            "A list of filter descriptions in the format 'filter_name(param1=value1, param2=value2)'. "
            "Example: ['median(ksize=3)', 'gaussian(ksize=5, sigma=1.2)']"
        )
    )

    function_code: str = Field(
        description="A complete Python function that implements the filtering steps, starting with def ..., and outputs filtered_img"
    )

class Response_structure(BaseModel):
    reasoning: str = Field(..., description="Detailedreasoning process to accomplish the task, please solve all the tasks step by step")
    config: ConfigFile
