import argparse,gc,json,math,os,resource,subprocess,tempfile,time
from pathlib import Path
from uuid import uuid4

def main():
    parser=argparse.ArgumentParser(description='Private CPU benchmark: WhisperX + pyannote')
    parser.add_argument('--recording',help='Relative to /data/audio: USER/UUID.mp3')
    parser.add_argument('--model',default='small',choices=['small','medium','large-v3','large-v3-turbo'])
    parser.add_argument('--language',default=None)
    parser.add_argument('--seconds',type=int,default=300)
    parser.add_argument('--start',type=float,default=0)
    args=parser.parse_args()
    if not 10<=args.seconds<=600 or not math.isfinite(args.start) or args.start<0: parser.error('Length 10–600 seconds; start >= 0')
    root=Path('/data/audio').resolve(); files=sorted(f for f in root.glob('*/*.mp3') if not f.name.endswith('.trim.mp3'))
    if args.recording:
        source=(root/args.recording).resolve()
        if not source.is_relative_to(root) or not source.is_file() or source.suffix!='.mp3': parser.error('Recording not found')
    else:
        if not files: parser.error('No uploaded recordings')
        for n,f in enumerate(files,1): print(f'{n}. {f.relative_to(root)} ({f.stat().st_size/1048576:.1f} MB)')
        try:
            selected=int(input('Recording number: ')); assert 1<=selected<=len(files); source=files[selected-1]
        except (ValueError,IndexError,AssertionError): parser.error('Invalid recording number')
    token=os.environ.get('HF_TOKEN','').strip()
    if not token: parser.error('HF_TOKEN missing; accept community-1 conditions first')
    import numpy as np
    import torch,whisperx
    torch.set_num_threads(2); started=time.monotonic(); stages={}; warnings=[]
    with tempfile.TemporaryDirectory() as tmp:
        wav=Path(tmp)/'excerpt.wav'
        print('Preparing audio excerpt; uploaded MP3 stays untouched.',flush=True)
        subprocess.run(['ffmpeg','-nostdin','-v','error','-ss',str(args.start),'-i',str(source),'-t',str(args.seconds),'-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le',str(wav)],check=True,timeout=120)
        audio=whisperx.load_audio(str(wav)); duration=len(audio)/16000
        if duration<1: raise ValueError('Selected excerpt contains no audio')
        rms=float(np.sqrt(np.mean(audio.astype(np.float64)**2)))
        quiet=[float(np.sqrt(np.mean(chunk.astype(np.float64)**2)))<.01 for chunk in np.array_split(audio,max(1,int(duration)))]
        technical={'duration_seconds':duration,'rms_dbfs':20*math.log10(max(rms,1e-12)),'near_full_scale_fraction':float(np.mean(np.abs(audio)>=.999)),'quiet_window_fraction':sum(quiet)/len(quiet),'note':'Amplitude indicators on temporary mono 16 kHz audio, not ASR accuracy or perceptual quality.'}
        print('Loading WhisperX; first run downloads models.',flush=True); t=time.monotonic()
        model=whisperx.load_model(args.model,'cpu',compute_type='int8',language=args.language,vad_method='silero',threads=2,download_root='/cache/whisper')
        result=model.transcribe(audio,batch_size=1); stages['transcription_seconds']=time.monotonic()-t
        del model; gc.collect(); language=result['language']; aligned=False
        print('Aligning words…',flush=True); t=time.monotonic()
        try:
            align,metadata=whisperx.load_align_model(language_code=language,device='cpu',model_dir='/cache/alignment')
            result=whisperx.align(result['segments'],align,metadata,audio,'cpu',return_char_alignments=False)
            del align; gc.collect(); aligned=True
        except Exception as exc:
            warnings.append('Word alignment unavailable: '+type(exc).__name__)
            print('Alignment unavailable; keeping segment timestamps.',flush=True)
        stages['alignment_seconds']=time.monotonic()-t
        print('Separating speakers…',flush=True); t=time.monotonic()
        from whisperx.diarize import DiarizationPipeline
        diarizer=DiarizationPipeline(model_name='pyannote/speaker-diarization-community-1',token=token,device='cpu')
        turns=diarizer(audio); result=whisperx.assign_word_speakers(turns,result)
        speakers=[{'start':float(row.start),'end':float(row.end),'speaker':str(row.speaker)} for row in turns.itertuples()]
        stages['diarization_seconds']=time.monotonic()-t
        elapsed=time.monotonic()-started; output=Path('/output')/(uuid4().hex+'.json'); temp=output.with_suffix('.part')
        report={'schema_version':1,'recording':str(source.relative_to(root)),'excerpt_start_seconds':args.start,'timestamps_relative_to':'excerpt','language':language,'model':args.model,'engine':'WhisperX 3.8.6 / CPU int8','word_alignment_available':aligned,'diarization_available':True,'segments':result['segments'],'speaker_turns':speakers,'technical_audio':technical,'warnings':warnings,'benchmark':{'elapsed_seconds':elapsed,'audio_seconds':duration,'processing_seconds_per_audio_second':elapsed/duration,'peak_memory_mb':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'stages':stages,'includes_model_loading_and_possible_downloads':True}}
        temp.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False,default=lambda x:x.item()))
        os.chmod(temp,0o600); os.chown(temp,int(os.environ['ASR_UID']),int(os.environ['ASR_GID'])); temp.replace(output)
        print('DONE:',output,flush=True); print(f'Elapsed {elapsed:.1f}s; peak RAM {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB',flush=True)
if __name__=='__main__': main()
