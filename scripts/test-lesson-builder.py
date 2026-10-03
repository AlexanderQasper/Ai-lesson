import secrets
from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app,db,digest,COOKIE
ids=[]
def check(r,status): assert r.status_code==status,(r.status_code,r.text[:200])
try:
 with TestClient(app,base_url='https://projector-school.info',follow_redirects=False) as client:
  accounts=[]
  for i in range(2):
   token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
   with db() as c:
    u=c.execute('INSERT INTO users(google_sub,email,name) VALUES(%s,%s,%s) RETURNING id',('manual-fixture-'+str(uuid4()),'fixture@example.invalid','Fixture')).fetchone()['id']; ids.append(u)
    c.execute("INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(%s,%s,%s,now()+interval '1 hour')",(digest(token),u,csrf))
   accounts.append((u,csrf,{'Cookie':COOKIE+'='+token}))
  u,csrf,h=accounts[0]; _,csrf2,h2=accounts[1]
  check(client.get('/teacher/prepare'),303)
  check(client.get('/teacher/materials'),401)
  check(client.post('/teacher/prepare/save',headers=h,data={'csrf':'bad','content':'Test'}),403)
  r=client.post('/teacher/prepare/save',headers=h,data={'csrf':csrf,'content':'   '}); check(r,400); assert 'Напишите текст' in r.text
  from app.lesson_builder import SCHEMES,make_plan
  check(client.post('/teacher/prepare/build',data={'csrf':csrf,'topic':'Тема','goal':'new'}),401)
  check(client.post('/teacher/prepare/build',headers=h,data={'csrf':'bad','topic':'Тема','goal':'new'}),403)
  check(client.post('/teacher/prepare/build',headers=h,data={'csrf':csrf,'topic':'Тема','goal':'invalid'}),400)
  check(client.post('/teacher/prepare/build',headers=h,data={'csrf':csrf,'topic':'Тема','goal':'new','minutes':19}),400)
  for goal in SCHEMES:
   r=client.post('/teacher/prepare/build',headers=h,data={'csrf':csrf,'topic':'Сложение дробей','goal':goal,'prior':'partial','minutes':45}); check(r,200)
   result=r.json(); assert result['recommended']==goal and len(result['openings'])>=2
   for schema in result['plans'].values(): assert sum(stage['minutes'] for stage in schema['stages'])==45
  for goal in SCHEMES:
   for prior in ['new','partial','secure']:
    for minutes in [20,30,40,45,60,90,120]:
     result=make_plan('Тема',goal,prior,minutes)
     for schema in result['plans'].values(): assert sum(stage['minutes'] for stage in schema['stages'])==minutes
  assert make_plan('Тема','discussion','new',45)['recommended']=='new'
  assert make_plan('Тема','new','secure',45)['recommended']=='practice'
  check(client.get('/teacher/prepare?mode=manual',headers=h),200)
  content='План урока\nПример <script>alert(1)</script>'
  r=client.post('/teacher/prepare/save',headers=h,data={'csrf':csrf,'content':content}); check(r,303); assert r.headers['location']=='/teacher/materials?saved=1'
  with db() as c: row=c.execute('SELECT * FROM teacher_materials WHERE user_id=%s',(u,)).fetchone()
  assert row['title']=='План урока' and row['content']==content
  identifier=row['id']
  r=client.get('/teacher/materials?q=Пример',headers=h); check(r,200); assert 'План урока' in r.text and '&lt;script&gt;' in r.text and '<script>alert(1)</script>' not in r.text
  check(client.get('/teacher/prepare?edit='+str(identifier),headers=h),200)
  check(client.get('/teacher/prepare?edit='+str(identifier),headers=h2),404)
  check(client.get(f'/teacher/materials/{identifier}/download',headers=h2),404)
  r=client.get(f'/teacher/materials/{identifier}/download',headers=h); check(r,200); assert r.text==row['title']+'\n\n'+content
  check(client.post('/teacher/prepare/save',headers=h2,data={'csrf':csrf2,'identifier':identifier,'content':' чужое'}),404)
  check(client.post('/teacher/prepare/save',headers=h,data={'csrf':csrf,'identifier':identifier,'title':'Обновлено','content':'Новый текст','subject':'Математика'}),303)
  with db() as c:
   rows=c.execute('SELECT * FROM teacher_materials WHERE user_id=%s',(u,)).fetchall(); assert len(rows)==1 and rows[0]['content']=='Новый текст'
  check(client.post('/teacher/prepare/save',headers=h,data={'csrf':csrf,'content':'x'*100001}),400)
  check(client.get('/teacher/materials?tab=courses',headers=h),200)
  print('PASS: save/edit/search/TXT, auto title, escaped text, validation, CSRF and private ownership')
finally:
 with db() as c:
  for u in ids: c.execute('DELETE FROM users WHERE id=%s',(u,))
