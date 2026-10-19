"""Taskiq jobs that send email.

The worker imports this module (see ``taskiq/worker.py``) as ``infrastructure.email.tasks``
while the API imports it as ``src.infrastructure.email.tasks``. taskiq derives a task's
default name from its module path, so every task here sets an explicit ``task_name``
that both sides agree on.

Queue a job from app code with ``await send_welcome_email_task.kiq(name=..., email=...)``.
"""

from ..taskiq.brokers import default_broker
from .service import send_welcome_email


@default_broker.task(task_name="send_welcome_email")
async def send_welcome_email_task(name: str, email: str) -> None:
    """Worker job: send the welcome email."""
    await send_welcome_email(name=name, email=email)
