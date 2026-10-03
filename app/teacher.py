"""Private teacher library and read-only benchmark transcript viewer."""
import json, secrets
from pathlib import Path
from uuid import UUID
from fastapi import Request, HTTPException, Form, UploadFile, File
from fastapi.responses import RedirectResponse, Response
from psycopg.types.json import Jsonb

def initialize():
    from app.main import db
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS recording_transcripts (
          id BIGSERIAL PRIMARY KEY,recording_id UUID NOT NULL REFERENCES audio_recordings(id) ON DELETE CASCADE,
          model TEXT NOT NULL,payload JSONB NOT NULL,source_size BIGINT NOT NULL,source_mtime BIGINT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),UNIQUE(recording_id,model))""")
        c.execute("""CREATE TABLE IF NOT EXISTS teacher_courses (
          id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          title TEXT NOT NULL,subject TEXT NOT NULL DEFAULT '',grade TEXT NOT NULL DEFAULT '',
          description TEXT NOT NULL DEFAULT '',content TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        c.execute("""CREATE TABLE IF NOT EXISTS teacher_materials (
          id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          kind TEXT NOT NULL CHECK(kind IN ('topic','task')),title TEXT NOT NULL,subject TEXT NOT NULL DEFAULT '',
          grade TEXT NOT NULL DEFAULT '',content TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        c.execute('CREATE INDEX IF NOT EXISTS teacher_courses_owner ON teacher_courses(user_id)')
        c.execute('CREATE INDEX IF NOT EXISTS teacher_materials_owner ON teacher_materials(user_id)')

def auth(request,csrf=None):
    from app.main import current_user
    u=current_user(request)
    if not u: raise HTTPException(401,'Войдите в кабинет')
    if csrf is not None and not secrets.compare_digest(u['csrf'],csrf): raise HTTPException(403,'Invalid request')
    return u

def fields(title,subject,grade,content,description=''):
    vals=[title.strip(),subject.strip(),grade.strip(),content.strip(),description.strip()]
    if not vals[0] or any(len(v)>limit for v,limit in zip(vals,[160,100,50,100000,2000])):
        raise HTTPException(400,'Укажите название до 160 символов. Текст — до 100 000 символов.')
    return vals

def owned_recording(identifier,u):
    from app.main import db
    with db() as c:
        r=c.execute('SELECT * FROM audio_recordings WHERE id=%s AND user_id=%s',(identifier,u['id'])).fetchone()
    if not r: raise HTTPException(404,'Запись не найдена')
    return r

def transcript_rows(identifier,u):
    from app.main import db
    from app.uploads import ROOT
    r=owned_recording(identifier,u)
    path=ROOT/str(u['id'])/(str(identifier)+('.trim.mp3' if r['trim_size'] else '.mp3'))
    stat=path.stat() if path.is_file() else None
    with db() as c:
        rows=c.execute('SELECT * FROM recording_transcripts WHERE recording_id=%s ORDER BY id',(identifier,)).fetchall()
    for row in rows:
        row['stale']=not stat or stat.st_size!=row['source_size'] or stat.st_mtime_ns!=row['source_mtime']
        row['segments']=row['payload'].get('segments',[])
        row['duration']=row['payload'].get('audio_seconds',300)
    return r,rows

class LibraryBodyLimit:
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or scope['method']!='POST' or not scope['path'].startswith('/teacher/'):
            return await self.app(scope,receive,send)
        from fastapi.responses import PlainTextResponse
        limit=1200000; size=0
        try: length=int(dict(scope.get('headers',[])).get(b'content-length',b'0'))
        except ValueError: length=limit+1
        if length>limit: return await PlainTextResponse('Максимум 1 МБ',status_code=413)(scope,receive,send)
        async def bounded():
            nonlocal size
            msg=await receive(); size+=len(msg.get('body',b''))
            if size>limit: raise HTTPException(413,'Максимум 1 МБ')
            return msg
        await self.app(scope,bounded,send)

def install(app):
    from app.main import db,page
    app.add_middleware(LibraryBodyLimit)
    async def workspace_error(request,exc):
        from fastapi.exception_handlers import http_exception_handler
        from app.main import current_user
        if request.url.path.startswith('/teacher/') and exc.status_code in (400,413):
            u=current_user(request)
            if u:
                section='bank' if request.url.path.startswith('/teacher/bank') or (request.url.path=='/teacher/materials' and request.query_params.get('tab','bank')=='bank') else 'courses'
                table='teacher_materials' if section=='bank' else 'teacher_courses'
                with db() as c: items=c.execute(f'SELECT * FROM {table} WHERE user_id=%s ORDER BY updated_at DESC',(u['id'],)).fetchall()
                response=page(request,'workspace',user=u,section=section,items=items,editing=None,q='',kind='',saved=False,library_error=str(exc.detail))
                response.status_code=exc.status_code
                return response
        return await http_exception_handler(request,exc)
    app.add_exception_handler(HTTPException,workspace_error)
    @app.get('/recordings/{identifier}/transcript')
    def transcript(identifier:UUID,request:Request):
        u=auth(request); r,rows=transcript_rows(identifier,u)
        return page(request,'workspace',user=u,section='transcript',recording=r,transcripts=rows)
    @app.get('/recordings/{identifier}/transcript/{transcript_id}/download')
    def transcript_download(identifier:UUID,transcript_id:int,request:Request):
        u=auth(request); r,rows=transcript_rows(identifier,u)
        row=next((x for x in rows if x['id']==transcript_id),None)
        if not row: raise HTTPException(404,'Черновик не найден')
        if row['stale']: raise HTTPException(409,'Запись изменилась после распознавания')
        text='ЧЕРНОВИК — НЕ ПРОВЕРЕН\n'+row['model']+'\n\n'
        for s in row['segments']:
            text+=f"[{s['start']:.2f}–{s['end']:.2f}] {s.get('speaker','')} {s['text'].strip()}\n"
        return Response(text,media_type='text/plain; charset=utf-8',headers={'Content-Disposition':'attachment; filename="transcript.txt"'})
    @app.get('/teacher/{section}')
    @app.get('/teacher/materials')
    def library(request:Request,section:str='courses',q:str='',kind:str='',edit:int=0,tab:str='bank'):
        if request.url.path=='/teacher/materials': section=tab
        if section=='bank' and edit: return RedirectResponse('/teacher/prepare?edit='+str(edit),303)
        u=auth(request)
        if section not in ('courses','bank'): raise HTTPException(404)
        if len(q)>150: raise HTTPException(400)
        table='teacher_courses' if section=='courses' else 'teacher_materials'
        with db() as c:
            rows=c.execute(f'SELECT * FROM {table} WHERE user_id=%s ORDER BY updated_at DESC,id DESC',(u['id'],)).fetchall()
        selected=next((x for x in rows if x['id']==edit),None)
        if edit and not selected: raise HTTPException(404)
        filtered=[x for x in rows if (not q or q.casefold() in (x['title']+' '+x['subject']+' '+x['content']).casefold()) and (section=='courses' or not kind or x['kind']==kind)]
        return page(request,'workspace',user=u,section=section,items=filtered,editing=selected,q=q,kind=kind,saved=request.query_params.get('saved')=='1')
    @app.post('/teacher/courses/save')
    def save_course(request:Request,csrf:str=Form(...),title:str=Form(...),subject:str=Form(''),grade:str=Form(''),description:str=Form(''),content:str=Form(''),identifier:int=Form(0)):
        u=auth(request,csrf); title,subject,grade,content,description=fields(title,subject,grade,content,description)
        with db() as c:
            if identifier:
                if not c.execute('UPDATE teacher_courses SET title=%s,subject=%s,grade=%s,content=%s,description=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING id',(title,subject,grade,content,description,identifier,u['id'])).fetchone(): raise HTTPException(404)
            else:
                if c.execute('SELECT count(*) AS n FROM teacher_courses WHERE user_id=%s',(u['id'],)).fetchone()['n']>=100: raise HTTPException(400,'Лимит — 100 курсов')
                c.execute('INSERT INTO teacher_courses(user_id,title,subject,grade,content,description) VALUES(%s,%s,%s,%s,%s,%s)',(u['id'],title,subject,grade,content,description))
        return RedirectResponse('/teacher/materials?tab=courses&saved=1',303)
    @app.post('/teacher/courses/import')
    def import_course(request:Request,csrf:str=Form(...),course:UploadFile=File(...)):
        u=auth(request,csrf)
        try:
            raw=course.file.read(1000001)
            if len(raw)>1000000: raise HTTPException(413,'Максимум 1 МБ')
            suffix=Path(course.filename or '').suffix.lower()
            try:
                text=raw.decode('utf-8-sig')
                data=json.loads(text) if suffix=='.json' else {'title':Path(course.filename or 'Курс').stem,'content':text}
            except (UnicodeError,json.JSONDecodeError): raise HTTPException(400,'Нужен UTF-8 текст или JSON курса')
            if suffix not in ('.json','.txt','.md') or not isinstance(data,dict): raise HTTPException(400,'Поддерживаются TXT, Markdown и JSON')
            if any(not isinstance(data.get(k,''),str) for k in ('title','subject','grade','content','description')): raise HTTPException(400,'Поля курса должны быть текстом')
            title,subject,grade,content,description=fields(data.get('title',''),data.get('subject',''),data.get('grade',''),data.get('content',''),data.get('description',''))
            with db() as c:
                if c.execute('SELECT count(*) AS n FROM teacher_courses WHERE user_id=%s',(u['id'],)).fetchone()['n']>=100: raise HTTPException(400,'Лимит — 100 курсов')
                c.execute('INSERT INTO teacher_courses(user_id,title,subject,grade,content,description) VALUES(%s,%s,%s,%s,%s,%s)',(u['id'],title,subject,grade,content,description))
        finally: course.file.close()
        return RedirectResponse('/teacher/materials?tab=courses&saved=1',303)
    @app.get('/teacher/courses/{identifier}/export')
    def export_course(identifier:int,request:Request):
        u=auth(request)
        with db() as c: row=c.execute('SELECT title,subject,grade,description,content FROM teacher_courses WHERE id=%s AND user_id=%s',(identifier,u['id'])).fetchone()
        if not row: raise HTTPException(404)
        return Response(json.dumps({'schema_version':1,**row},ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="course.json"'})
    @app.post('/teacher/bank/save')
    def save_material(request:Request,csrf:str=Form(...),kind:str=Form(...),title:str=Form(...),subject:str=Form(''),grade:str=Form(''),content:str=Form(''),identifier:int=Form(0)):
        u=auth(request,csrf); title,subject,grade,content,_=fields(title,subject,grade,content)
        if kind not in ('topic','task'): raise HTTPException(400)
        with db() as c:
            if identifier:
                if not c.execute('UPDATE teacher_materials SET kind=%s,title=%s,subject=%s,grade=%s,content=%s,updated_at=now() WHERE id=%s AND user_id=%s RETURNING id',(kind,title,subject,grade,content,identifier,u['id'])).fetchone(): raise HTTPException(404)
            else:
                if c.execute('SELECT count(*) AS n FROM teacher_materials WHERE user_id=%s',(u['id'],)).fetchone()['n']>=1000: raise HTTPException(400,'Лимит — 1000 материалов')
                c.execute('INSERT INTO teacher_materials(user_id,kind,title,subject,grade,content) VALUES(%s,%s,%s,%s,%s,%s)',(u['id'],kind,title,subject,grade,content))
        return RedirectResponse('/teacher/materials?tab=bank&saved=1',303)
