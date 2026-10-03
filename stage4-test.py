import os,tempfile,subprocess,secrets,shutil
from pathlib import Path
from unittest.mock import patch
os.environ['MATERIALS_DIR']=tempfile.mkdtemp(prefix='upload-test-')
from app.main import app,db
from app import uploads
from fastapi.testclient import TestClient
ids=[]
try:
 with TestClient(app,base_url='https://projector-school.info',follow_redirects=False) as c:
  with db() as conn:
   for n in [1,2]:
    ids.append(conn.execute('INSERT INTO users(google_sub,email,name) VALUES(%s,%s,%s) RETURNING id',('upload-test-'+secrets.token_hex(12),'test@example.invalid','Test')).fetchone()['id'])
  users=[dict(id=i,name='Test',email='test@example.invalid',csrf='csrf') for i in ids]
  file=Path(os.environ['MATERIALS_DIR'])/'test.mp3'
  subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=440:duration=4','-c:a','libmp3lame',str(file)],check=True)
  audio=file.read_bytes()
  def post(data=audio,name='lesson.mp3',csrf='csrf'):
   return c.post('/recordings',data={'csrf':csrf,'title':'<script>Test</script>'},files={'audio':(name,data,'audio/mpeg')})
  with patch('app.main.current_user',return_value=users[0]):
   assert post(csrf='wrong').status_code==403
   assert post(name='lesson.wav').status_code==400
   assert post(data=b'not audio').status_code==400
   assert post(data=b'').status_code==400
   with patch('app.uploads.QUOTA',1): assert post().status_code==400
   assert not list(uploads.ROOT.rglob('*.part'))
   r=post(); assert r.status_code==303,r.text
   with db() as conn: row=conn.execute('SELECT * FROM audio_recordings WHERE user_id=%s',(ids[0],)).fetchone()
   assert row['duration_seconds']>0
   url='/recordings/'+str(row['id'])+'/download'
   assert c.get(url).content==audio
   assert '&lt;script&gt;Test&lt;/script&gt;' in c.get('/account').text
   media='/recordings/'+str(row['id'])+'/audio'
   edit='/recordings/'+str(row['id'])+'/trim'
   def cut(start='0:01',end='0:03',csrf='csrf',mode='trim'):
    return c.post(edit,data=dict(start=start,end=end,csrf=csrf,mode=mode))
   wave=c.get('/recordings/'+str(row['id'])+'/waveform'); assert wave.status_code==200,wave.text
   assert wave.json()['duration']>3 and len(wave.json()['peaks'][0])>0
   assert c.get('/recordings/'+str(row['id'])+'/waveform').json()==wave.json()
   assert 'data-waveform' in c.get('/account').text
   assert c.get(media).content==audio
   r=c.get(media,headers={'range':'bytes=0-31'}); assert r.status_code==206 and r.content==audio[:32]
   assert cut(csrf='wrong').status_code==403
   assert cut(start='NaN').status_code==400
   assert cut(start='0:03',end='0:01').status_code==400
   assert cut(end='1:00').status_code==400
   assert cut().status_code==303
   segment=c.get(media).content; assert segment and segment!=audio
   assert c.get(media+'?original=true').content==audio
   assert c.get(url).content==segment
   with db() as conn:
    saved=conn.execute('SELECT * FROM audio_recordings WHERE id=%s',(row['id'],)).fetchone()
   assert saved['trim_start']==1 and saved['trim_end']==3
   cropped=file.parent/'cropped.mp3'; cropped.write_bytes(segment)
   import json
   probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(cropped)],capture_output=True,check=True)
   assert 1.8<float(json.loads(probe.stdout)['format']['duration'])<2.2
   assert cut(start='0:00.5',end='0:02').status_code==303
   assert cut(mode='restore').status_code==303
   assert c.get(media).content==audio and c.get(url).content==audio
  with patch('app.main.current_user',return_value=users[1]):
   assert c.get(url).status_code==404
   assert c.get(media).status_code==404
   assert c.get('/recordings/'+str(row['id'])+'/waveform').status_code==404
   assert c.post(edit,data=dict(csrf='csrf',start='0',end='2')).status_code==404
   assert 'lesson.mp3' not in c.get('/account').text
  with patch('app.main.current_user',return_value=None):
   assert c.get(url).status_code==303
   assert post().status_code==303
  assert c.post('/recordings',content=b'x',headers={'content-length':str(uploads.MAX_REQUEST+1)}).status_code==413
  print('PASS: waveform + cache + ownership + upload + audio/range, trimming/retrim/restore, source preservation, duration, invalid boundaries, owner isolation, CSRF')
finally:
 with db() as conn:
  for uid in ids: conn.execute('DELETE FROM users WHERE id=%s',(uid,))
 shutil.rmtree(os.environ['MATERIALS_DIR'])
