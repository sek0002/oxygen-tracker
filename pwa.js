let installPrompt;
const buttons = [...document.querySelectorAll('[data-install]')];
const dialog = document.getElementById('install-dialog');
const standalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
function updateButtons() { buttons.forEach(button => { button.hidden = standalone(); }); }
updateButtons();
window.addEventListener('beforeinstallprompt', event => {
  event.preventDefault();
  installPrompt = event;
  updateButtons();
});
window.addEventListener('appinstalled', () => {
  installPrompt = null;
  buttons.forEach(button => { button.hidden = true; });
  if (dialog.open) dialog.close();
});
for (const button of buttons) button.addEventListener('click', async () => {
  if (installPrompt) {
    const prompt = installPrompt;
    installPrompt = null;
    await prompt.prompt();
    await prompt.userChoice;
    return;
  }
  const ios = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  document.getElementById('install-help').textContent = !window.isSecureContext
    ? 'Open this app over HTTPS to install it.'
    : ios ? 'Share → Add to Home Screen → Open as Web App → Add.'
    : 'Browser menu → Install app. In Safari on Mac: File → Add to Dock.';
  dialog.showModal();
});
document.getElementById('close-install').onclick = () => dialog.close();
if ('serviceWorker' in navigator && window.isSecureContext) {
  navigator.serviceWorker.register('./sw.js').catch(() => {
    // Installation can still be supported by the browser without offline caching.
  });
}
