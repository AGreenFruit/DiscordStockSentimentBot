from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Dict, Any, Callable, List
from datetime import datetime, timezone
from logging import getLogger
import asyncio

logger = getLogger(__name__)


class Job(ABC):
    def __init__(self, job_id: str):
        self._job_id = job_id
        self._status = "PENDING"
        self._resources: Dict[str, Any] = {}
        self._cleanup_tasks: List[Callable] = []
        self._result: Dict[str, Any] = {}

    def __str__(self) -> str:
        return f"{self._job_id}"

    def __repr__(self) -> str:
        return self.__str__()

    async def setup_resources(self) -> None:
        '''
        Setup any resources needed for the job
        '''

    async def cleanup_resources(self) -> None:
        '''
        Cleanup any resources used by the job
        '''
        for cleanup_task in reversed(self._cleanup_tasks):
            try:
                if asyncio.iscoroutinefunction(cleanup_task):
                    await cleanup_task()
                else:
                    cleanup_task()
            except Exception as e:
                logger.error(f"Error running cleanup task in {self}: {e}")

    def register_cleanup(self, cleanup_func: callable) -> None:
        '''
        Register a cleanup function to be run when the job is completed
        '''
        self._cleanup_tasks.append(cleanup_func)

    async def pre_run_hook(self) -> None:
        '''
        Run any pre-run hooks before execution
        '''

    async def post_run_hook(self) -> None:
        '''
        Run any post-run hooks after execution
        '''

    @abstractmethod
    async def run_implementation(self) -> Dict[str, Any]:
        '''
        Run the job implementation
        '''
        raise NotImplementedError(
            f"run_implementation must be implemented by "
            f"{self.__class__.__name__}"
        )

    @asynccontextmanager
    async def _resource_context(self):
        '''Context manager for resource lifecycle management'''
        try:
            await self.setup_resources()
            yield
        finally:
            await self.cleanup_resources()

    async def execute(self) -> Dict[str, Any]:
        '''
        Execute the job
        '''
        start_time = datetime.now(timezone.utc)
        logger.info(f"Executing job {self}")
        error_message = None

        try:
            async with self._resource_context():
                # Pre-execution hook
                await self.pre_run_hook()

                # Run job implementation
                self._status = "RUNNING"
                self._result = await self.run_implementation()

                # Update job status
                self._status = "COMPLETED"
                end_time = datetime.now(timezone.utc)

                # Post-run hook
                await self.post_run_hook()

                runTime = end_time - start_time
                logger.info(
                    f"Job {self} completed successfully in {runTime}"
                )
        except Exception as e:
            self._status = "FAILED"
            error_message = str(e)
            logger.error(f"Error executing job {self}: {e}")

            try:
                await self.post_run_hook()
            except Exception as post_run_hook_error:
                logger.error(
                    f"Error running post-run hook: {post_run_hook_error}"
                )
        finally:
            end_time = datetime.now(timezone.utc)

        return {
            "job_id": self._job_id,
            "status": self._status,
            "duration": (end_time - start_time).total_seconds(),
            "result": self._result,
            "error": error_message
        }


__all__ = [
    "Job"
]
