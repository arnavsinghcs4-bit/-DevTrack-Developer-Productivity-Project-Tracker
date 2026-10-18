from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.dsa_problems import router as dsa_problems_router
from app.api.v1.goals import router as goals_router
from app.api.v1.tasks import router as tasks_router
from app.api.v1.projects import router as projects_router
from app.api.v1.milestones import router as milestones_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(dsa_problems_router)
api_router.include_router(goals_router)
api_router.include_router(tasks_router)
api_router.include_router(projects_router)
api_router.include_router(milestones_router)
