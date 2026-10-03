"""Integration checks with disposable accounts; never modifies real materials."""
import json,secrets
from uuid import uuid4
from pathlib import Path
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from app.main import app,db,digest,COOKIE
from app.uploads import ROOT
ids=[]; folders=[]
def check(response,status):
    assert response.status_code==status,(status,response.status_code,response.text[:300])
try:
    with TestClient(app,base_url='https://projector-school.info',follow_redirects=False) as client:
        accounts=[]
        for n in range(2):
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
            with db() as c:
                u=c.execute('INSERT INTO users(google_sub,email,name) VALUES(%s,%s,%s) RETURNING id',('teacher-test-'+str(uuid4()),'fixture@example.invalid','Fixture')).fetchone()['id']
                ids.append(u)
                c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(%s,%s,%s,now()+interval '1 hour')",(digest(token),u,csrf))
            accounts.append((u,csrf,{'Cookie':COOKIE+'='+token}))
        u,csrf,h=accounts[0]; _,csrf2,h2=accounts[1]
        check(client.get('/teacher/courses'),401)
        check(client.get('/teacher/courses',headers=h),200)
        check(client.get('/teacher/bank',headers=h),200)
        check(client.post('/teacher/courses/save',headers=h,data={'csrf':'wrong','title':'bad'}),403)
        payload={'csrf':csrf,'title':'Test <script>alert(1)</script>','subject':'English','grade':'A2','description':'Test course','content':'# Unit 1\nChristmas'}
        check(client.post('/teacher/courses/save',headers=h,data=payload),303)
        with db() as c: course=c.execute('SELECT id FROM teacher_courses WHERE user_id=%s',(u,)).fetchone()['id']
        check(client.get(f'/teacher/courses/{course}/export',headers=h2),404)
        check(client.get(f'/teacher/courses?edit={course}',headers=h2),404)
        check(client.post('/teacher/courses/save',headers=h2,data={**payload,'csrf':csrf2,'identifier':course}),404)
        resp=client.get('/teacher/courses',headers=h); check(resp,200)
        assert '&lt;script&gt;' in resp.text and '<script>alert(1)</script>' not in resp.text
        exported=client.get(f'/teacher/courses/{course}/export',headers=h); check(exported,200)
        check(client.post('/teacher/courses/import',headers=h,data={'csrf':csrf},files={'course':('course.json',exported.content,'application/json')}),303)
        check(client.post('/teacher/courses/import',headers=h,data={'csrf':csrf},files={'course':('notes.md',b'# Topic\nText','text/plain')}),303)
        check(client.post('/teacher/courses/import',headers=h,data={'csrf':csrf},files={'course':('bad.json',b'{','application/json')}),400)
        check(client.post('/teacher/courses/import',headers=h,data={'csrf':csrf},files={'course':('bad.exe',b'text','application/octet-stream')}),400)
        check(client.post('/teacher/courses/save',headers=h,data={**payload,'identifier':course,'content':'Updated'}),303)
        check(client.get('/teacher/courses?q=Updated',headers=h),200)
        for kind in ('topic','task'):
            check(client.post('/teacher/bank/save',headers=h,data={'csrf':csrf,'kind':kind,'title':'Christmas','content':'Discuss traditions'}),303)
        with db() as c: material=c.execute('SELECT id FROM teacher_materials WHERE user_id=%s LIMIT 1',(u,)).fetchone()['id']
        check(client.post('/teacher/bank/save',headers=h2,data={'csrf':csrf2,'kind':'task','title':'No','identifier':material}),404)
        check(client.get('/teacher/bank?kind=task&q=Christmas',headers=h),200)
        bad=client.post('/teacher/courses/import',headers=h,data={'csrf':csrf},files={'course':('bad.json',b'{','application/json')})
        assert 'Нужен UTF-8 текст' in bad.text and '<html' in bad.text
        check(client.post('/teacher/courses/import',headers=h,data={'csrf':csrf},files={'course':('too-big.txt',b'a'*1200001,'text/plain')}),413)
        identifier=uuid4(); folder=ROOT/str(u); folder.mkdir(mode=0o700); folders.append(folder)
        audio=folder/(str(identifier)+'.mp3'); audio.write_bytes(b'fixture'); stat=audio.stat()
        with db() as c:
            c.execute('INSERT INTO audio_recordings(id,user_id,title,original_name,size_bytes,duration_seconds) VALUES(%s,%s,%s,%s,%s,%s)',(identifier,u,'Fixture','fixture.mp3',7,30))
            tid=c.execute('INSERT INTO recording_transcripts(recording_id,model,payload,source_size,source_mtime) VALUES(%s,%s,%s,%s,%s) RETURNING id',(identifier,'Fixture model',Jsonb({'segments':[{'start':0,'end':1,'text':'Hello <script>','speaker':'UNKNOWN'}],'audio_seconds':30}),stat.st_size,stat.st_mtime_ns)).fetchone()['id']
        check(client.get(f'/recordings/{identifier}/transcript',headers=h2),404)
        check(client.get(f'/recordings/{identifier}/transcript/{tid}/download',headers=h2),404)
        resp=client.get(f'/recordings/{identifier}/transcript',headers=h); check(resp,200); assert 'Hello &lt;script&gt;' in resp.text
        check(client.get(f'/recordings/{identifier}/transcript/{tid}/download',headers=h),200)
        audio.write_bytes(b'changed fixture')
        check(client.get(f'/recordings/{identifier}/transcript/{tid}/download',headers=h),409)
        assert 'устарел' in client.get(f'/recordings/{identifier}/transcript',headers=h).text
        check(client.get('/account',headers=h),200)
        check(client.get('/healthz'),200)
        print('PASS: CRUD/import/export/search; account isolation; CSRF; escaped content; transcript ownership and stale audio',flush=True)
finally:
    with db() as c:
        for u in ids: c.execute('DELETE FROM users WHERE id=%s AND google_sub LIKE %s',(u,'teacher-test-%'))
    for folder in folders:
        for file in folder.iterdir(): file.unlink()
        folder.rmdir()
