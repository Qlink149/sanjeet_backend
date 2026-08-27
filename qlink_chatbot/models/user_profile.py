from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel


class UserProfile(BaseModel):
    """User profile model."""

    name: str
    whatsapp_username: str
    age: int
    location: str
    phone_number: str
    email_id: str
    assistant_name: str
    assistant_language: str
    chat_history: list
    is_registered: bool
    profile_searched: list
    user_state: str
    free_notify_trial_done: int
    free_professional_discovery_done: int
    free_product_discovery_done: int
    service_selected: str
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {ObjectId: str}
