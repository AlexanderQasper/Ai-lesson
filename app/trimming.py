import math, os, secrets, subprocess
from pathlib import Path
from uuid import UUID,uuid4
from fastapi import Request,Form,HTTPException
from fastapi.responses import FileResponse,RedirectResponse,Response
from app.uploads import ROOT,QUOTA,account_page

def time_label(seconds):
    minutes=int(seconds//60)
    return f"{minutes}:{seconds-minutes*60:06.3f}"
def parse_time(value):
    parts=value.strip().replace(",",".").split(":")
    if not 1<=len(parts)<=3: raise ValueError()
    nums=[float(x) for x in parts]
    if any(not math.isfinite(x) or x<0 for x in nums): raise ValueError()
    if len(nums)>1 and any(x>=60 for x in nums[1:]): raise ValueError()
    result=0
    for x in nums: result=result*60+x
    return result

def initialize():
    from app.main import db
    with db() as conn:
        conn.execute("ALTER TABLE audio_recordings ADD COLUMN IF NOT EXISTS trim_start DOUBLE PRECISION NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE audio_recordings ADD COLUMN IF NOT EXISTS trim_end DOUBLE PRECISION")
        conn.execute("ALTER TABLE audio_recordings ADD COLUMN IF NOT EXISTS trim_size BIGINT NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE audio_recordings ADD COLUMN IF NOT EXISTS trim_duration DOUBLE PRECISION")

def install(app):
    @app.get("/recordings/{identifier}/audio")
    def audio(identifier: UUID,request: Request,original: bool=False):
        from app.main import db,current_user
        user=current_user(request)
        if not user: raise HTTPException(401,"Sign in required")
        with db() as conn:
            row=conn.execute("SELECT trim_size FROM audio_recordings WHERE id=%s AND user_id=%s",(identifier,user["id"])).fetchone()
        if not row: raise HTTPException(404,"Recording not found")
        path=ROOT/str(user["id"])/(str(identifier)+(".trim.mp3" if row["trim_size"] and not original else ".mp3"))
        if not path.is_file(): raise HTTPException(404,"Recording not found")
        return FileResponse(path,media_type="audio/mpeg")

    @app.post("/recordings/{identifier}/trim")
    def trim(identifier: UUID,request: Request,csrf: str=Form(...),start: str=Form("0"),end: str=Form(""),mode: str=Form("trim")):
        from app.main import db,current_user
        user=current_user(request)
        if not user: return RedirectResponse("/login",303)
        if not secrets.compare_digest(user["csrf"],csrf): raise HTTPException(403,"Invalid request")
        folder=ROOT/str(user["id"]); source=folder/(str(identifier)+".mp3")
        target=folder/(str(identifier)+".trim.mp3")
        temp=folder/(str(uuid4())+".mp3"); backup=folder/(str(uuid4())+".bak")
        replaced=False; committed=False
        try:
            with db() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(%s)",(user["id"],))
                row=conn.execute("SELECT * FROM audio_recordings WHERE id=%s AND user_id=%s FOR UPDATE",(identifier,user["id"])).fetchone()
                if not row: raise HTTPException(404,"Recording not found")
                if mode!="trim": raise ValueError("Восстановление исходника недоступно. Храним только сохранённый фрагмент.")
                try: a=parse_time(start); z=parse_time(end)
                except ValueError: raise ValueError("Укажите время в формате минуты:секунды, например 1:25.")
                if not 0<=a<z or z>row["duration_seconds"]+0.1 or z-a<1:
                    raise ValueError("Конец должен быть позже начала, внутри записи. Минимум — 1 секунда.")
                z=min(z,row["duration_seconds"])
                subprocess.run(["ffmpeg","-nostdin","-v","error","-protocol_whitelist","file,pipe","-ss",str(a),"-i",str(source),"-t",str(z-a),"-map","0:a:0","-c:a","copy",str(temp)],capture_output=True,check=True,timeout=90)
                os.chmod(temp,0o600)
                size=temp.stat().st_size
                used=conn.execute("SELECT COALESCE(sum(size_bytes+trim_size),0) AS size FROM audio_recordings WHERE user_id=%s",(user["id"],)).fetchone()["size"]
                if used-row["size_bytes"]-row["trim_size"]+size>QUOTA: raise ValueError("Для сохранения фрагмента недостаточно места в лимите 2 ГБ.")
                source.rename(backup)
                temp.rename(source); replaced=True
                conn.execute("UPDATE audio_recordings SET trim_start=0,trim_end=NULL,trim_size=0,trim_duration=NULL,size_bytes=%s,duration_seconds=%s WHERE id=%s",(size,z-a,identifier))
                (folder/(str(identifier)+".wave.json")).unlink(missing_ok=True)
            committed=True
            backup.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
        except HTTPException: raise
        except Exception as exc:
            if replaced and not committed: source.unlink(missing_ok=True)
            if backup.exists() and not committed: backup.rename(source)
            error=str(exc) if isinstance(exc,ValueError) else "Не удалось сохранить фрагмент. Попробуйте ещё раз."
            return account_page(request,user,error,400)
        finally: temp.unlink(missing_ok=True)
        return RedirectResponse("/account#recording-"+str(identifier),303)

    @app.get("/assets/audio.js")
    def javascript():
        return Response((Path(__file__).parent / "assets" / "audio.js").read_text(),media_type="application/javascript")

    @app.get("/recordings/{identifier}/waveform")
    def waveform(identifier: UUID,request: Request):
        from app.main import db,current_user
        import json,array,sys
        user=current_user(request)
        if not user: raise HTTPException(401,"Sign in required")
        with db() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(%s)",(user["id"],))
            row=conn.execute("SELECT duration_seconds FROM audio_recordings WHERE id=%s AND user_id=%s",(identifier,user["id"])).fetchone()
            if not row: raise HTTPException(404,"Recording not found")
            folder=ROOT/str(user["id"]); cache=folder/(str(identifier)+".wave.json")
            if cache.exists(): return FileResponse(cache,media_type="application/json")
            source=folder/(str(identifier)+".mp3")
            try:
                result=subprocess.run(["ffmpeg","-nostdin","-v","error","-threads","1","-filter_threads","1","-protocol_whitelist","file,pipe","-i",str(source),"-ac","1","-af","aeval=abs(val(0)),aresample=100","-ar","100","-f","f32le","pipe:1"],capture_output=True,check=True,timeout=90)
                samples=array.array("f"); samples.frombytes(result.stdout)
                if sys.byteorder!="little": samples.byteswap()
                step=max(1,math.ceil(len(samples)/60000))
                peaks=[round(max(samples[n:n+step]),5) for n in range(0,len(samples),step)]
                maximum=max(peaks,default=0) or 1
                peaks=[round(max(0,min(1,x/maximum)),4) for x in peaks]
                temp=folder/(str(uuid4())+".json")
                temp.write_text(json.dumps({"duration":row["duration_seconds"],"peaks":[peaks]})); os.chmod(temp,0o600); temp.replace(cache)
            except (subprocess.SubprocessError,OSError): raise HTTPException(503,"Waveform unavailable")
        return FileResponse(cache,media_type="application/json")

    @app.post("/recordings/{identifier}/delete")
    def delete_recording(identifier: UUID,request: Request,csrf: str=Form(...)):
        from app.main import db,current_user
        user=current_user(request)
        if not user: return RedirectResponse("/login",303)
        if not secrets.compare_digest(user["csrf"],csrf): raise HTTPException(403,"Invalid request")
        folder=ROOT/str(user["id"]); moved=[]; committed=False
        try:
            with db() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(%s)",(user["id"],))
                row=conn.execute("SELECT id FROM audio_recordings WHERE id=%s AND user_id=%s FOR UPDATE",(identifier,user["id"])).fetchone()
                if not row: raise HTTPException(404,"Recording not found")
                for suffix in [".mp3",".trim.mp3",".wave.json"]:
                    source=folder/(str(identifier)+suffix)
                    if source.exists():
                        pending=folder/(str(uuid4())+".delete")
                        source.rename(pending); moved.append((source,pending))
                conn.execute("DELETE FROM audio_recordings WHERE id=%s AND user_id=%s",(identifier,user["id"]))
            committed=True
        finally:
            for source,pending in moved:
                if committed: pending.unlink(missing_ok=True)
                else: pending.rename(source)
        return RedirectResponse("/account",303)
