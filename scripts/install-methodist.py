"""Apply narrow integration changes to the existing server project."""
from datetime import datetime
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parents[1]
backup=Path('/tmp/methodist-backup-'+datetime.now().strftime('%Y%m%d%H%M%S'))
backup.mkdir(mode=0o700)
for name in ['app/assistant.py','app/templates/assistant.html','app/templates/material-editor.html','.gitignore']:
    p=root/name
    if p.exists():
        dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
p=root/'app/assistant.py';s=p.read_text()
needle="    from app.teacher import auth\n"
assert needle in s
if 'install_methodist(app)' not in s:
    s=s.replace(needle,needle+"    from app.methodist_ai import install as install_methodist,enabled\n    install_methodist(app)\n",1)
needle="manual=bool(edit) or mode=='manual')"
if needle in s:
    s=s.replace(needle,"manual=bool(edit) or mode=='manual',ai_mode=mode in ('ai','review'),ai_review=mode=='review',ai_enabled=enabled(u))",1)
assert 'ai_mode=' in s
p.write_text(s)
p=root/'app/templates/assistant.html';s=p.read_text()
if 'methodist.html' not in s:
    assert '{% if manual %}' in s
    s=s.replace('{% if manual %}',"{% if ai_mode %}{% include 'methodist.html' %}{% elif manual %}",1)
if 'Составить с ИИ' not in s:
    target='<h1>'
    # Place the alternative actions after the builder heading, without changing navigation.
    start=s.find(target);end=s.find('</h1>',start)
    assert start>=0 and end>start
    s=s[:end+5]+'''<p><a href="/teacher/prepare?mode=ai">Составить с ИИ</a> · <a href="/teacher/prepare?mode=review">Проверить готовый материал</a></p>'''+s[end+5:]
p.write_text(s)
p=root/'app/templates/material-editor.html';s=p.read_text()
s=s.replace('Сейчас это ручной редактор; ИИ не подключён.','Проверку методиста можно открыть отдельно; исходник сохранится.')
if 'Проверить методистом' not in s:
    s+='''<p><a href="/teacher/prepare?mode=review{% if editing and editing.id %}&amp;edit={{editing.id}}{% endif %}">Проверить методистом →</a></p>'''
p.write_text(s)
p=root/'.gitignore';s=p.read_text() if p.exists() else ''
if '/library/methodist/' not in s: p.write_text(s.rstrip()+'\n/library/methodist/\n')
subprocess.run(['python3','-m','py_compile','app/assistant.py','app/methodist_ai.py'],cwd=root,check=True)
print('Methodist integration prepared. Backup:',backup)
