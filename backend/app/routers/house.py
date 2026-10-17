"""Eng begrenzte Hausaktionen; kein allgemeiner Home-Assistant-Proxy."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.connectors.base import ConnectorError
from app.connectors.homeassistant_connector import HomeAssistantConnector
from app.core.security import get_current_user, require_min_role
from app.models.user import ROLE_PARTNER, User

router = APIRouter(prefix="/api/house", tags=["house"])


class HouseAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    entity_id: str = Field(pattern=r"^(light|switch|script|scene)\.[a-z0-9_]+$")
    action: Literal["turn_on", "turn_off", "brightness", "activate"]
    brightness: int | None = Field(default=None, ge=0, le=255)

    @model_validator(mode="after")
    def validate_brightness(self):
        if self.action == "brightness":
            if self.brightness is None:
                raise ValueError("Helligkeit erforderlich")
        elif "brightness" in self.model_fields_set:
            raise ValueError("Helligkeit nur für Dimmeraktion erlaubt")
        return self


@router.get("/controls")
async def house_controls(response: Response, user: User = Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return await HomeAssistantConnector().get_house_controls(user.is_admin or user.role in {"admin", "partner"})


@router.post("/actions")
async def house_action(data: HouseAction, request: Request, user: User = Depends(require_min_role(ROLE_PARTNER))):
    if request.query_params:
        raise HTTPException(422, "Keine zusätzlichen Parameter erlaubt")
    try:
        control = await HomeAssistantConnector().house_action(data.entity_id, data.action, data.brightness)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except ConnectorError as exc:
        raise HTTPException(409, str(exc)) from exc
    # control: bestätigter neuer Zustand, falls HA ihn sofort meldet; sonst liest die App nach.
    return {"accepted": True, "control": control}
