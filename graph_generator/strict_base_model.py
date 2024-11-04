from pydantic import BaseModel


# Custom base model with Config that forbids extra fields
class StrictBaseModel(BaseModel):
    class Config:
        extra = "forbid"
