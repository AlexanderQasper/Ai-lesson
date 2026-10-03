"""Import explicitly selected local benchmark reports into their owner's recording."""
import json,subprocess,sys
from pathlib import Path
reports=[]
for filename in sys.argv[1:]:
    r=json.loads(Path(filename).read_text())
    is_whisper=r.get('word_alignment_available',False)
    if is_whisper:
        segments=[]; group=[]; speaker=None
        def flush():
            if group: segments.append({'start':group[0]['start'],'end':group[-1]['end'],'speaker':speaker,'text':' '.join(w['word'] for w in group)})
        for segment in r['segments']:
            for w in segment.get('words',[]):
                if 'start' not in w or 'end' not in w: continue
                current=w.get('speaker','UNKNOWN')
                if current!=speaker or len(group)>=35 or (group and w['start']-group[-1]['end']>2):
                    flush(); group=[]; speaker=current
                group.append(w)
        flush(); model=r.get('display_model','Whisper small')
    else:
        segments=r['segments']; model='Parakeet v3'
    reports.append({'recording':r['recording'],'model':model,'payload':{'segments':segments,'audio_seconds':r.get('audio_seconds',r.get('benchmark',{}).get('audio_seconds',300)),'excerpt_start_seconds':r.get('excerpt_start_seconds',0),'draft':True}})
program="""
import json,sys
from uuid import UUID
from psycopg.types.json import Jsonb
from app.main import db
from app.uploads import ROOT
for report in json.load(sys.stdin):
    owner,filename=report['recording'].split('/')
    identifier=UUID(filename.removesuffix('.mp3')); owner=int(owner)
    with db() as c:
        row=c.execute('SELECT id,duration_seconds,trim_size FROM audio_recordings WHERE id=%s AND user_id=%s',(identifier,owner)).fetchone()
        if not row: raise ValueError('Recording ownership mismatch')
        if row['duration_seconds']<report['payload']['audio_seconds']: raise ValueError('Recording changed duration')
        path=ROOT/str(owner)/(str(identifier)+('.trim.mp3' if row['trim_size'] else '.mp3'))
        stat=path.stat()
        c.execute('INSERT INTO recording_transcripts(recording_id,model,payload,source_size,source_mtime) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(recording_id,model) DO UPDATE SET payload=excluded.payload,source_size=excluded.source_size,source_mtime=excluded.source_mtime',(identifier,report['model'],Jsonb(report['payload']),stat.st_size,stat.st_mtime_ns))
    print('IMPORTED',report['model'],len(report['payload']['segments']),'segments')
"""
subprocess.run(['docker','compose','exec','-T','backend','python','-c',program],input=json.dumps(reports).encode(),check=True)
