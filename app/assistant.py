"""Minimal private material editor, with no external AI calls."""
from fastapi import Request,HTTPException,Form
from fastapi.responses import RedirectResponse,Response,JSONResponse

def install(app):
    from app.main import page,current_user,db
    from app.teacher import auth
    from app.methodist_ai import install as install_methodist,enabled
    install_methodist(app)
    def owned(identifier,u):
        with db() as c:
            row=c.execute('SELECT * FROM teacher_materials WHERE id=%s AND user_id=%s',(identifier,u['id'])).fetchone()
        if not row: raise HTTPException(404,'Материал не найден')
        return row
    @app.get('/teacher/prepare')
    def prepare(request:Request,edit:int=0,mode:str='builder'):
        u=current_user(request)
        if not u: return RedirectResponse('/login',303)
        editing=owned(edit,u) if edit else None
        return page(request,'assistant',user=u,page_title='Подготовка урока',editing=editing,form_error='',manual=bool(edit) or mode=='manual',ai_mode=mode in ('ai','review'),ai_review=mode=='review',ai_enabled=enabled(u))
    @app.post('/teacher/prepare/build')
    def build(request:Request,csrf:str=Form(...),topic:str=Form(...),goal:str=Form(...),prior:str=Form('partial'),minutes:int=Form(45)):
        auth(request,csrf)
        from app.lesson_builder import make_plan
        try: return JSONResponse(make_plan(topic.strip(),goal,prior,minutes))
        except ValueError as exc: return JSONResponse({'error':str(exc)},status_code=400)
    @app.post('/teacher/prepare/save')
    def save(request:Request,csrf:str=Form(...),content:str=Form(...),title:str=Form(''),subject:str=Form(''),grade:str=Form(''),identifier:int=Form(0)):
        u=auth(request,csrf)
        previous=owned(identifier,u) if identifier else None
        content=content.strip(); title=title.strip(); subject=subject.strip(); grade=grade.strip()
        if not title: title=next((line.strip()[:160] for line in content.splitlines() if line.strip()),'Материал')
        error=''
        if not content: error='Напишите текст материала.'
        elif len(content)>100000: error='Текст — до 100 000 символов.'
        elif len(title)>160 or len(subject)>100 or len(grade)>50: error='Название — до 160 символов, предмет — до 100, класс — до 50.'
        with db() as c:
            if not identifier and c.execute('SELECT count(*) AS n FROM teacher_materials WHERE user_id=%s',(u['id'],)).fetchone()['n']>=1000:
                error='Достигнут лимит: 1000 материалов.'
            if not error:
                if identifier:
                    c.execute('UPDATE teacher_materials SET title=%s,content=%s,subject=%s,grade=%s,updated_at=now() WHERE id=%s AND user_id=%s',(title,content,subject,grade,identifier,u['id']))
                else:
                    c.execute("INSERT INTO teacher_materials(user_id,kind,title,content,subject,grade) VALUES(%s,'task',%s,%s,%s,%s)",(u['id'],title,content,subject,grade))
        if error:
            response=page(request,'assistant',user=u,page_title='Подготовка урока',editing=dict(id=identifier,title=title,content=content,subject=subject,grade=grade),form_error=error,manual=True)
            response.status_code=400
            return response
        return RedirectResponse('/teacher/materials?saved=1',303)
    @app.get('/teacher/materials/{identifier}/download')
    def download(identifier:int,request:Request):
        row=owned(identifier,auth(request))
        return Response(row['title']+'\n\n'+row['content'],media_type='text/plain; charset=utf-8',headers={'Content-Disposition':'attachment; filename="material.txt"'})
    @app.get('/teacher/help')
    def legacy_overview(): return RedirectResponse('/teacher/prepare',307)
    @app.get('/teacher/help/{slug}')
    def legacy_detail(slug:str):
        target={'prepare':'/teacher/prepare','adapt':'/teacher/prepare','library':'/teacher/materials','review':'/account','resources':'/teacher/materials'}
        if slug not in target: raise HTTPException(404)
        return RedirectResponse(target[slug],307)
