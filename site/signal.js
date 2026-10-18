/* The Signal: live trace (pen, tooltips, scroll highlight). No dependencies. */
(function () {
  var root = document.documentElement;

  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- pen that rides the line while it draws
  document.querySelectorAll('svg.trace').forEach(function (svg) {
    var line = svg.querySelector('.line');
    if (!line || reduce || !line.getTotalLength) return;
    var ns = 'http://www.w3.org/2000/svg';
    var pen = document.createElementNS(ns, 'circle');
    pen.setAttribute('r', svg.viewBox.baseVal.width > 600 ? 6 : 4);
    pen.setAttribute('class', 'pen');
    svg.appendChild(pen);
    var total = line.getTotalLength();
    var start = null;
    function frame(ts) {
      if (start === null) start = ts;
      var off = parseFloat(getComputedStyle(line).strokeDashoffset);
      if (isNaN(off)) off = 0;
      var prog = Math.min(Math.max(1 - off, 0), 1);
      var pt = line.getPointAtLength(prog * total);
      pen.setAttribute('cx', pt.x);
      pen.setAttribute('cy', pt.y);
      if (prog < 0.999 && ts - start < 4000) requestAnimationFrame(frame);
      else pen.classList.add('done');
    }
    requestAnimationFrame(frame);
  });

  // ---- tooltips on spikes
  document.querySelectorAll('.trace-box').forEach(function (box) {
    var tip = box.querySelector('.tip');
    if (!tip) return;
    function show(a) {
      var dot = a.querySelector('.pk');
      if (!dot) return;
      var r = dot.getBoundingClientRect(), b = box.getBoundingClientRect();
      tip.innerHTML = '';
      var l = document.createElement('span'); l.className = 'tip-l tip-' + (a.dataset.m || ''); l.textContent = a.dataset.l || '';
      var h = document.createElement('span'); h.className = 'tip-h'; h.textContent = a.dataset.h || '';
      tip.appendChild(l); tip.appendChild(h);
      tip.hidden = false;
      var x = r.left + r.width / 2 - b.left;
      var w = tip.offsetWidth;
      x = Math.max(w / 2, Math.min(b.width - w / 2, x));
      tip.style.left = x + 'px';
      tip.style.top = (r.top - b.top - 12) + 'px';
    }
    function hide() { tip.hidden = true; }
    box.querySelectorAll('.tk[data-h]').forEach(function (a) {
      a.addEventListener('pointerenter', function () { show(a); });
      a.addEventListener('focus', function () { show(a); });
      a.addEventListener('pointerleave', hide);
      a.addEventListener('blur', hide);
    });
  });

  // ---- slim trace pinned to the top once the big one scrolls away
  var bar = document.querySelector('.mini-bar'), big = document.querySelector('.trace-fig');
  if (bar && big && 'IntersectionObserver' in window) {
    new IntersectionObserver(function (en) {
      bar.classList.toggle('show', !en[0].isIntersecting && en[0].boundingClientRect.top < 0);
    }).observe(big);
  }

  // ---- light up the spike for the story on screen
  if ('IntersectionObserver' in window) {
    var marks = {};
    document.querySelectorAll('.tk[data-thread]').forEach(function (a) {
      (marks[a.dataset.thread] = marks[a.dataset.thread] || []).push(a);
    });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        (marks[en.target.id] || []).forEach(function (a) { a.classList.toggle('on', en.isIntersecting); });
      });
    }, { rootMargin: '-35% 0px -55% 0px' });
    document.querySelectorAll('article.story[id]').forEach(function (art) {
      if (marks[art.id]) io.observe(art);
    });
  }
})();
