"""Business API router; domain operations are added in later phases."""

from fastapi import APIRouter

from ..constants import API_PREFIX

# Reserve the documented service-specific prefix without adding fake operations.
api_router = APIRouter(prefix=API_PREFIX)
