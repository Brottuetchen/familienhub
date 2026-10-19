"""Rezepte-Verwaltung."""

from __future__ import annotations

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_min_role
from app.models.recipe import Recipe
from app.models.user import User, ROLE_PARTNER

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


class RecipeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    ingredients: List[str] = Field(default_factory=list, max_length=100)
    instructions: Optional[str] = Field(default=None, max_length=20000)
    servings: int = Field(default=2, ge=1, le=50)
    prep_minutes: Optional[int] = Field(default=None, ge=0, le=6000)
    tags: Optional[str] = Field(default=None, max_length=200)
    source_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Titel fehlt")
        return v.strip()

    @field_validator("ingredients")
    @classmethod
    def _ingredients(cls, v: List[str]) -> List[str]:
        return [i.strip()[:200] for i in v if i and i.strip()]

    @field_validator("source_url")
    @classmethod
    def _url(cls, v: Optional[str]) -> Optional[str]:
        v = (v or "").strip()
        if not v:
            return None
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("Link muss mit http:// oder https:// beginnen")
        return v


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
async def list_recipes(q: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Recipe)
    if q and q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Recipe.title.ilike(like), Recipe.ingredients_json.ilike(like), Recipe.tags.ilike(like)))
    return [_to_dict(r) for r in query.order_by(Recipe.title.asc()).all()]


@router.get("/{recipe_id}")
async def get_recipe(recipe_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    r = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _to_dict(r)


@router.post("")
async def create_recipe(data: RecipeRequest, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(ROLE_PARTNER))):
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


@router.put("/{recipe_id}")
async def update_recipe(recipe_id: int, data: RecipeRequest, db: Session = Depends(get_db),
                        current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    r = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")
    r.title, r.description, r.instructions = data.title, data.description, data.instructions
    r.ingredients_json = json.dumps(data.ingredients, ensure_ascii=False)
    r.servings, r.prep_minutes, r.tags, r.source_url = data.servings, data.prep_minutes, data.tags, data.source_url
    db.commit()
    db.refresh(r)
    return _to_dict(r)


@router.post("/{recipe_id}/shopping")
async def recipe_to_shopping(recipe_id: int, db: Session = Depends(get_db),
                             current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    """Puts the recipe's ingredients on the family's shopping list (hub, Home Assistant or Mealie)."""
    from app.routers.shopping import add_recipe_ingredients

    r = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")
    items = _to_dict(r)["ingredients"]
    return {"added": await add_recipe_ingredients([(r.title, items)], current_user.id), "ingredients": items}


@router.delete("/{recipe_id}")
async def delete_recipe(recipe_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_min_role(ROLE_PARTNER))):
    r = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recipe not found")
    db.delete(r)
    db.commit()
    return {"message": "deleted"}
