"""Repair word timestamps using saved ASR and speaker turns; preserve original."""
import json, os, subprocess, tempfile, time, sys
from pathlib import Path
import torch, whisperx, pandas as pd

torch.set_num_threads(2)
Path(os.environ.get('NLTK_DATA','/cache/nltk_data')).mkdir(parents=True,exist_ok=True)
src=Path('/output')/sys.argv[1]
report=json.loads(src.read_text())
recording=(Path('/data/audio')/report['recording']).resolve()
if not recording.is_relative_to(Path('/data/audio')): raise ValueError('Invalid recording path')
started=time.monotonic()
with tempfile.TemporaryDirectory() as td:
    wav=Path(td)/'excerpt.wav'
    subprocess.run(['ffmpeg','-v','error','-ss',str(report['excerpt_start_seconds']),'-i',str(recording),'-t',str(report['benchmark']['audio_seconds']),'-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],check=True)
    audio=whisperx.load_audio(str(wav))
    print('Loading alignment model...',flush=True)
    model,metadata=whisperx.load_align_model(language_code=report['language'],device='cpu',model_dir='/cache/alignment')
    print('Aligning saved text; no transcription or diarization rerun...',flush=True)
    result=whisperx.align(report['segments'],model,metadata,audio,'cpu',return_char_alignments=False)
    turns=pd.DataFrame(report['speaker_turns'])
    result=whisperx.assign_word_speakers(turns,result,fill_nearest=False)
    words=[w for s in result['segments'] for w in s.get('words',[])]
    timed=[w for w in words if 'start' in w and 'end' in w]
    if not timed: raise RuntimeError('No timed words; refusing success')
    report['segments']=result['segments']
    report['word_alignment_available']=True
    report['warnings']=[w for w in report['warnings'] if not w.startswith('Word alignment unavailable:')]
    report['warnings'].append('Test transcript: recognition and speaker labels require listening review.')
    report['realignment']={'source':src.name,'elapsed_seconds':time.monotonic()-started,'words':len(words),'timed_words':len(timed),'untimed_words':len(words)-len(timed),'reused_speaker_turns':True}
    dest=src.with_name(src.stem+'.aligned.json')
    def save(path,text):
        tmp=path.with_suffix('.part'); tmp.write_text(text); os.chmod(tmp,0o600)
        os.chown(tmp,int(os.environ['ASR_UID']),int(os.environ['ASR_GID'])); tmp.replace(path)
    save(dest,json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False,default=lambda x:x.item()))
    lines=['TEST TRANSCRIPT — NOT VERIFIED','Word times and speaker labels are estimates. [NO TIME] means unavailable.','']
    group=[]; speaker=None
    def flush():
        if group:
            valid=[w for w in group if 'start' in w and 'end' in w]
            stamp=f"{valid[0]['start']:.2f}–{valid[-1]['end']:.2f}" if valid else 'NO TIME'
            lines.append(f'[{stamp}] {speaker}: '+ ' '.join(w['word'] if 'start' in w else '[NO TIME] '+w['word'] for w in group))
    for w in words:
        current=w.get('speaker','UNKNOWN')
        if current!=speaker or len(group)>=35:
            flush(); group=[]; speaker=current
        group.append(w)
    flush()
    save(dest.with_suffix('.txt'),'\n'.join(lines)+'\n')
    print('DONE',dest.name,json.dumps(report['realignment']),flush=True)
    print('WORD_SPEAKERS',pd.Series([w.get('speaker','UNKNOWN') for w in words]).value_counts().to_dict(),flush=True)
