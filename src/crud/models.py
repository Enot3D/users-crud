from datetime import date

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column

from crud.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    created_at: Mapped[date] = mapped_column(
        Date,
        default=date.today,
    )

    password_hash: Mapped[str | None] = mapped_column(
    String(255),
    nullable=True,
)