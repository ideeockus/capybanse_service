from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


def custom_encoder(obj):
    if isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
