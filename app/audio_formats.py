import json, math, subprocess, os
from pathlib import Path
EXTENSIONS = {'.mp3','.m4a','.aac','.wav','.flac','.ogg','.opus','.webm'}
FORMATS = {'mp3','mov','mp4','m4a','3gp','3g2','mj2','aac','wav','flac','ogg','matroska','webm'}
MAX_DURATION = 3 * 60 * 60

def probe(path):
    result = subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration,format_name,bit_rate:stream=codec_type,codec_name,channels','-of','json',str(path)],capture_output=True,timeout=30,check=True)
    return json.loads(result.stdout)

def normalize(source, output, budget):
    try:
        info=probe(source)
        formats=set(info.get('format',{}).get('format_name','').split(','))
        streams=info.get('streams',[])
        audio=[s for s in streams if s.get('codec_type')=='audio']
        duration=float(info.get('format',{}).get('duration',0))
        if not formats.intersection(FORMATS) or len(audio)!=1 or audio[0].get('channels') not in (1,2):
            raise ValueError('Нужна запись с одной аудиодорожкой, моно или стерео.')
        if not math.isfinite(duration) or duration <= 0 or duration > MAX_DURATION:
            raise ValueError('Продолжительность записи должна быть от 1 секунды до 3 часов.')
        if duration*40000 + 65536 > budget:
            raise ValueError('После конвертации запись превысит лимит кабинета — 2 ГБ.')
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-xerror','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:a:0','-vn','-map_metadata','-1','-c:a','libmp3lame','-b:a','320k','-ar','48000','-threads','1','-fs',str(budget+1),'-f','mp3','-y',str(output)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=600,check=True)
        os.chmod(output,0o600)
        result=probe(output); saved=float(result.get('format',{}).get('duration',0)); size=output.stat().st_size
        if size>budget: raise ValueError('Запись превышает лимит кабинета — 2 ГБ.')
        if result.get('format',{}).get('format_name')!='mp3' or not math.isfinite(saved) or saved<=0 or abs(saved-duration)>max(1,duration*.005):
            raise ValueError('Не удалось полностью конвертировать запись. Исходный файл повреждён или не поддерживается.')
        if not any(s.get('codec_name')=='mp3' and s.get('channels')==audio[0]['channels'] for s in result.get('streams',[])):
            raise ValueError('Не удалось сохранить аудиоканалы.')
        return size,saved
    except (subprocess.SubprocessError,KeyError,TypeError,json.JSONDecodeError):
        raise ValueError('Не удалось прочитать или конвертировать аудио. Проверьте исходный файл.')
