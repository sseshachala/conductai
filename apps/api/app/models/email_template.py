from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, JSON, DateTime
from app.core.database import Base


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    slug = Column(String(100), primary_key=True)
    subject = Column(Text, nullable=False)
    html_body = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    variables = Column(JSON, nullable=True)  # list of variable names
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
