import WaveSurfer from '/assets/editor/vendor/wavesurfer.esm.js';
import Regions from '/assets/editor/vendor/regions.esm.js';
import Timeline from '/assets/editor/vendor/timeline.esm.js';
const format=t=>{const m=Math.floor(t/60);return m+':'+(t-m*60).toFixed(2).padStart(5,'0')};
document.querySelectorAll('[data-editor]').forEach(editor=>{
 const form=editor.querySelector('form'),status=editor.querySelector('[data-wave-status]'),play=editor.querySelector('[data-play]');
 let wave,region,loading=false,ready=false,preview=false,zoom=1;
 const duration=Number(editor.dataset.duration);
 function labels(){const a=Number(form.elements.start.value),z=Number(form.elements.end.value);editor.querySelector('[data-start-label]').textContent=format(a);editor.querySelector('[data-end-label]').textContent=format(z);editor.querySelector('[data-length-label]').textContent=format(z-a)}
 labels();
 const fit=()=>Math.max(.01,editor.querySelector('[data-wave]').clientWidth/duration);
 function setZoom(value){zoom=Math.max(1,Math.min(256,value));wave.zoom(fit()*zoom)}
 async function initialize(){
  if(loading||ready)return;loading=true;status.textContent='Готовим звуковую дорожку…';
  try{
   const response=await fetch(editor.dataset.waveform,{credentials:'same-origin'});if(!response.ok)throw new Error('waveform');
   const data=await response.json();const regions=Regions.create();
   wave=WaveSurfer.create({container:editor.querySelector('[data-wave]'),height:128,waveColor:'#a8cfd9',progressColor:'#269faf',cursorColor:'#163f8c',cursorWidth:2,normalize:true,barWidth:2,barGap:1,autoScroll:true,autoCenter:false,dragToSeek:true,plugins:[regions,Timeline.create({container:editor.querySelector('[data-timeline]'),height:22,style:{fontSize:'11px',color:'#647889'}})]});
   wave.on('error',()=>{status.textContent='Не удалось воспроизвести запись. Попробуйте обновить страницу.'});
   await wave.load(editor.dataset.source,data.peaks,data.duration);
   const media=wave.getMediaElement();
   if(media.readyState<1)await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('metadata')),30000);media.addEventListener('loadedmetadata',()=>{clearTimeout(timer);resolve()},{once:true});media.addEventListener('error',()=>{clearTimeout(timer);reject(new Error('audio'))},{once:true});media.load()});
   region=regions.addRegion({start:Number(form.elements.start.value),end:Number(form.elements.end.value),minLength:Math.min(1,duration),drag:false,resize:true,color:'rgba(61,185,202,.22)'});
   regions.on('region-updated',r=>{form.elements.start.value=r.start.toFixed(3);form.elements.end.value=r.end.toFixed(3);labels();preview=false;wave.pause()});
   regions.on('region-clicked',(_r,event)=>{event.stopPropagation();const rect=wave.getWrapper().getBoundingClientRect();wave.setTime(Math.max(0,Math.min(duration,(event.clientX-rect.left)/rect.width*duration)));preview=false});
   wave.on('timeupdate',t=>{editor.querySelector('[data-clock]').textContent=format(t);if(preview&&t>=region.end){wave.pause();preview=false}});
   wave.on('play',()=>play.textContent='Ⅱ Пауза');wave.on('pause',()=>play.textContent='▶ Слушать');
   play.addEventListener('click',()=>{preview=false;wave.playPause().catch(()=>{})});
   editor.querySelector('[data-preview]').addEventListener('click',()=>{preview=true;wave.setTime(region.start);wave.play().catch(()=>{preview=false})});
   editor.querySelectorAll('[data-zoom]').forEach(button=>button.addEventListener('click',()=>setZoom(button.dataset.zoom==='fit'?1:zoom*(button.dataset.zoom==='in'?2:.5))));
   requestAnimationFrame(()=>{const handles=wave.getWrapper().getRootNode().querySelectorAll('[part*="region-handle"]');
   handles?.forEach((handle,index)=>{handle.tabIndex=0;handle.setAttribute('role','slider');handle.setAttribute('aria-label',index===0?'Начало фрагмента':'Конец фрагмента');handle.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const step=(event.shiftKey?10:1)*(event.key==='ArrowLeft'?-1:1);region.setOptions(index===0?{start:Math.max(0,Math.min(region.end-1,region.start+step))}:{end:Math.min(duration,Math.max(region.start+1,region.end+step))});form.elements.start.value=region.start.toFixed(3);form.elements.end.value=region.end.toFixed(3);labels()})});});
   editor.querySelectorAll('button[disabled]').forEach(button=>button.disabled=false);ready=true;status.textContent='Выделенная область будет сохранена. Масштаб + поможет выбрать границы точнее.';
   form.addEventListener('submit',event=>{if(!window.confirm('Сохранить только выделенный фрагмент? Начало и конец за его пределами будут удалены без возможности восстановления.')){event.preventDefault();return}wave.pause();editor.querySelector('[data-save]').textContent='Сохраняем…';editor.querySelector('[data-save]').disabled=true});
  }catch(error){wave?.destroy();status.textContent='Не удалось построить дорожку. Закройте и откройте редактор для повторной попытки.'}finally{loading=false}
 }
 editor.addEventListener('toggle',()=>{if(editor.open)initialize();else wave?.pause()});if(editor.open)initialize();
});

document.querySelectorAll('.delete-recording').forEach(form=>form.addEventListener('submit',event=>{if(!window.confirm('Удалить запись навсегда? Аудиофайл исчезнет из кабинета, восстановить его нельзя.')){event.preventDefault();return}const button=form.querySelector('button');button.disabled=true;button.textContent='Удаляем…'}));
