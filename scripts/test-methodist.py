"""Offline integration checks: fake API, no material/account changes."""
import copy
import json
import os
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app import main
from app import methodist_ai as m


class FakeRedis:
    count=0
    busy=False
    def set(self,*args,**kwargs): return not self.busy
    def incr(self,*args): self.count+=1;return self.count
    def expire(self,*args): pass
    def eval(self,*args): return 1


redis=FakeRedis(); variant='valid'; captured=[]
def fake_api(body):
    captured.append(body)
    data=json.loads(body['input'][0]['content']);fields=data['task']
    result={'title':'Дроби','objective':'Сложить две дроби','summary':'Черновик',
            'stages':[], 'suggestions':[],'limitations':[],
            'source_ids':[data['source_fragments'][0]['id']]}
    if fields['mode']=='generate':
        result['stages']=[{'title':title,'minutes':15,'teacher_action':'Показать пример',
                          'student_action':'Решить пример','check':'Объяснить решение'}
                         for title in ['Начало','Практика','Проверка']]
    if variant=='bad-reference': result['source_ids']=['invented:page:999']
    if variant=='bad-timing': result['stages'][0]['minutes']=10
    if variant=='bad-quote':
        result['suggestions']=[{'location':'Первый абзац','evidence_quote':'Такого текста нет',
                               'issue':'Проблема','why':'Основание','fix':'Правка','success_check':'Проверка',
                               'kind':'risk','source_ids':[]}]
    return result


fields={'csrf':'fixture','mode':'generate','topic':'Дроби','subject':'Математика','grade':'5 класс','minutes':'45'}
user={'id':1,'csrf':'fixture','name':'Fixture','email':'fixture@example.invalid'}
with patch.dict(os.environ,{'OPENAI_API_KEY':'','AI_ALLOWED_USER_IDS':'1'}), \
     patch.object(main,'current_user',return_value=user) as current, \
     patch.object(m.Redis,'from_url',return_value=redis), \
     patch.object(m,'openai_call',side_effect=fake_api), \
     TestClient(app,base_url='https://projector-school.info',follow_redirects=False) as client:
    current.return_value=None
    assert client.post('/teacher/prepare/ai',data=fields).status_code==401
    current.return_value=user
    assert client.post('/teacher/prepare/ai',data=fields|{'csrf':'bad'}).status_code==403
    assert client.post('/teacher/prepare/ai',data=fields).status_code==503
    assert not captured
    os.environ['OPENAI_API_KEY']='fixture-not-a-real-key'
    assert client.post('/teacher/prepare/ai',data=fields|{'grade':''}).status_code==400
    assert client.post('/teacher/prepare/ai',data=fields|{'minutes':'19'}).status_code==400
    assert client.post('/teacher/prepare/ai',data=fields|{'content':'a'*20001}).status_code==400
    response=client.post('/teacher/prepare/ai',data=fields)
    assert response.status_code==200,response.text
    assert response.json()['sources'] and all('text' not in s for s in response.json()['sources'])
    assert captured[-1]['store'] is False and captured[-1]['max_output_tokens']==6000
    assert 'Методист урока' in captured[-1]['instructions']
    for variant,task in [('bad-reference','generate'),('bad-timing','generate'),('bad-quote','review')]:
        redis.count=0
        assert client.post('/teacher/prepare/ai',data=fields|{'mode':task,'content':'Реальный материал'}).status_code==502
    variant='valid';redis.count=0
    for i in range(5): assert client.post('/teacher/prepare/ai',data=fields).status_code==200
    before=len(captured)
    assert client.post('/teacher/prepare/ai',data=fields).status_code==429
    assert len(captured)==before
    redis.busy=True
    assert client.post('/teacher/prepare/ai',data=fields).status_code==409
    redis.busy=False
    # The existing GET handler captures the real session reader, independently of
    # the patched POST authentication above. It must still require a real login.
    for mode in ['ai','review']:
        assert client.get('/teacher/prepare?mode='+mode).status_code==303
    assert client.get('/assets/editor/methodist/SKILL.md').status_code==404
    assert client.get('/data/methodist/chunks.jsonl').status_code==404
import httpx
from fastapi import HTTPException
with patch.dict(os.environ,{'OPENAI_API_KEY':'fixture-not-a-real-key'}), patch.object(m.httpx,'Client') as factory:
    post=factory.return_value.__enter__.return_value.post
    post.return_value=httpx.Response(200,json={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}]})
    assert m.openai_call({'model':'fixture'})=={'ok':True}
    for code,payload,expected in [(401,{},503),(429,{},503),(200,{'status':'incomplete'},502),
                                 (200,{'status':'completed','output':[{'type':'message','content':[{'type':'refusal'}]}]},422)]:
        post.return_value=httpx.Response(code,json=payload)
        try: m.openai_call({})
        except HTTPException as exc: assert exc.status_code==expected
        else: raise AssertionError('API error not handled')
print('PASS: auth/CSRF, key gate, grounded requests, no exposed books, citations/timing/quote checks, trial quota, API errors')
