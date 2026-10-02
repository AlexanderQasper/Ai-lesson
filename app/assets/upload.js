(() => {
const form = document.querySelector('[data-upload-form]');
if (!form) return;
const box = document.createElement('div');
box.hidden = true; box.setAttribute('role', 'status'); box.setAttribute('aria-live', 'polite');
const label = document.createElement('p'); label.className = 'small';
const bar = document.createElement('progress'); bar.max = 100; bar.value = 0;
bar.style.cssText = 'width:100%;height:16px;accent-color:#269faf';
box.append(label, bar); form.append(box);
let busy = false;
const mb = bytes => (bytes / 1048576).toFixed(1) + ' МБ';
form.addEventListener('submit', event => {
if (!form.checkValidity()) return;
event.preventDefault(); if (busy) return;
const file = form.querySelector('[name="audio"]').files[0];
if (!file) return;
box.hidden = false;
if (file.size > 250 * 1048576) { label.textContent = 'Файл больше 250 МБ. Выберите файл поменьше.'; bar.hidden = true; return; }
const data = new FormData(form);
const button = form.querySelector('[type="submit"]');
const controls = Array.from(form.querySelectorAll('input,button'));
const prior = controls.map(el => el.disabled);
busy = true; controls.forEach(el => el.disabled = true);
button.textContent = 'Загружаем…'; bar.hidden = false; bar.value = 0;
label.textContent = 'Начинаем загрузку: ' + file.name + ' · ' + mb(file.size);
const xhr = new XMLHttpRequest();
xhr.open('POST', form.action); xhr.timeout = 30 * 60 * 1000;
const unlock = message => { busy = false; controls.forEach((el,i) => el.disabled = prior[i]); button.textContent = 'Загрузить запись'; label.textContent = message; bar.hidden = true; };
xhr.upload.addEventListener('progress', event => {
if (!event.lengthComputable) { bar.removeAttribute('value'); label.textContent = 'Передаём файл на сервер…'; return; }
const percent = Math.min(100, Math.floor(event.loaded / event.total * 100));
bar.value = percent;
label.textContent = 'Загрузка ' + percent + '% · ' + mb(event.loaded) + ' из ' + mb(event.total);
});
xhr.upload.addEventListener('load', () => {
bar.removeAttribute('value'); button.textContent = 'Готовим MP3…';
label.textContent = 'Файл передан. Сервер проверяет аудио и конвертирует в MP3 320 кбит/с — дождитесь завершения.';
});
xhr.addEventListener('load', () => {
if (xhr.status >= 200 && xhr.status < 300) {
label.textContent = 'Готово. Открываем историю загрузок…';
window.location.assign(xhr.responseURL || '/account');
} else { let detail = ''; try { detail = new DOMParser().parseFromString(xhr.responseText, 'text/html').querySelector('.error')?.textContent?.trim() || ''; } catch (_) {} unlock(detail || (xhr.status === 413 ? 'Файл слишком большой. Допустимо до 250 МБ.' : 'Сервер не принял файл (код ' + xhr.status + '). Попробуйте ещё раз.')); }
});
xhr.addEventListener('error', () => unlock('Связь с сервером прервалась. Проверьте историю загрузок перед повторной отправкой.'));
xhr.addEventListener('timeout', () => unlock('Время ожидания истекло. Проверьте историю загрузок перед повторной отправкой.'));
xhr.send(data);
});
})();
