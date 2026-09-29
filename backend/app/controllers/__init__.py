"""Collects every router. Register new controllers here."""

from fastapi import APIRouter

from app.controllers import ai_controller, file_controller, health_controller, item_controller

api_router = APIRouter()
api_router.include_router(health_controller.router)
api_router.include_router(item_controller.router)
api_router.include_router(ai_controller.router)
api_router.include_router(file_controller.router)
