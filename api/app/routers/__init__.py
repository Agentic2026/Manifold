from app.routers import auth_ext, dashboard, aegis, ingest


def include_all_routers(app):
    app.include_router(auth_ext.router)
    app.include_router(dashboard.router)
    app.include_router(aegis.router)
    app.include_router(ingest.router)
