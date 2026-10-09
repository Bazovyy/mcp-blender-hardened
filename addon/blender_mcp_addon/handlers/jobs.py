"""Runtime job lifecycle handlers."""

from ..jobs import cancel_job, get_job, list_jobs
from ..validation import require_param


class JobHandlersMixin:
    def _handle_job_status(self, params: dict) -> dict:
        job_id = require_param(params, "job_id", str)
        job = get_job(job_id)
        if job is None:
            return {"success": False, "code": "job_not_found", "error": f"Unknown job: {job_id}"}
        return {"success": True, **job.to_dict()}

    def _handle_job_cancel(self, params: dict) -> dict:
        job_id = require_param(params, "job_id", str)
        job = get_job(job_id)
        if job is None:
            return {"success": False, "code": "job_not_found", "error": f"Unknown job: {job_id}"}
        cancelled = cancel_job(job_id)
        return {"success": cancelled, **job.to_dict()}

    def _handle_job_list(self, params: dict) -> dict:
        jobs = [job.to_dict() for job in list_jobs()]
        status = params.get("status")
        if status:
            jobs = [job for job in jobs if job["status"] == status]
        return {"success": True, "jobs": jobs, "count": len(jobs)}
