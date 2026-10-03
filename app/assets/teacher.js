'use strict';
for (const root of document.querySelectorAll('[data-transcript]')) {
  const audio = root.querySelector('[data-transcript-audio]');
  const status = root.querySelector('[data-play-status]');
  for (const tab of root.querySelectorAll('[data-model-tab]')) {
    tab.addEventListener('click', () => {
      for (const other of root.querySelectorAll('[data-model-tab]')) other.setAttribute('aria-selected', String(other === tab));
      for (const panel of root.querySelectorAll('[data-model-panel]')) panel.hidden = panel.dataset.modelPanel !== tab.dataset.modelTab;
    });
  }
  for (const button of root.querySelectorAll('[data-seek]')) {
    button.addEventListener('click', async () => {
      const seconds = Number(button.dataset.seek);
      if (!Number.isFinite(seconds) || seconds < 0) return;
      try {
        if (!audio.readyState) {
          audio.load();
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => { cleanup(); reject(new Error('timeout')); }, 15000);
            const ready = () => { cleanup(); resolve(); };
            const error = () => { cleanup(); reject(new Error('audio')); };
            const cleanup = () => { clearTimeout(timer); audio.removeEventListener('loadedmetadata', ready); audio.removeEventListener('error', error); };
            audio.addEventListener('loadedmetadata', ready, {once:true});
            audio.addEventListener('error', error, {once:true});
          });
        }
        audio.currentTime = Math.min(seconds, Number.isFinite(audio.duration) ? audio.duration : seconds);
        await audio.play();
        status.textContent = 'Слушаем запись с выбранного места.';
      } catch { status.textContent = 'Не удалось начать воспроизведение. Нажмите ▶ в плеере.'; }
    });
  }
}
