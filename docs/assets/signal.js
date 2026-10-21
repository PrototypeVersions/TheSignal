/* The Signal: site interactions. No dependencies. */
(function () {
  var path = window.location.pathname.replace(/\/+$/, '');
  if (path === '/TheSignal' || path === '/TheSignal/index.html') {
    var mast = document.querySelector('header.mast');
    if (mast && !document.getElementById('development-pause')) {
      var notice = document.createElement('div');
      notice.id = 'development-pause';
      notice.setAttribute('role', 'status');
      notice.textContent = 'Updates are currently paused for site development.';
      notice.style.cssText = 'box-sizing:border-box;max-width:1120px;margin:1.2rem auto 0;padding:.9rem 1.1rem;border:1px solid #c9975b;border-radius:6px;background:rgba(201,151,91,.12);color:#f4eadc;font-family:DM Sans,system-ui,sans-serif;font-size:.95rem;font-weight:600;letter-spacing:.01em;text-align:center;';
      mast.insertAdjacentElement('afterend', notice);
    }
  }

  var links = document.querySelectorAll('[data-region]');
  if (!links.length) return;
  function select(slug, reveal) {
    links.forEach(function (a) {
      var on = a.getAttribute('data-region') === slug;
      a.classList.toggle('on', on);
      if (on) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
    });
    document.querySelectorAll('[data-panel]').forEach(function (p) {
      p.hidden = p.getAttribute('data-panel') !== slug;
    });
    var panel = document.getElementById('region-panel-' + slug);
    if (reveal && panel && window.matchMedia('(max-width: 899px)').matches) {
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
  links.forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      select(a.getAttribute('data-region'), true);
    });
  });
  select(links[0].getAttribute('data-region'), false);
})();
