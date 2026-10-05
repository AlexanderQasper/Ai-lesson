"""Run manually in the server terminal. The API key is never echoed or logged."""
from getpass import getpass
import os
from pathlib import Path
import re
import subprocess

root=Path(__file__).resolve().parents[1]
key=getpass('Вставьте OpenAI API key (ввод скрыт): ').strip()
if not re.fullmatch(r'sk-[A-Za-z0-9_-]{20,}',key):
    raise SystemExit('Ключ выглядит неверно. Файл не изменён.')
path=root/'.env';lines=path.read_text().splitlines()
updates={'OPENAI_API_KEY':key,'AI_ALLOWED_USER_IDS':'1'}
if not any(line.startswith('OPENAI_METHODIST_MODEL=') and line.split('=',1)[1].strip() for line in lines):
    updates['OPENAI_METHODIST_MODEL']='gpt-5.4'
seen=set();output=[]
for line in lines:
    name=line.split('=',1)[0]
    if name in updates:
        if name not in seen: output.append(name+'='+updates[name]);seen.add(name)
    else: output.append(line)
output.extend(name+'='+value for name,value in updates.items() if name not in seen)
temporary=root/'.env.openai.pending'
fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream: stream.write('\n'.join(output)+'\n')
temporary.replace(path)
subprocess.run(['docker','compose','up','-d','--no-deps','backend'],cwd=root,check=True)
print('Ключ сохранён. Backend перезапущен. Обновите страницу методиста.')
