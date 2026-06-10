import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.layer import LayerCreate, LayerUpdate, LayerResponse
from app.services import experiment_service

router = APIRouter(prefix="/api/v1/layers", tags=["layers"])


@router.post("", response_model=LayerResponse, status_code=201)
async def create_layer(data: LayerCreate, db: AsyncSession = Depends(get_db)):
    layer = await experiment_service.create_layer(db, name=data.name, description=data.description)
    return layer


@router.get("", response_model=list[LayerResponse])
async def list_layers(db: AsyncSession = Depends(get_db)):
    return await experiment_service.list_layers(db)


@router.get("/{layer_id}", response_model=LayerResponse)
async def get_layer(layer_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    layer = await experiment_service.get_layer(db, layer_id)
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    return layer
