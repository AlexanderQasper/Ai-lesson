"""Preparation workspace and compatibility redirects."""
from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
def install(app):
    from app.main import page,current_user
    @app.get('/teacher/prepare')
    def prepare(request:Request):
        return page(request,'assistant',user=current_user(request),page_title='Подготовка урока')
    @app.get('/teacher/help')
    def legacy_overview(): return RedirectResponse('/teacher/prepare',307)
    @app.get('/teacher/help/{slug}')
    def legacy_detail(slug:str):
        target={'prepare':'/teacher/prepare','adapt':'/teacher/prepare#adapt','library':'/teacher/materials','review':'/account','resources':'/teacher/materials'}
        if slug not in target: raise HTTPException(404)
        return RedirectResponse(target[slug],307)
