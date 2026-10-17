"""Rezepte & Essensplanung (Hermes-eigen)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.core.database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    # Zutaten als JSON-Array von Strings, z.B. ["500g Mehl", "3 Eier"]
    ingredients_json = Column(Text, default="[]")
    instructions = Column(Text, nullable=True)
    servings = Column(Integer, default=2)
    prep_minutes = Column(Integer, nullable=True)
    tags = Column(String, nullable=True)  # kommagetrennt
    source_url = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MealPlanEntry(Base):
    __tablename__ = "meal_plan"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, index=True, nullable=False)  # ISO YYYY-MM-DD
    meal_type = Column(String, default="dinner")  # breakfast | lunch | dinner
    recipe_id = Column(Integer, nullable=True)
    custom_title = Column(String, nullable=True)  # falls kein Rezept verknüpft

    created_at = Column(DateTime, default=datetime.utcnow)
