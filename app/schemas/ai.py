from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class MessageSchema(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True

class ConversationSchema(BaseModel):
    id: int
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    is_pinned: bool
    
    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None
    stream: bool = False
    deep_think: bool = False

class ChatResponse(BaseModel):
    message: str
    conversation_id: int
    role: str = "assistant"
