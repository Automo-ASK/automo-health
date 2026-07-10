from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base schema for models read out of the ORM."""

    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str
