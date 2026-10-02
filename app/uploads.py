import json, math, os, secrets, subprocess
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from app.audio_formats import EXTENSIONS, normalize
MAX_FILE = 250*1024*1024
MAX_REQUEST = MAX_FILE+1024*1024
QUOTA = 2*1024*1024*1024
ROOT = Path(os.environ.get("MATERIALS_DIR", "/data"))/"audio"
class TooLarge(Exception): pass
class BodyLimit:
    def __init__(self, app): self.app=app
    async def __call__(self, scope, receive, send):
        if scope["type"]!="http" or scope["method"]!="POST" or scope["path"]!="/recordings":
            return await self.app(scope,receive,send)
        try: length=int(dict(scope.get("headers",[])).get(b"content-length",b"0"))
        except ValueError: length=MAX_REQUEST+1
        if length>MAX_REQUEST:
            return await PlainTextResponse("Файл слишком большой. Максимум — 250 МБ. Вернитесь в кабинет.",status_code=413)(scope,receive,send)
        size=0
        async def limited():
            nonlocal size
            msg=await receive(); size+=len(msg.get("body",b""))
            if size>MAX_REQUEST: raise TooLarge()
            return msg
        try: await self.app(scope,limited,send)
        except TooLarge:
            await PlainTextResponse("Файл слишком большой. Максимум — 250 МБ.",status_code=413)(scope,receive,send)
def initialize():
    from app.main import db
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS audio_recordings (
            id UUID PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,original_name TEXT NOT NULL,size_bytes BIGINT NOT NULL,
            duration_seconds DOUBLE PRECISION NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        conn.execute("CREATE INDEX IF NOT EXISTS audio_recordings_owner ON audio_recordings(user_id,created_at DESC)")
def account_page(request,user,error=None,status=200):
    from app.main import db,page
    with db() as conn:
        rows=conn.execute("SELECT * FROM audio_recordings WHERE user_id=%s ORDER BY created_at DESC",(user["id"],)).fetchall()
    used=sum(x["size_bytes"]+x.get("trim_size",0) for x in rows)
    for row in rows:
        secs=round(row["trim_duration"] or row["duration_seconds"])
        from app.trimming import time_label
        row["start_label"]=time_label(row["trim_start"])
        row["end_label"]=time_label(row["trim_end"] if row["trim_end"] is not None else row["duration_seconds"])
        row["duration_label"]=f"{secs//60}:{secs%60:02d}"
        row["size_label"]=f'{row["size_bytes"]/1024/1024:.1f}'
    response=page(request,"account",user=user,recordings=rows,used_mb=round(used/1024/1024),upload_error=error,uploaded=request.query_params.get("uploaded")=="1")
    response.status_code=status
    return response

def install(app):
    app.add_middleware(BodyLimit)
    @app.post("/recordings")
    def upload(request: Request,audio: UploadFile=File(...),csrf: str=Form(...),title: str=Form("")):
        from app.main import db,current_user
        user=current_user(request)
        if not user:
            audio.file.close(); return RedirectResponse("/login",303)
        if not secrets.compare_digest(user["csrf"],csrf):
            audio.file.close(); raise HTTPException(403,"Invalid request")
        filename=Path((audio.filename or "").replace("\\","/")).name[:200]
        title=title.strip()
        if Path(filename).suffix.lower() not in EXTENSIONS or len(title)>160:
            audio.file.close(); return account_page(request,user,"Выберите MP3, M4A, AAC, WAV, FLAC, OGG, OPUS или WebM. Название урока — до 160 символов.",400)
        identifier=uuid4(); folder=ROOT/str(user["id"])
        folder.mkdir(exist_ok=True,mode=0o700)
        temporary=folder/(str(identifier)+".part"); final=folder/(str(identifier)+".mp3")
        try:
            with db() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(%s)",(user["id"],))
                used=conn.execute("SELECT COALESCE(sum(size_bytes+trim_size),0) AS size FROM audio_recordings WHERE user_id=%s",(user["id"],)).fetchone()["size"]
                size=0
                with temporary.open("xb") as out:
                    os.chmod(temporary,0o600)
                    while chunk:=audio.file.read(1024*1024):
                        size+=len(chunk)
                        if size>MAX_FILE: raise ValueError("Файл слишком большой. Максимум — 250 МБ.")
                        if used+size>QUOTA: raise ValueError("Загрузка превышает лимит кабинета — 2 ГБ.")
                        out.write(chunk)
                if not size: raise ValueError("Файл пустой. Выберите аудиозапись урока.")
                size,duration=normalize(temporary,final,QUOTA-used)
                saved_name=Path(filename).stem+".mp3"
                conn.execute("INSERT INTO audio_recordings(id,user_id,title,original_name,size_bytes,duration_seconds) VALUES(%s,%s,%s,%s,%s,%s)",(identifier,user["id"],title or Path(filename).stem,saved_name,size,duration))
        except ValueError as exc:
            temporary.unlink(missing_ok=True); final.unlink(missing_ok=True)
            return account_page(request,user,str(exc),400)
        except Exception:
            temporary.unlink(missing_ok=True); final.unlink(missing_ok=True)
            return account_page(request,user,"Не удалось сохранить запись. Попробуйте ещё раз.",503)
        finally:
            temporary.unlink(missing_ok=True)
            audio.file.close()
        return RedirectResponse("/account?uploaded=1",303)
    @app.get("/recordings/{identifier}/download")
    def download(identifier: UUID,request: Request):
        from app.main import db,current_user
        user=current_user(request)
        if not user: return RedirectResponse("/login",303)
        with db() as conn:
            row=conn.execute("SELECT original_name,trim_size FROM audio_recordings WHERE id=%s AND user_id=%s",(identifier,user["id"])).fetchone()
        if not row: raise HTTPException(404,"Recording not found")
        path=ROOT/str(user["id"])/(str(identifier)+(".trim.mp3" if row["trim_size"] else ".mp3"))
        if not path.is_file(): raise HTTPException(404,"Recording not found")
        return FileResponse(path,media_type="audio/mpeg",filename=row["original_name"])
