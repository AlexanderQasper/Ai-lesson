(() => {
 const form=document.getElementById('lesson-build-form'); if(!form) return;
 const byId=id=>document.getElementById(id);
 const list=byId('stage-list'),saveForm=byId('lesson-save-form');
 let data=null,selected='',drafts={};
 const outcomeDefaults={new:'Объяснить основную идею и выполнить короткое задание по теме',practice:'Самостоятельно применить изученный способ в задании по теме',review:'Восстановить ключевые идеи и выбрать способ решения задачи по теме',inquiry:'Обосновать ответ на исследовательский вопрос по теме',discussion:'Сформулировать вывод и подкрепить его основанием по теме',check:'Показать понимание в самостоятельном задании по теме'};
 function el(tag,text,cls){const n=document.createElement(tag); if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
 function stageValues(){return [...list.children].map(card=>({title:card.querySelector('[data-stage-title]').value,minutes:Number(card.querySelector('[data-stage-minutes]').value),notes:card.querySelector('textarea').value}));}
 function openingValue(){return document.querySelector('input[name="opening"]:checked')?.value||'';}
 function remember(){if(selected) drafts[selected]={stages:stageValues(),opening:openingValue(),outcome:byId('lesson-outcome').value};}
 function total(){
  const stages=stageValues(),sum=stages.reduce((a,s)=>a+s.minutes,0);
  const valid=stages.every(s=>Number.isInteger(s.minutes)&&s.minutes>=1&&s.minutes<=120&&s.title.trim())&&sum===data.minutes;
  byId('time-total').textContent='Всего '+(Number.isFinite(sum)?sum:'—')+' из '+data.minutes+' минут'+(valid?'':' — проверьте время и названия этапов');
  byId('time-total').classList.toggle('invalid',!valid);byId('save-plan').disabled=!valid;return valid;
 }
 function draw(key){
  remember();selected=key;const plan=data.plans[key],draft=drafts[key];
  [...byId('scheme-options').children].forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.scheme===key)));
  byId('scheme-caution').textContent=plan.caution;
  byId('lesson-outcome').value=draft?.outcome||(outcomeDefaults[key]+' «'+data.topic+'».');
  const openings=data.all_openings.filter(o=>o.goals.includes(key));
  byId('opening-list').replaceChildren();openings.forEach((o,i)=>{
   const label=el('label',undefined,'opening-option'),radio=el('input');radio.type='radio';radio.name='opening';radio.value=o.id;radio.checked=draft?draft.opening===o.id:i===0;
   const text=el('span');text.append(el('strong',o.title),el('span',o.text));label.append(radio,text);byId('opening-list').append(label);
  });
  list.replaceChildren();(draft?.stages||plan.stages.map(s=>({title:s.title,minutes:s.minutes,notes:s.activity+'\nПроверка: '+s.check}))).forEach((s,i)=>{
   const card=el('li',undefined,'card stage-card'),top=el('div',undefined,'stage-top');top.append(el('span',String(i+1),'stage-number'));
   const titleLabel=el('label','Этап '+(i+1)),title=el('input');title.dataset.stageTitle='';title.value=s.title;title.maxLength=160;title.setAttribute('aria-label','Название этапа '+(i+1));titleLabel.append(title);
   const minutesLabel=el('label','Минут'),minutes=el('input');minutes.type='number';minutes.min='1';minutes.max='120';minutes.value=s.minutes;minutes.dataset.stageMinutes='';minutes.setAttribute('aria-label','Время этапа '+(i+1));minutesLabel.append(minutes);top.append(titleLabel,minutesLabel);
   const notes=el('textarea');notes.rows=3;notes.maxLength=6000;notes.value=s.notes;notes.setAttribute('aria-label','Действия и проверка этапа '+(i+1));card.append(top,notes);list.append(card);
  });
  byId('source-list').replaceChildren();[...new Set([...plan.sources,'alignment'])].forEach(id=>{
   const s=data.sources[id],li=el('li'),a=el('a',s.title);a.href=s.url;a.target='_blank';a.rel='noopener noreferrer';li.append(a);byId('source-list').append(li);
  });total();
 }
 function textPlan(){
  const schema=data.plans[selected],open=data.all_openings.find(o=>o.id===openingValue());
  const lines=['Тема: '+data.topic,'Тип урока: '+schema.title,'Длительность: '+data.minutes+' минут'];
  const subject=byId('lesson-subject').value.trim(),grade=byId('lesson-grade').value.trim();
  if(subject)lines.push('Предмет: '+subject);if(grade)lines.push('Класс: '+grade);
  lines.push('Результат: '+byId('lesson-outcome').value.trim(),'','Начало: '+(open?open.title+' — '+open.text:'Уточните начало'),'', 'Этапы:');
  let start=0;stageValues().forEach((s,i)=>{lines.push((i+1)+'. '+s.title+' ('+start+'–'+(start+s.minutes)+' мин; '+s.minutes+' мин)',s.notes,'');start+=s.minutes;});
  lines.push('Методическая подсказка: '+schema.caution,'Схема и тайминг — редактируемые ориентиры, не норматив. Конкретное содержание выбирает учитель.','', 'Методическая основа:');
  [...new Set([...schema.sources,'alignment'])].forEach(id=>lines.push(data.sources[id].title+': '+data.sources[id].url));return lines.join('\n');
 }
 form.addEventListener('submit',async e=>{
  e.preventDefault();byId('builder-error').hidden=true;byId('build-button').disabled=true;byId('build-status').textContent='Подбираем схему…';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try{
   const response=await fetch(form.action,{method:'POST',body:new FormData(form),signal:controller.signal,credentials:'same-origin'});
   if(!response.ok){let message='Не удалось подобрать схему. Проверьте поля и повторите.';try{const error=await response.json();message=error.error||(typeof error.detail==='string'?error.detail:message);}catch{}throw Error(message);}
   const next=await response.json();data=next;selected='';drafts={};byId('result-topic').textContent='Тема: '+data.topic;
   byId('recommend-title').textContent=data.plans[data.recommended].title;byId('recommend-reason').textContent=data.reason;
   byId('scheme-options').replaceChildren();Object.entries(data.plans).forEach(([key,p])=>{const b=el('button',p.title,'secondary');b.type='button';b.dataset.scheme=key;b.setAttribute('aria-pressed','false');b.addEventListener('click',()=>draw(key));byId('scheme-options').append(b);});
   byId('builder-result').hidden=false;draw(data.recommended);byId('build-status').textContent='Схема готова. Выберите начало и уточните действия.';byId('builder-result').scrollIntoView({behavior:'smooth',block:'start'});
  }catch(error){byId('builder-error').textContent=error.name==='AbortError'?'Сервер не ответил вовремя. Попробуйте ещё раз.':error.message;byId('builder-error').hidden=false;byId('build-status').textContent='';}
  finally{clearTimeout(timer);byId('build-button').disabled=false;}
 });
 list.addEventListener('input',()=>{if(data)total();});
 byId('reset-timing').addEventListener('click',()=>{if(!data)return;[...list.children].forEach((card,i)=>{card.querySelector('[data-stage-minutes]').value=data.plans[selected].stages[i].minutes;});total();});
 saveForm.addEventListener('submit',e=>{
  if(!data||!total()){e.preventDefault();return;}
  if(!byId('lesson-outcome').value.trim()){e.preventDefault();byId('plan-status').textContent='Уточните результат урока.';byId('lesson-outcome').focus();return;}
  byId('plan-content').value=textPlan();byId('plan-title').value=data.topic;
  byId('plan-subject').value=byId('lesson-subject').value;byId('plan-grade').value=byId('lesson-grade').value;
  byId('save-plan').disabled=true;byId('save-plan').textContent='Сохраняем…';byId('plan-status').textContent='Сохраняем план';
 });
 byId('copy-plan').addEventListener('click',async()=>{if(!data||!total())return;try{await navigator.clipboard.writeText(textPlan());byId('plan-status').textContent='План скопирован.';}catch{byId('plan-status').textContent='Копирование недоступно. Сохраните план и скачайте TXT.';}});
})();
