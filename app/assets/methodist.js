(() => {
 const form=document.getElementById('methodist-form'); if(!form)return;
 const byId=id=>document.getElementById(id),run=byId('ai-run'),status=byId('ai-status');
 let busy=false,resultContext=null;
 const mode=()=>form.querySelector('input[name="mode"]:checked').value;
 function update(){const review=mode()==='review';byId('ai-material-field').hidden=!review;byId('ai-content').required=review;byId('ai-topic').required=!review;run.textContent=review?'Проверить материал':'Составить план с ИИ';}
 form.querySelectorAll('input[name="mode"]').forEach(input=>input.addEventListener('change',update));update();
 function reference(ids,sources){return ids.map(id=>{const s=sources.find(x=>x.id===id);return s?`${s.author}. ${s.title} (${s.year}). ${s.location}`:'';}).filter(Boolean).join('; ');}
 function render(data){
  const r=data.result,s=data.sources,lines=[r.summary];
  if(r.objective)lines.push('\nЦель: '+r.objective);
  let start=0;
  r.stages.forEach((stage,i)=>{lines.push(`\n${i+1}. ${stage.title} (${start}–${start+stage.minutes} мин)\nУчитель: ${stage.teacher_action}\nУченики: ${stage.student_action}\nПроверка понимания: ${stage.check}`);start+=stage.minutes;});
  if(r.suggestions.length)lines.push('\nПредложения методиста:');
  const kinds={error:'Ошибка',risk:'Возможное затруднение',option:'Необязательное улучшение'};
  r.suggestions.forEach((item,i)=>{lines.push(`\n${i+1}. ${kinds[item.kind]}: ${item.location}`);if(item.evidence_quote)lines.push('В материале: «'+item.evidence_quote+'»');lines.push(item.issue,'Почему: '+item.why,'Предлагаемая правка: '+item.fix,'Как проверить результат: '+item.success_check,'Основание: '+(reference(item.source_ids,s)||'Методическое суждение без подтверждения в переданных фрагментах.'));});
  if(r.limitations.length)lines.push('\nЧто учесть:\n'+r.limitations.map(x=>'• '+x).join('\n'));
  if(r.source_ids.length)lines.push('\nМетодическая основа:\n'+reference(r.source_ids,s));
  const prefix=data.mode==='review'?'Разбор: ':'';
  byId('ai-save-title').value=(prefix+r.title).slice(0,160);byId('ai-save-content').value=lines.join('\n');
  byId('ai-save-subject').value=resultContext.subject;byId('ai-save-grade').value=resultContext.grade;
  const sources=byId('ai-sources');sources.replaceChildren();
  s.forEach(source=>{const p=document.createElement('p');p.textContent=reference([source.id],s)+(source.extraction==='local-ocr'?' — распознанный скан':'');sources.append(p);});
  if(!s.length){const p=document.createElement('p');p.textContent='В этом ответе нет ссылок на подключённые фрагменты. Проверьте обоснование рекомендаций.';sources.append(p);}
  byId('ai-result-note').textContent='Модель: '+data.model+'. Сохранение создаст отдельный материал. Исходник не изменяется.';
  byId('ai-result').hidden=false;
 }
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;
  if(!form.reportValidity())return;
  if(!byId('ai-result').hidden&&!window.confirm('Новый запрос заменит текущий черновик. Продолжить?'))return;
  busy=true;run.disabled=true;byId('ai-error').hidden=true;status.textContent='Методист готовит ответ… Обычно это занимает до двух минут.';
  const fields=new FormData(form);resultContext={subject:fields.get('subject'),grade:fields.get('grade')};
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),125000);
  try{
   const response=await fetch(form.action,{method:'POST',body:fields,signal:controller.signal,headers:{Accept:'application/json'}});
   const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Не удалось выполнить запрос. Проверьте поля формы.');
   render(data);status.textContent='Готово. Проверьте черновик перед сохранением.';
  }catch(error){byId('ai-error').textContent=error.name==='AbortError'?'Время ожидания истекло. Ввод остался в форме. Запрос на сервере мог ещё выполняться.':error.message;byId('ai-error').hidden=false;status.textContent='';}
  finally{clearTimeout(timer);busy=false;run.disabled=false;}
 });
 byId('ai-copy').addEventListener('click',async()=>{try{await navigator.clipboard.writeText(byId('ai-save-title').value+'\n\n'+byId('ai-save-content').value);status.textContent='Скопировано';}catch{status.textContent='Выделите текст результата и скопируйте вручную.';}});
 byId('ai-save').addEventListener('submit',event=>{if(busy){event.preventDefault();return;}if(!event.currentTarget.reportValidity())return;const button=event.currentTarget.querySelector('button[type="submit"]');button.disabled=true;button.textContent='Сохраняю…';});
})();
