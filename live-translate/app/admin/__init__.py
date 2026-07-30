"""Admin package: bootstrap + protected management routes.

The admin module is split into two layers:

* ``bootstrap.ensure_admin_user`` is called from the FastAPI lifespan and is
  idempotent (only creates the configured admin when the email is unused).
* ``routes.router`` exposes the protected management endpoints.

Both endpoints and bootstrap reuse the same ``hash_password`` helper and the
``role`` column introduced on the ``User`` model.
"""
from app.admin.routes import router

__all__ = ["router"]