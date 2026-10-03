"""ASR-only stronger Whisper baseline; reuse previously computed speaker turns."""
import json,os,resource,subprocess,tempfile,time
from pathlib import Path
from faster_whisper import WhisperModel
src=Path('/output/f7438000bf3b479387264d09ffaf5f0d.json'); r=json.loads(src.read_text())
source=(Path('/data/audio')/r['recording']).resolve(); assert source.is_relative_to(Path('/data/audio'))
started=time.monotonic()
print('Loading large-v3-turbo / CPU int8; first run downloads model...',flush=True)
model=WhisperModel('large-v3-turbo',device='cpu',compute_type='int8',cpu_threads=2,num_workers=1,download_root='/cache/whisper')
load=time.monotonic()-started; rows=[]; turns=r['speaker_turns']
with tempfile.TemporaryDirectory() as td:
    wav=str(Path(td)/'excerpt.wav')
    subprocess.run(['ffmpeg','-v','error','-ss',str(r['excerpt_start_seconds']),'-i',str(source),'-t','300','-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le',wav],check=True)
    t=time.monotonic()
    segments,info=model.transcribe(wav,language='en',beam_size=5,temperature=0,condition_on_previous_text=False,vad_filter=True,word_timestamps=True)
    for s in segments:
        words=[]
        for w in s.words or []:
            overlaps={}
            for turn in turns:
                overlap=max(0,min(w.end,turn['end'])-max(w.start,turn['start']))
                if overlap: overlaps[turn['speaker']]=overlaps.get(turn['speaker'],0)+overlap
            words.append({'start':w.start,'end':w.end,'word':w.word.strip(),'probability':w.probability,'speaker':max(overlaps,key=overlaps.get) if overlaps else 'UNKNOWN'})
        flags=[]
        if s.avg_logprob < -1: flags.append('low_log_probability')
        if s.no_speech_prob > .6: flags.append('high_no_speech_probability')
        if s.compression_ratio > 2.4: flags.append('repetition_signal')
        rows.append({'start':s.start,'end':s.end,'text':s.text,'words':words,'avg_logprob':s.avg_logprob,'no_speech_prob':s.no_speech_prob,'compression_ratio':s.compression_ratio,'review_flags':flags})
        print(f'Processed through {s.end:.1f}/300 seconds',flush=True)
    recognition=time.monotonic()-t
report={'schema_version':1,'model':'large-v3-turbo','display_model':'Whisper large-v3-turbo','recording':r['recording'],'excerpt_start_seconds':r['excerpt_start_seconds'],'language':'en','word_alignment_available':True,'word_timing_method':'model-native estimated timestamps','speaker_turns':turns,'segments':rows,'warnings':['Unverified draft. Native word times and reused speaker labels are estimates.','Probability and repetition signals are not accuracy guarantees. No LLM rewriting.'],'benchmark':{'elapsed_seconds':time.monotonic()-started,'audio_seconds':300,'model_loading_seconds':load,'transcription_seconds':recognition,'peak_memory_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'diarization_reused':True}}
p=src.with_name(src.stem+'.large-v3-turbo.json'); tmp=p.with_suffix('.part'); tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)); os.chmod(tmp,0o600); os.chown(tmp,int(os.environ['ASR_UID']),int(os.environ['ASR_GID'])); tmp.replace(p)
print('DONE',p.name,json.dumps(report['benchmark']),flush=True)
