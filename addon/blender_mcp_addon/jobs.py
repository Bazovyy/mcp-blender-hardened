"""Bounded, cancellable job runtime for work spanning Blender timer ticks."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic, perf_counter
from typing import Any, Callable
from uuid import uuid4

TERMINAL_STATES = {"completed", "failed", "cancelled", "timeout"}


@dataclass(slots=True)
class JobStep:
    done: bool = False
    result: Any = None
    progress: float | None = None
    error: str | None = None
    delay_seconds: float = 0.0


@dataclass(slots=True)
class RuntimeJob:
    id: str
    kind: str
    stepper: Callable[["RuntimeJob"], JobStep]
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    progress: float = 0.0
    result: Any = None
    error: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    next_run_at: float = 0.0
    deadline: float | None = None

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id, "kind": self.kind, "status": self.status,
            "progress": self.progress, "result": self.result, "error": self.error,
            "metadata": dict(self.metadata), "terminal": self.terminal,
        }


class JobRuntime:
    def __init__(self, clock: Callable[[], float] = monotonic):
        self.clock = clock
        self._jobs: dict[str, RuntimeJob] = {}

    def submit_job(self, kind: str, stepper: Callable[[RuntimeJob], JobStep],
                   metadata: dict[str, Any] | None = None, timeout_seconds: float | None = None) -> str:
        now = self.clock()
        job = RuntimeJob(
            id=str(uuid4()), kind=kind, stepper=stepper, metadata=dict(metadata or {}),
            created_at=now, updated_at=now, next_run_at=now,
            deadline=(now + float(timeout_seconds)) if timeout_seconds is not None else None,
        )
        self._jobs[job.id] = job
        return job.id

    def get_job(self, job_id: str) -> RuntimeJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[RuntimeJob]:
        return list(self._jobs.values())

    def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.terminal:
            return False
        now = self.clock()
        job.status = "cancelled"
        job.updated_at = now
        job.error = "Cancelled by request"
        return True

    def tick(self, max_jobs: int = 4, time_budget_ms: float = 4.0) -> int:
        if max_jobs <= 0 or time_budget_ms <= 0:
            return 0
        budget_started = perf_counter()
        processed = 0
        for job in list(self._jobs.values()):
            if processed >= max_jobs:
                break
            if processed and (perf_counter() - budget_started) * 1000.0 >= time_budget_ms:
                break
            if job.terminal:
                continue
            now = self.clock()
            if job.deadline is not None and now >= job.deadline:
                job.status = "timeout"
                job.error = "Job deadline exceeded"
                job.updated_at = now
                processed += 1
                continue
            if now < job.next_run_at:
                continue
            job.status = "running"
            try:
                step = job.stepper(job)
                if not isinstance(step, JobStep):
                    raise TypeError(f"Job stepper must return JobStep, got {type(step).__name__}")
                if step.progress is not None:
                    job.progress = max(0.0, min(1.0, float(step.progress)))
                if step.result is not None:
                    job.result = step.result
                if step.error is not None:
                    job.error = step.error
                if step.done:
                    job.status = "failed" if step.error else "completed"
                    if not step.error:
                        job.progress = 1.0
                else:
                    job.next_run_at = now + max(0.0, float(step.delay_seconds))
                job.updated_at = now
            except Exception as exc:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                job.updated_at = now
            processed += 1
        return processed


_runtime = JobRuntime()

def submit_job(kind, stepper, metadata=None, timeout_seconds=None):
    return _runtime.submit_job(kind, stepper, metadata, timeout_seconds)

def get_job(job_id):
    return _runtime.get_job(job_id)

def list_jobs():
    return _runtime.list_jobs()

def cancel_job(job_id):
    return _runtime.cancel_job(job_id)

def tick_jobs(max_jobs=4, time_budget_ms=4.0):
    return _runtime.tick(max_jobs=max_jobs, time_budget_ms=time_budget_ms)
