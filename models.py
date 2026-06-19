import json
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


class Base(DeclarativeBase):
    pass


class LeaseAnalysis(Base):
    __tablename__ = "lease_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_text = Column(Text, nullable=False)
    extracted_json = Column(Text, nullable=True)
    confirmed_json = Column(Text, nullable=True)
    z3_result_json = Column(Text, nullable=True)
    plain_english_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def get_extracted(self) -> dict | None:
        return json.loads(self.extracted_json) if self.extracted_json else None

    def get_confirmed(self) -> dict | None:
        return json.loads(self.confirmed_json) if self.confirmed_json else None

    def get_z3_result(self) -> dict | None:
        return json.loads(self.z3_result_json) if self.z3_result_json else None

    def get_plain_english(self) -> dict | None:
        return json.loads(self.plain_english_json) if self.plain_english_json else None


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    with Session(engine) as session:
        yield session
