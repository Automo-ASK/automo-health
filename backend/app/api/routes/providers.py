import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.services import _infer_type
from app.core.database import get_db
from app.models.provider import Provider as ProviderModel
from app.models.service import Service as ServiceModel

router = APIRouter(prefix="/providers", tags=["providers"])


class ProviderRead(BaseModel):
    id: uuid.UUID
    slug: str | None
    full_name: str
    specialty: str | None
    role: str  # "doctor" | "lab" — inferred from the services they offer


@router.get("", response_model=list[ProviderRead], summary="List providers (staff dashboards)")
def list_providers(db: Session = Depends(get_db)) -> list[ProviderRead]:
    """Real providers, for the dashboards to populate their doctor/lab pickers
    dynamically instead of hardcoding identities. A provider is "lab" if every
    active service they offer is a lab test; otherwise "doctor"."""
    providers = db.execute(select(ProviderModel)).scalars().all()
    services = db.execute(
        select(ServiceModel).where(ServiceModel.is_active.is_(True))
    ).scalars().all()

    types_by_provider: dict[uuid.UUID, list[str]] = {}
    for s in services:
        types_by_provider.setdefault(s.provider_id, []).append(_infer_type(s.name))

    out: list[ProviderRead] = []
    for p in providers:
        types = types_by_provider.get(p.id, [])
        role = "lab" if types and all(t == "lab_test" for t in types) else "doctor"
        out.append(
            ProviderRead(
                id=p.id, slug=p.slug, full_name=p.full_name, specialty=p.specialty, role=role
            )
        )
    return out
