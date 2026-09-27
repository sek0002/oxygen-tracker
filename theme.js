(() => {
  const key = 'oxygen-theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference;
  try { preference = localStorage.getItem(key); } catch {}
  if (!['light', 'dark'].includes(preference)) preference = null;
  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').content = '#1424cc';
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      const dark = theme === 'dark';
      button.textContent = dark ? '☀' : '☾';
      button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
      button.title = dark ? 'Light mode' : 'Dark mode';
    });
  }
  const current = () => preference || (system.matches ? 'dark' : 'light');
  apply(current());
  document.addEventListener('DOMContentLoaded', () => {
    apply(current());
    document.querySelectorAll('[data-theme-toggle]').forEach(button => button.addEventListener('click', () => {
      preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem(key, preference); } catch {}
      apply(preference);
    }));
  });
  system.addEventListener('change', () => { if (!preference) apply(current()); });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    preference = ['light', 'dark'].includes(event.newValue) ? event.newValue : null;
    apply(current());
  });
})();
