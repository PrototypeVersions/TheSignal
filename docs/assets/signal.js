/* The Signal: region map selection. No dependencies. */
(function () {
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
