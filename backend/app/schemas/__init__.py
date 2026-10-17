"""Technische Verträge der gemeinsamen HTTP-Grenze."""
from typing import Annotated
from pydantic import StringConstraints

# Identitäten vor dem Lookup prüfen, nicht durch UUID-Normalisierung reparieren.
CanonicalUUID = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
