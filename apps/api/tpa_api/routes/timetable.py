from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..services.timetable import MilestoneCreate, MilestonePatch
from ..services.timetable import TimetableCreate, TimetablePatch, TimetableReviewCreate
from ..services.timetable import create_milestone as service_create_milestone
from ..services.timetable import create_timetable as service_create_timetable
from ..services.timetable import create_timetable_review as service_create_timetable_review
from ..services.timetable import list_milestones as service_list_milestones
from ..services.timetable import list_timetable_reviews as service_list_timetable_reviews
from ..services.timetable import list_timetables as service_list_timetables
from ..services.timetable import patch_milestone as service_patch_milestone
from ..services.timetable import patch_timetable as service_patch_timetable
from ..services.timetable import publish_timetable as service_publish_timetable


router = APIRouter(tags=["timetables"])


@router.post("/timetables")
def create_timetable(body: TimetableCreate) -> JSONResponse:
    return service_create_timetable(body)


@router.get("/plan-projects/{plan_project_id}/timetables")
def list_timetables(plan_project_id: str) -> JSONResponse:
    return service_list_timetables(plan_project_id)


@router.patch("/timetables/{timetable_id}")
def patch_timetable(timetable_id: str, body: TimetablePatch) -> JSONResponse:
    return service_patch_timetable(timetable_id, body)


@router.post("/timetables/{timetable_id}/publish")
def publish_timetable(timetable_id: str) -> JSONResponse:
    return service_publish_timetable(timetable_id)


@router.post("/milestones")
def create_milestone(body: MilestoneCreate) -> JSONResponse:
    return service_create_milestone(body)


@router.patch("/milestones/{milestone_id}")
def patch_milestone(milestone_id: str, body: MilestonePatch) -> JSONResponse:
    return service_patch_milestone(milestone_id, body)


@router.get("/timetables/{timetable_id}/milestones")
def list_milestones(timetable_id: str) -> JSONResponse:
    return service_list_milestones(timetable_id)


@router.post("/timetables/{timetable_id}/reviews")
def create_timetable_review(timetable_id: str, body: TimetableReviewCreate) -> JSONResponse:
    payload = body.model_dump()
    payload["timetable_id"] = timetable_id
    return service_create_timetable_review(TimetableReviewCreate(**payload))


@router.get("/timetables/{timetable_id}/reviews")
def list_timetable_reviews(timetable_id: str) -> JSONResponse:
    return service_list_timetable_reviews(timetable_id)
