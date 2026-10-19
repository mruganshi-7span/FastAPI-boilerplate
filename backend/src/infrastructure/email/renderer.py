"""Jinja rendering for email templates.

Templates live next to this module in ``templates/``, so the path resolves the
same way whether the code is imported by the API (``src.infrastructure``) or by
the taskiq worker (``infrastructure``).
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)


def render_template(template_name: str, **context: object) -> str:
    """Render a template under ``templates/`` (e.g. ``"emails/welcome.html"``).

    HTML templates are autoescaped, so user-supplied values like a name are safe to pass in.
    """
    return _env.get_template(template_name).render(**context)
