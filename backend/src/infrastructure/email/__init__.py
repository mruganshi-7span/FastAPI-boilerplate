"""Transactional email: Jinja templates rendered and sent over SMTP by the taskiq worker.

Flow::

    UserService.create() -> send_welcome_email_task.kiq(...)  # Redis (taskiq)
             -> taskiq worker -> send_welcome_email() -> render templates
             -> send_email() -> aiosmtplib -> SMTP server

The worker must be running for queued emails to go out (``docker compose up`` starts it;
without Docker run ``taskiq worker infrastructure.taskiq.worker:default_broker`` from
``backend/src``). SMTP is configured with the ``SMTP_*`` and ``MAIL_FROM_*`` settings.

How to add a new email:
    1. Add ``templates/emails/<name>.html`` and ``templates/emails/<name>.txt``.
    2. Add ``send_<name>_email(...)`` in ``service.py``: build the template context and
       subject, render both templates, and call ``send_email(...)``.
    3. Add a task in ``tasks.py`` with ``@default_broker.task(task_name="send_<name>_email")``
       that calls it (always set ``task_name`` explicitly).
    4. Call ``await send_<name>_email_task.kiq(...)`` from your service (wrap it in
       try/except and log, like ``UserService.create``, if a failure shouldn't fail the request).
"""

from .service import send_email, send_welcome_email

__all__ = ["send_email", "send_welcome_email"]
