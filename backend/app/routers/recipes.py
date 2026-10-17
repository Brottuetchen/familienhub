"""Rezepte-Verwaltung."""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.recipe import Recipe
from app.models.user import User

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


class RecipeRequest(BaseModel):
    title: str
    description: Optional[str] = None
    ingredients: List[str] = []
    instructions: Optional[str] = None
    servings: int = 2
    prep_minutes: Optional[int] = None
    tags: Optional[str] = None
    source_url: Optional[str] = None


def _to_dict(r: Recipe) -> dict:
    try:
        ingredients = json.loads(r.ingredients_json or "[]")
    except (ValueError, TypeError):
        ingredients = []
    return {
        "id": r.id,
        "title": r.title,
        "description": r.description,
        "ingredients": ingredients,
        "instructions": r.instructions,
        "servings": r.servings,
        "prep_minutes": r.prep_minutes,
        "tags": r.tags,
        "source_url": r.source_url,
    }


@router.get("")
async def list_recipes(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return [_to_dict(r) for r in db.query(Recipe).order_by(Recipe.title.asc()).all()]


@router.get("/{recipe_id}")
async def get_recipe(recipe_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _to_dict(r)


@router.post("")
async def create_recipe(data: RecipeRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    recipe = Recipe(
        title=data.title,
        description=data.description,
        ingredients_json=json.dumps(data.ingredients, ensure_ascii=False),
        instructions=data.instructions,
        servings=data.servings,
        prep_minutes=data.prep_minutes,
        tags=data.tags,
        source_url=data.source_url,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return _to_dict(recipe)


@router.delete("/{recipe_id}")
async def delete_recipe(recipe_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")
    db.delete(r)
    db.commit()
    return {"message": "deleted"}
