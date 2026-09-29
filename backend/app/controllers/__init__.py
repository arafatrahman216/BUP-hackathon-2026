"""Collects every router. Register new controllers here."""

from fastapi import APIRouter

from app.controllers import (ai_controller, health_controller, pipeline_controller, recommendation_controller,
                             status_controller)

api_router = APIRouter()
api_router.include_router(health_controller.router)
api_router.include_router(ai_controller.router)
api_router.include_router(pipeline_controller.router)
api_router.include_router(recommendation_controller.router)
api_router.include_router(status_controller.router)
