from fastapi import APIRouter, HTTPException

from app.sync_service import get_last_snapshot, run_sync

router = APIRouter(prefix="/api/comparison", tags=["comparison"])


@router.get("")
async def get_comparison():
    snapshot = get_last_snapshot()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Noch kein Sync durchgeführt. POST /api/comparison/sync aufrufen.")
    return snapshot.model_dump(mode="json")


@router.post("/sync")
async def trigger_sync():
    snapshot = await run_sync()
    return snapshot.model_dump(mode="json")
