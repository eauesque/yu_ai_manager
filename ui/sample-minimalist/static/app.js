/* ========== MinUI — Sample Minimalist UI Logic ========== */
(function() {
  'use strict';

  /* ---------- API Helper ---------- */
  function apiFetch(url, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    if (opts.method && opts.method !== 'GET') {
      headers['X-Requested-With'] = 'XMLHttpRequest';
    }
    if (opts.body && typeof opts.body === 'object') {
      headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    opts.headers = headers;
    return fetch(url, opts).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  /* ---------- HTML Escape ---------- */
  var _esc = document.createElement('span');
  function esc(s) { _esc.textContent = s || ''; return _esc.innerHTML; }

  /* ---------- Dark Mode ---------- */
  function initTheme() {
    var stored = localStorage.getItem('minui-dark');
    if (stored === '1' || (stored === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.body.classList.add('dark');
    }
    var btn = document.getElementById('themeToggle');
    if (btn) {
      btn.textContent = document.body.classList.contains('dark') ? '\u2600' : '\u263D';
      btn.addEventListener('click', function() {
        document.body.classList.toggle('dark');
        var isDark = document.body.classList.contains('dark');
        localStorage.setItem('minui-dark', isDark ? '1' : '0');
        btn.textContent = isDark ? '\u2600' : '\u263D';
      });
    }
  }

  /* ---------- Navigation ---------- */
  function initNav() {
    var hamburger = document.getElementById('hamburger');
    var links = document.getElementById('navLinks');
    if (hamburger && links) {
      hamburger.addEventListener('click', function() {
        links.classList.toggle('open');
      });
    }
    var overBtn = document.getElementById('overflowBtn');
    var overMenu = document.getElementById('overflowMenu');
    if (overBtn && overMenu) {
      overBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        overMenu.classList.toggle('open');
      });
      document.addEventListener('click', function() {
        overMenu.classList.remove('open');
      });
    }
  }

  /* ---------- Toast ---------- */
  function toast(msg) {
    var el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(function() { el.classList.remove('show'); }, 2000);
  }

  /* ---------- Star Widget ---------- */
  function createStars(fileId, rating, large) {
    var wrap = document.createElement('div');
    wrap.className = 'stars' + (large ? ' stars-lg' : '');
    for (var i = 1; i <= 5; i++) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'star' + (i <= rating ? ' filled' : '');
      btn.textContent = '\u2605';
      btn.dataset.val = i;
      btn.dataset.fid = fileId;
      btn.addEventListener('click', onStarClick);
      wrap.appendChild(btn);
    }
    return wrap;
  }

  function onStarClick(e) {
    var btn = e.currentTarget;
    var fileId = parseInt(btn.dataset.fid);
    var val = parseInt(btn.dataset.val);
    var current = ratingsCache[fileId] || 0;
    var newVal = (val === current) ? 0 : val;
    apiFetch('/api/ratings/set', {
      method: 'POST',
      body: { file_id: fileId, rating: newVal }
    }).then(function(d) {
      ratingsCache[fileId] = d.rating;
      refreshStars(fileId, d.rating);
      toast(d.rating ? '\u2605 ' + d.rating : 'Rating cleared');
    }).catch(function() { toast('Error setting rating'); });
  }

  function refreshStars(fileId, rating) {
    document.querySelectorAll('.stars').forEach(function(wrap) {
      var btns = wrap.querySelectorAll('.star');
      if (btns.length && parseInt(btns[0].dataset.fid) === fileId) {
        btns.forEach(function(b) {
          b.classList.toggle('filled', parseInt(b.dataset.val) <= rating);
        });
      }
    });
  }

  /* ---------- Rating Batch ---------- */
  var ratingsCache = {};
  function fetchRatings(ids) {
    if (!ids.length) return Promise.resolve();
    return apiFetch('/api/ratings/batch', {
      method: 'POST',
      body: { file_ids: ids }
    }).then(function(d) {
      var map = d.ratings || {};
      Object.keys(map).forEach(function(k) { ratingsCache[parseInt(k)] = map[k]; });
    }).catch(function() {});
  }

  /* ---------- Search Page ---------- */
  var allResults = [];
  var searchState = { cursor: null, hasMore: false, query: '', sort: 'date' };

  function initSearch() {
    var input = document.getElementById('searchInput');
    var select = document.getElementById('sortSelect');
    var loadBtn = document.getElementById('loadMoreBtn');
    if (!input) return;

    var timer = null;
    input.addEventListener('input', function() {
      clearTimeout(timer);
      timer = setTimeout(function() { doSearch(true); }, 300);
    });
    select.addEventListener('change', function() { doSearch(true); });
    loadBtn.addEventListener('click', function() { doSearch(false); });
    doSearch(true);
  }

  function doSearch(reset) {
    var input = document.getElementById('searchInput');
    var select = document.getElementById('sortSelect');
    if (reset) {
      searchState.cursor = null;
      searchState.query = input.value.trim();
      searchState.sort = select.value;
      document.getElementById('grid').innerHTML = '';
      allResults = [];
    }
    var url = '/api/search?limit=50&sort=' + encodeURIComponent(searchState.sort);
    if (searchState.query) url += '&q=' + encodeURIComponent(searchState.query);
    if (searchState.cursor) url += '&cursor=' + encodeURIComponent(searchState.cursor);

    apiFetch(url).then(function(d) {
      searchState.cursor = d.next_cursor;
      searchState.hasMore = d.has_more;
      var count = document.getElementById('resultCount');
      if (reset) count.textContent = d.total_count + ' results';

      var ids = d.results.map(function(r) { return r.id; });
      fetchRatings(ids).then(function() { renderCards(d.results); });

      var wrap = document.getElementById('loadMoreWrap');
      wrap.style.display = d.has_more ? '' : 'none';
    }).catch(function() { toast('Search failed'); });
  }

  function renderCards(results) {
    var grid = document.getElementById('grid');
    var startIdx = allResults.length;
    allResults = allResults.concat(results);

    results.forEach(function(r, i) {
      var div = document.createElement('div');
      div.className = 'card';
      div.dataset.id = r.id;
      div.dataset.idx = startIdx + i;

      var img = document.createElement('img');
      img.className = 'card-thumb';
      img.loading = 'lazy';
      img.src = '/api/thumbnail/' + r.id;
      img.alt = '';
      div.appendChild(img);

      var body = document.createElement('div');
      body.className = 'card-body';
      var name = document.createElement('div');
      name.className = 'card-name';
      var parts = (r.path || '').replace(/\\/g, '/').split('/');
      name.textContent = parts[parts.length - 1] || '';
      body.appendChild(name);

      var starDiv = document.createElement('div');
      starDiv.className = 'card-stars';
      starDiv.appendChild(createStars(r.id, ratingsCache[r.id] || 0, false));
      body.appendChild(starDiv);
      div.appendChild(body);

      div.addEventListener('click', function(e) {
        if (e.target.closest('.star')) return;
        openLightbox(parseInt(div.dataset.idx));
      });
      grid.appendChild(div);
    });
    buildFilmstrip();
  }

  /* ---------- Lightbox ---------- */
  var lightboxState = { open: false, currentIdx: -1, slideshowTimer: null, slideshowActive: false };
  var zoomState = { zoomed: false, scale: 1, dragging: false, startX: 0, startY: 0, scrollX: 0, scrollY: 0 };
  var detailOpen = false;

  function initLightbox() {
    var lb = document.getElementById('lightbox');
    if (!lb) return;
    document.getElementById('lbClose').addEventListener('click', closeLightbox);
    document.getElementById('lbPrev').addEventListener('click', function() { navLightbox(-1); });
    document.getElementById('lbNext').addEventListener('click', function() { navLightbox(1); });
    document.getElementById('lbSlideshow').addEventListener('click', toggleSlideshow);
    var detailBtn = document.getElementById('lbDetail');
    if (detailBtn) detailBtn.addEventListener('click', toggleDetail);
    document.addEventListener('keydown', function(e) {
      if (!lightboxState.open) return;
      switch (e.key) {
        case 'Escape': closeLightbox(); break;
        case 'ArrowLeft': e.preventDefault(); navLightbox(-1); stopSlideshow(); break;
        case 'ArrowRight': e.preventDefault(); navLightbox(1); stopSlideshow(); break;
        case ' ': e.preventDefault(); toggleSlideshow(); break;
        case 'i': toggleDetail(); break;
      }
    });
    var stage = document.getElementById('lightboxStage');
    stage.addEventListener('click', function(e) {
      if (e.target === this && !zoomState.zoomed) closeLightbox();
    });
    initZoom();
  }

  function openLightbox(idx) {
    if (idx < 0 || idx >= allResults.length) return;
    document.getElementById('lightbox').setAttribute('aria-hidden', 'false');
    lightboxState.open = true;
    lightboxState.currentIdx = idx;
    document.body.style.overflow = 'hidden';
    showLightboxImage(idx);
  }

  function closeLightbox() {
    document.getElementById('lightbox').setAttribute('aria-hidden', 'true');
    lightboxState.open = false;
    document.body.style.overflow = '';
    stopSlideshow(); resetZoom();
    detailOpen = false;
    var dp = document.getElementById('lightboxDetail');
    if (dp) dp.style.display = 'none';
    var db = document.getElementById('lbDetail');
    if (db) db.classList.remove('active');
  }

  function navLightbox(dir) {
    var n = lightboxState.currentIdx + dir;
    if (n < 0) n = allResults.length - 1;
    if (n >= allResults.length) n = 0;
    lightboxState.currentIdx = n;
    resetZoom();
    showLightboxImage(n);
  }

  function showLightboxImage(idx) {
    var r = allResults[idx];
    if (!r) return;
    var img = document.getElementById('lightboxImg');
    img.classList.add('loading');
    img.src = '/api/thumbnail/' + r.id + '?w=1200';
    img.onload = function() { img.classList.remove('loading'); };
    var parts = (r.path || '').replace(/\\/g, '/').split('/');
    var info = document.getElementById('lightboxInfo');
    if (info) info.textContent = (idx + 1) + ' / ' + allResults.length + '  \u2014  ' + (parts[parts.length - 1] || '');
    var starsWrap = document.getElementById('lbStars');
    if (starsWrap) { starsWrap.innerHTML = ''; starsWrap.appendChild(createStars(r.id, ratingsCache[r.id] || 0, false)); }
    loadDetail(r.id);
    syncFilmstrip(idx);
  }

  function toggleDetail() {
    detailOpen = !detailOpen;
    var p = document.getElementById('lightboxDetail');
    if (p) p.style.display = detailOpen ? '' : 'none';
    var b = document.getElementById('lbDetail');
    if (b) b.classList.toggle('active', detailOpen);
  }

  function loadDetail(fileId) {
    // Reset all detail sections
    ['ldPromptSection','ldNegSection','ldParamsSection','ldTagsSection'].forEach(function(id) {
      var el = document.getElementById(id); if (el) el.style.display = 'none';
    });
    apiFetch('/api/file/' + fileId).then(function(d) {
      if (d.positive) { document.getElementById('ldPromptSection').style.display = ''; document.getElementById('ldPrompt').textContent = d.positive; }
      if (d.negative) { document.getElementById('ldNegSection').style.display = ''; document.getElementById('ldNeg').textContent = d.negative; }
      var params = [];
      if (d.steps) params.push('Steps: ' + d.steps);
      if (d.sampler) params.push('Sampler: ' + d.sampler);
      if (d.cfg_scale) params.push('CFG: ' + d.cfg_scale);
      if (d.seed) params.push('Seed: ' + d.seed);
      if (d.model) params.push('Model: ' + d.model);
      if (d.source) params.push('Source: ' + d.source);
      if (d.width && d.height) params.push('Size: ' + d.width + '\u00d7' + d.height);
      if (params.length) { document.getElementById('ldParamsSection').style.display = ''; document.getElementById('ldParams').textContent = params.join(' | '); }
      if (d.tags && d.tags.length) {
        document.getElementById('ldTagsSection').style.display = '';
        var div = document.getElementById('ldTags'); div.innerHTML = '';
        d.tags.forEach(function(t) { var p = document.createElement('span'); p.className = 'pill'; p.textContent = t.tag; div.appendChild(p); });
      }
    }).catch(function() {});
  }

  /* ---------- Slideshow ---------- */
  function toggleSlideshow() { if (lightboxState.slideshowActive) stopSlideshow(); else startSlideshow(); }
  function startSlideshow() {
    lightboxState.slideshowActive = true;
    var btn = document.getElementById('lbSlideshow');
    if (btn) { btn.classList.add('active'); btn.innerHTML = '&#10074;&#10074;'; btn.title = 'Pause'; }
    lightboxState.slideshowTimer = setInterval(function() { navLightbox(1); }, 3000);
  }
  function stopSlideshow() {
    lightboxState.slideshowActive = false;
    var btn = document.getElementById('lbSlideshow');
    if (btn) { btn.classList.remove('active'); btn.innerHTML = '&#9654;'; btn.title = 'Slideshow'; }
    if (lightboxState.slideshowTimer) { clearInterval(lightboxState.slideshowTimer); lightboxState.slideshowTimer = null; }
  }

  /* ---------- Filmstrip ---------- */
  function buildFilmstrip() {
    var strip = document.getElementById('filmstrip');
    if (!strip) return;
    strip.innerHTML = '';
    allResults.forEach(function(r, i) {
      var thumb = document.createElement('img');
      thumb.className = 'filmstrip-thumb';
      thumb.src = '/api/thumbnail/' + r.id;
      thumb.alt = '';
      thumb.dataset.idx = i;
      thumb.setAttribute('role', 'listitem');
      thumb.addEventListener('click', function() { lightboxState.currentIdx = i; showLightboxImage(i); stopSlideshow(); });
      strip.appendChild(thumb);
    });
  }

  function syncFilmstrip(idx) {
    var strip = document.getElementById('filmstrip');
    if (!strip) return;
    var thumbs = strip.querySelectorAll('.filmstrip-thumb');
    thumbs.forEach(function(t, i) { t.classList.toggle('active', i === idx); });
    if (thumbs[idx]) {
      var wrap = document.getElementById('filmstripWrap');
      wrap.scrollTo({ left: thumbs[idx].offsetLeft - wrap.offsetWidth / 2 + thumbs[idx].offsetWidth / 2, behavior: 'smooth' });
    }
  }

  /* ---------- Zoom ---------- */
  function initZoom() {
    var stage = document.getElementById('lightboxStage');
    if (!stage) return;
    stage.addEventListener('dblclick', function(e) {
      e.preventDefault();
      if (zoomState.zoomed) resetZoom(); else { zoomState.scale = 2; applyZoom(); }
    });
    stage.addEventListener('wheel', function(e) {
      if (!lightboxState.open) return;
      e.preventDefault();
      zoomState.scale = Math.max(0.5, Math.min(5, zoomState.scale + (e.deltaY > 0 ? -0.2 : 0.2)));
      applyZoom();
    }, { passive: false });
    stage.addEventListener('mousedown', function(e) {
      if (!zoomState.zoomed) return;
      zoomState.dragging = true; zoomState.startX = e.clientX; zoomState.startY = e.clientY;
      zoomState.scrollX = stage.scrollLeft; zoomState.scrollY = stage.scrollTop;
      stage.classList.add('dragging'); e.preventDefault();
    });
    document.addEventListener('mousemove', function(e) {
      if (!zoomState.dragging) return;
      var s = document.getElementById('lightboxStage');
      s.scrollLeft = zoomState.scrollX - (e.clientX - zoomState.startX);
      s.scrollTop = zoomState.scrollY - (e.clientY - zoomState.startY);
    });
    document.addEventListener('mouseup', function() {
      if (zoomState.dragging) { zoomState.dragging = false; document.getElementById('lightboxStage').classList.remove('dragging'); }
    });
  }

  function applyZoom() {
    var img = document.getElementById('lightboxImg');
    var stage = document.getElementById('lightboxStage');
    if (zoomState.scale <= 1.05) { resetZoom(); return; }
    zoomState.zoomed = true;
    img.classList.add('zoomed');
    img.style.transform = 'scale(' + zoomState.scale + ')';
    img.style.transformOrigin = 'center center';
    stage.classList.add('zoomed');
  }

  function resetZoom() {
    var img = document.getElementById('lightboxImg');
    var stage = document.getElementById('lightboxStage');
    if (!img || !stage) return;
    zoomState.zoomed = false; zoomState.scale = 1;
    img.classList.remove('zoomed'); img.style.transform = ''; img.style.transformOrigin = '';
    stage.classList.remove('zoomed');
  }

  /* ---------- Stats Page ---------- */
  function initStats() {
    apiFetch('/api/stats/all').then(function(d) {
      var b = d.basic || {};
      document.getElementById('statFiles').textContent = (b.file_count || 0).toLocaleString();
      document.getElementById('statTags').textContent = (b.tag_count || 0).toLocaleString();

      var src = b.sources || {};
      var srcArr = Object.keys(src).map(function(k) { return k + ': ' + src[k]; });
      document.getElementById('statSources').textContent = Object.keys(src).length;

      // Source detail in cards
      if (srcArr.length) {
        var cards = document.getElementById('statCards');
        var sc = document.createElement('div');
        sc.className = 'stat-card';
        sc.innerHTML = '<div class="stat-label" style="margin-bottom:8px">Source Breakdown</div>';
        srcArr.forEach(function(s) {
          var p = document.createElement('div');
          p.style.fontSize = '0.9rem';
          p.textContent = s;
          sc.appendChild(p);
        });
        cards.appendChild(sc);
      }

      // Timeline chart
      // timeline is [{period, count}, ...]
      var tl = Array.isArray(d.timeline) ? d.timeline : [];
      var labels = tl.map(function(r) { return r.period; });
      var values = tl.map(function(r) { return r.count; });
      if (labels.length && typeof Chart !== 'undefined') {
        var isDark = document.body.classList.contains('dark');
        new Chart(document.getElementById('timelineChart'), {
          type: 'bar',
          data: {
            labels: labels,
            datasets: [{ label: 'Files', data: values,
              backgroundColor: isDark ? 'rgba(139,156,247,0.6)' : 'rgba(102,126,234,0.6)',
              borderRadius: 4 }]
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              x: { grid: { display: false }, ticks: { color: isDark ? '#888' : '#666' } },
              y: { beginAtZero: true, ticks: { color: isDark ? '#888' : '#666' } }
            }
          }
        });
      }

      // Top tags
      var tags = b.top_tags || [];
      var tagsEl = document.getElementById('topTags');
      tags.forEach(function(t) {
        var pill = document.createElement('span');
        pill.className = 'pill';
        pill.textContent = t.tag + ' (' + t.count + ')';
        tagsEl.appendChild(pill);
      });
    }).catch(function() { toast('Failed to load stats'); });
  }

  /* ---------- Init ---------- */
  initTheme();
  initNav();
  initLightbox();

  /* ---------- Public API ---------- */
  window.MinUI = {
    initSearch: initSearch,
    initStats: initStats
  };
})();
