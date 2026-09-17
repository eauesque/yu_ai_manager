"""Compatibility facade for background job manager."""

from .jobs_manager import JobManager
from .jobs_model import Job

job_manager = JobManager()

__all__ = [
    "Job",
    "JobManager",
    "job_manager",
]
