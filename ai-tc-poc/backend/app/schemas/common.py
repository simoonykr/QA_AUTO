from pydantic import BaseModel, Field


class ApiErrorBody(BaseModel):
    code: str
    message: str
    requestId: str
    retryable: bool = False
    details: dict = Field(default_factory=dict)
