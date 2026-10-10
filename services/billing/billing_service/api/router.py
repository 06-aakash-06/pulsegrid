"""Versioned business API router for Billing."""

from fastapi import APIRouter

from ..constants import API_PREFIX
from .billing import router as billing_router

# Reserve the documented service-specific prefix without adding fake operations.
api_router = APIRouter(prefix=API_PREFIX)
api_router.include_router(billing_router)
