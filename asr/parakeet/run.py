import json,os,subprocess,tempfile,time,resource,difflib
from pathlib import Path
from importlib.metadata import version
import onnx_asr
src=Path('/output/f7438000bf3b479387264d09ffaf5f0d.json')
r=json.loads(src.read_text()); source=(Path('/data/audio')/r['recording']).resolve()
assert source.is_relative_to(Path('/data/audio'))
t=time.monotonic()
print('Loading Parakeet v3 FP32 CPU; first run downloads model...',flush=True)
model=onnx_asr.load_model('nemo-parakeet-tdt-0.6b-v3','/cache/parakeet-v3',providers=['CPUExecutionProvider'])
load=time.monotonic()-t; segments=[]
with tempfile.TemporaryDirectory() as td:
    for offset in range(0,300,30):
        wav=str(Path(td)/'chunk.wav')
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(r['excerpt_start_seconds']+offset),'-i',str(source),'-t','30','-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le',wav],check=True)
        text=model.recognize(wav)
        if not isinstance(text,str): raise TypeError('Unexpected transcript result')
        segments.append({'start':offset,'end':offset+30,'text':text})
        print(f'Completed {len(segments)}/10 chunks',flush=True)
old=' '.join(s['text'].strip() for s in r['segments']); new=' '.join(s['text'].strip() for s in segments)
report={'model':'Parakeet v3 ONNX FP32 CPU','runtime_version':version('onnx-asr'),'recording':r['recording'],'excerpt_start_seconds':r['excerpt_start_seconds'],'audio_seconds':300,'segments':segments,'elapsed_seconds':time.monotonic()-t,'loading_seconds':load,'peak_memory_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'warnings':['Fixed 30s chunk boundaries may affect words. Chunk times are not word times.','Whisper small is unverified; differences are not accuracy scores.']}
base=src.stem+'.parakeet'
def save(suffix,text):
    p=Path('/output')/(base+suffix); temp=p.with_suffix(p.suffix+'.part'); temp.write_text(text); os.chmod(temp,0o600); os.chown(temp,int(os.environ['ASR_UID']),int(os.environ['ASR_GID'])); temp.replace(p)
save('.json',json.dumps(report,ensure_ascii=False,indent=2))
save('.txt','TEST — NOT VERIFIED\n'+'\n'.join(f"[{s['start']}–{s['end']}] {s['text']}" for s in segments))
a=old.split(); b=new.split(); differences=[]
for tag,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
    if tag!='equal': differences.append('WHISPER: '+' '.join(a[i:j])+'\nPARAKEET: '+' '.join(b[k:l]))
save('.comparison.txt','DIFFERENCES — NOT ACCURACY SCORES\n\n'+'\n\n'.join(differences))
print('DONE',base,'seconds',round(report['elapsed_seconds'],1),'peak MB',round(report['peak_memory_mb']),flush=True)
