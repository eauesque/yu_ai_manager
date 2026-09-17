/* ========== DashUI — Sample Dashboard UI Logic ========== */
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
    var stored = localStorage.getItem('dashui-dark');
    if (stored === '1' || (stored === null && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.body.classList.add('dark');
    }
    updateThemeButton();
    var btn = document.getElementById('themeToggle');
    if (btn) {
      btn.addEventListener('click', function() {
        document.body.classList.toggle('dark');
        var isDark = document.body.classList.contains('dark');
        localStorage.setItem('dashui-dark', isDark ? '1' : '0');
        updateThemeButton();
      });
    }
  }

  function updateThemeButton() {
    var isDark = document.body.classList.contains('dark');
    var icon = document.getElementById('themeIcon');
    var label = document.getElementById('themeLabel');
    if (icon) icon.textContent = isDark ? '\u2600' : '\u263D';
    if (label) label.textContent = isDark ? 'Light Mode' : 'Dark Mode';
  }

  /* ---------- Sidebar Navigation ---------- */
  function initSidebar() {
    var hamburger = document.getElementById('hamburger');
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    var closeBtn = document.getElementById('sidebarClose');

    function openSidebar() {
      if (sidebar) sidebar.classList.add('open');
      if (overlay) overlay.classList.add('open');
    }
    function closeSidebar() {
      if (sidebar) sidebar.classList.remove('open');
      if (overlay) overlay.classList.remove('open');
    }

    if (hamburger) hamburger.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (overlay) overlay.addEventListener('click', closeSidebar);
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
      btn.setAttribute('aria-label', 'Rate ' + i + ' star' + (i > 1 ? 's' : ''));
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

  /* ---------- Lightbox State ---------- */
  var allResults = [];
  var lightboxState = {
    open: false,
    currentIdx: -1,
    slideshowTimer: null,
    slideshowActive: false
  };
  var zoomState = { zoomed: false, scale: 1, dragging: false, startX: 0, startY: 0, scrollX: 0, scrollY: 0 };
  var detailOpen = false;

  /* ---------- Lightbox Init ---------- */
  function initLightbox() {
    var lb = document.getElementById('lightbox');
    if (!lb) return;

    document.getElementById('lbClose').addEventListener('click', closeLightbox);
    document.getElementById('lbPrev').addEventListener('click', function() { navLightbox(-1); });
    document.getElementById('lbNext').addEventListener('click', function() { navLightbox(1); });
    document.getElementById('lbSlideshow').addEventListener('click', toggleSlideshow);
    var detailBtn = document.getElementById('lbDetail');
    if (detailBtn) detailBtn.addEventListener('click', toggleDetail);

    // Keyboard shortcuts
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

    // Click stage background to close (not when zoomed)
    var stage = document.getElementById('lightboxStage');
    stage.addEventListener('click', function(e) {
      if (e.target === this && !zoomState.zoomed) closeLightbox();
    });

    initZoom();
  }

  function openLightbox(idx) {
    if (idx < 0 || idx >= allResults.length) return;
    var lb = document.getElementById('lightbox');
    lb.setAttribute('aria-hidden', 'false');
    lightboxState.open = true;
    lightboxState.currentIdx = idx;
    document.body.style.overflow = 'hidden';
    showLightboxImage(idx);
  }

  function closeLightbox() {
    var lb = document.getElementById('lightbox');
    lb.setAttribute('aria-hidden', 'true');
    lightboxState.open = false;
    document.body.style.overflow = '';
    stopSlideshow();
    resetZoom();
    detailOpen = false;
    var dp = document.getElementById('lightboxDetail');
    if (dp) dp.style.display = 'none';
    var db = document.getElementById('lbDetail');
    if (db) db.classList.remove('active');
  }

  function navLightbox(dir) {
    var newIdx = lightboxState.currentIdx + dir;
    if (newIdx < 0) newIdx = allResults.length - 1;
    if (newIdx >= allResults.length) newIdx = 0;
    lightboxState.currentIdx = newIdx;
    resetZoom();
    showLightboxImage(newIdx);
  }

  function showLightboxImage(idx) {
    var r = allResults[idx];
    if (!r) return;

    var img = document.getElementById('lightboxImg');
    img.classList.add('loading');
    img.src = '/api/thumbnail/' + r.id + '?w=1200';
    img.onload = function() { img.classList.remove('loading'); };

    // Info bar
    var parts = (r.path || '').replace(/\\/g, '/').split('/');
    var info = document.getElementById('lightboxInfo');
    if (info) info.textContent = (idx + 1) + ' / ' + allResults.length + '  \u2014  ' + (parts[parts.length - 1] || '');

    // Stars
    var starsWrap = document.getElementById('lbStars');
    if (starsWrap) {
      starsWrap.innerHTML = '';
      starsWrap.appendChild(createStars(r.id, ratingsCache[r.id] || 0, false));
    }

    // Load detail metadata
    loadDetail(r.id);

    // Sync filmstrip highlight
    syncFilmstrip(idx);
  }

  /* ---------- Detail Panel ---------- */
  function toggleDetail() {
    detailOpen = !detailOpen;
    var panel = document.getElementById('lightboxDetail');
    if (panel) panel.style.display = detailOpen ? '' : 'none';
    var btn = document.getElementById('lbDetail');
    if (btn) btn.classList.toggle('active', detailOpen);
  }

  function loadDetail(fileId) {
    ['ldPromptSection','ldNegSection','ldParamsSection','ldTagsSection'].forEach(function(id) {
      var el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });

    apiFetch('/api/file/' + fileId).then(function(d) {
      if (d.positive) {
        document.getElementById('ldPromptSection').style.display = '';
        document.getElementById('ldPrompt').textContent = d.positive;
      }
      if (d.negative) {
        document.getElementById('ldNegSection').style.display = '';
        document.getElementById('ldNeg').textContent = d.negative;
      }
      var params = [];
      if (d.steps) params.push('Steps: ' + d.steps);
      if (d.sampler) params.push('Sampler: ' + d.sampler);
      if (d.cfg_scale) params.push('CFG: ' + d.cfg_scale);
      if (d.seed) params.push('Seed: ' + d.seed);
      if (d.model) params.push('Model: ' + d.model);
      if (d.source) params.push('Source: ' + d.source);
      if (d.width && d.height) params.push('Size: ' + d.width + '\u00d7' + d.height);
      if (params.length) {
        document.getElementById('ldParamsSection').style.display = '';
        document.getElementById('ldParams').textContent = params.join(' | ');
      }
      if (d.tags && d.tags.length) {
        document.getElementById('ldTagsSection').style.display = '';
        var tagsDiv = document.getElementById('ldTags');
        tagsDiv.innerHTML = '';
        d.tags.forEach(function(t) {
          var pill = document.createElement('span');
          pill.className = 'pill';
          pill.textContent = t.tag;
          tagsDiv.appendChild(pill);
        });
      }
    }).catch(function() {});
  }

  /* ---------- Slideshow ---------- */
  function toggleSlideshow() {
    if (lightboxState.slideshowActive) { stopSlideshow(); } else { startSlideshow(); }
  }

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
      thumb.addEventListener('click', function() {
        lightboxState.currentIdx = i;
        showLightboxImage(i);
        stopSlideshow();
      });
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
      var scrollTo = thumbs[idx].offsetLeft - (wrap.offsetWidth / 2) + (thumbs[idx].offsetWidth / 2);
      wrap.scrollTo({ left: scrollTo, behavior: 'smooth' });
    }
  }

  /* ---------- Zoom ---------- */
  function initZoom() {
    var stage = document.getElementById('lightboxStage');
    if (!stage) return;

    // Double-click to toggle zoom
    stage.addEventListener('dblclick', function(e) {
      e.preventDefault();
      if (zoomState.zoomed) { resetZoom(); } else { zoomState.scale = 2; applyZoom(); }
    });

    // Mouse wheel to adjust zoom level
    stage.addEventListener('wheel', function(e) {
      if (!lightboxState.open) return;
      e.preventDefault();
      zoomState.scale = Math.max(0.5, Math.min(5, zoomState.scale + (e.deltaY > 0 ? -0.2 : 0.2)));
      applyZoom();
    }, { passive: false });

    // Drag to pan when zoomed
    stage.addEventListener('mousedown', function(e) {
      if (!zoomState.zoomed) return;
      zoomState.dragging = true;
      zoomState.startX = e.clientX;
      zoomState.startY = e.clientY;
      zoomState.scrollX = stage.scrollLeft;
      zoomState.scrollY = stage.scrollTop;
      stage.classList.add('dragging');
      e.preventDefault();
    });

    document.addEventListener('mousemove', function(e) {
      if (!zoomState.dragging) return;
      var stageEl = document.getElementById('lightboxStage');
      stageEl.scrollLeft = zoomState.scrollX - (e.clientX - zoomState.startX);
      stageEl.scrollTop = zoomState.scrollY - (e.clientY - zoomState.startY);
    });

    document.addEventListener('mouseup', function() {
      if (zoomState.dragging) {
        zoomState.dragging = false;
        var stageEl = document.getElementById('lightboxStage');
        stageEl.classList.remove('dragging');
      }
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
    zoomState.zoomed = false;
    zoomState.scale = 1;
    img.classList.remove('zoomed');
    img.style.transform = '';
    img.style.transformOrigin = '';
    stage.classList.remove('zoomed');
  }

  /* ---------- Dashboard Page ---------- */
  function initDashboard() {
    // Quick search redirect
    var searchInput = document.getElementById('dashSearchInput');
    var searchBtn = document.getElementById('dashSearchBtn');
    function doQuickSearch() {
      var q = (searchInput && searchInput.value.trim()) || '';
      window.location.href = '/search' + (q ? '?q=' + encodeURIComponent(q) : '');
    }
    if (searchBtn) searchBtn.addEventListener('click', doQuickSearch);
    if (searchInput) searchInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') doQuickSearch();
    });

    // Load stats
    apiFetch('/api/stats/all').then(function(d) {
      var b = d.basic || {};
      var el;

      el = document.getElementById('statFiles');
      if (el) el.textContent = (b.file_count || 0).toLocaleString();
      el = document.getElementById('statTags');
      if (el) el.textContent = (b.tag_count || 0).toLocaleString();

      var src = b.sources || {};
      var srcKeys = Object.keys(src);
      el = document.getElementById('statSources');
      if (el) el.textContent = srcKeys.length;

      // Rated count + distribution from /api/ratings/stats
      var rc = {};
      apiFetch('/api/ratings/stats').then(function(rd) {
        rc = rd.distribution || {};
        var totalRated = 0;
        Object.keys(rc).forEach(function(k) { if (parseInt(k) > 0) totalRated += rc[k]; });
        el = document.getElementById('statRated');
        if (el) el.textContent = totalRated.toLocaleString();
        // Render rating bars once data is available
        renderRatingBars(rc);
      }).catch(function() {});

      // Source breakdown chart (doughnut)
      if (srcKeys.length && typeof Chart !== 'undefined') {
        var sourceColors = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#06b6d4', '#84cc16'];
        var srcValues = srcKeys.map(function(k) { return src[k]; });
        new Chart(document.getElementById('sourceChart'), {
          type: 'doughnut',
          data: {
            labels: srcKeys,
            datasets: [{
              data: srcValues,
              backgroundColor: sourceColors.slice(0, srcKeys.length),
              borderWidth: 0
            }]
          },
          options: {
            responsive: true,
            cutout: '65%',
            plugins: {
              legend: { display: false }
            }
          }
        });

        // Source list below chart
        var listEl = document.getElementById('sourceList');
        if (listEl) {
          srcKeys.forEach(function(k, i) {
            var item = document.createElement('div');
            item.className = 'dash-source-item';
            item.innerHTML = '<span class="dash-source-name">' +
              '<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:' +
              sourceColors[i % sourceColors.length] + ';margin-right:8px;vertical-align:middle;"></span>' +
              esc(k) + '</span><span class="dash-source-count">' + src[k].toLocaleString() + '</span>';
            listEl.appendChild(item);
          });
        }
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
            datasets: [{
              label: 'Files',
              data: values,
              backgroundColor: isDark ? 'rgba(96,165,250,0.5)' : 'rgba(59,130,246,0.5)',
              borderColor: isDark ? '#60a5fa' : '#3b82f6',
              borderWidth: 1,
              borderRadius: 4
            }]
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              x: {
                grid: { display: false },
                ticks: { color: isDark ? '#64748b' : '#94a3b8', font: { size: 11 } }
              },
              y: {
                beginAtZero: true,
                ticks: { color: isDark ? '#64748b' : '#94a3b8', font: { size: 11 } },
                grid: { color: isDark ? 'rgba(51,65,85,0.5)' : 'rgba(226,232,240,0.8)' }
              }
            }
          }
        });
      }

      // Rating distribution bars (rendered after async fetch)
      function renderRatingBars(rc) {
        var barsEl = document.getElementById('ratingBars');
        if (!barsEl) return;
        barsEl.innerHTML = '';
        var maxCount = 0;
        for (var s = 1; s <= 5; s++) {
          var c = (rc[s] || 0);
          if (c > maxCount) maxCount = c;
        }
        for (var star = 5; star >= 1; star--) {
          var count = rc[star] || 0;
          var pct = maxCount > 0 ? (count / maxCount * 100) : 0;
          var row = document.createElement('div');
          row.className = 'dash-rating-row';
          row.innerHTML =
            '<span class="dash-rating-label">' + star + '</span>' +
            '<span class="dash-rating-star">\u2605</span>' +
            '<div class="dash-rating-bar-wrap"><div class="dash-rating-bar" data-star="' + star +
            '" style="width:' + pct + '%"></div></div>' +
            '<span class="dash-rating-count">' + count.toLocaleString() + '</span>';
          barsEl.appendChild(row);
        }
      }

      // Top tags
      var tags = b.top_tags || [];
      var tagsEl = document.getElementById('topTags');
      if (tagsEl) {
        tags.slice(0, 20).forEach(function(t) {
          var pill = document.createElement('span');
          pill.className = 'pill';
          pill.textContent = t.tag + ' (' + t.count + ')';
          tagsEl.appendChild(pill);
        });
      }
    }).catch(function() { toast('Failed to load dashboard data'); });

    // Load recent images
    apiFetch('/api/search?sort=date&limit=20').then(function(d) {
      var strip = document.getElementById('recentStrip');
      if (!strip) return;
      allResults = d.results.slice();
      var ids = d.results.map(function(r) { return r.id; });
      fetchRatings(ids).then(function() {
        d.results.forEach(function(r, i) {
          var item = document.createElement('div');
          item.className = 'dash-recent-item';
          var img = document.createElement('img');
          img.loading = 'lazy';
          img.src = '/api/thumbnail/' + r.id;
          img.alt = '';
          item.appendChild(img);
          item.addEventListener('click', function() { openLightbox(i); });
          strip.appendChild(item);
        });
        buildFilmstrip();
      });
    }).catch(function() {});
  }

  /* ---------- Search Page ---------- */
  var searchState = { cursor: null, hasMore: false, query: '', sort: 'date' };

  function initSearch() {
    var input = document.getElementById('searchInput');
    var select = document.getElementById('sortSelect');
    var loadBtn = document.getElementById('loadMoreBtn');
    if (!input) return;

    // Check URL params for initial query
    var params = new URLSearchParams(window.location.search);
    if (params.get('q')) {
      input.value = params.get('q');
    }

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

  /* ---------- Stats Page ---------- */
  function initStats() {
    apiFetch('/api/stats/all').then(function(d) {
      var b = d.basic || {};
      var el;
      el = document.getElementById('statFiles');
      if (el) el.textContent = (b.file_count || 0).toLocaleString();
      el = document.getElementById('statTags');
      if (el) el.textContent = (b.tag_count || 0).toLocaleString();

      var src = b.sources || {};
      el = document.getElementById('statSources');
      if (el) el.textContent = Object.keys(src).length;

      // Source breakdown
      var sbEl = document.getElementById('sourceBreakdown');
      if (sbEl) {
        Object.keys(src).forEach(function(k) {
          var row = document.createElement('div');
          row.className = 'source-row';
          row.innerHTML = '<span>' + esc(k) + '</span><span style="font-weight:600;color:var(--accent)">' +
            src[k].toLocaleString() + '</span>';
          sbEl.appendChild(row);
        });
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
            datasets: [{
              label: 'Files',
              data: values,
              backgroundColor: isDark ? 'rgba(96,165,250,0.5)' : 'rgba(59,130,246,0.5)',
              borderColor: isDark ? '#60a5fa' : '#3b82f6',
              borderWidth: 1,
              borderRadius: 4
            }]
          },
          options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
              x: {
                grid: { display: false },
                ticks: { color: isDark ? '#64748b' : '#94a3b8', font: { size: 11 } }
              },
              y: {
                beginAtZero: true,
                ticks: { color: isDark ? '#64748b' : '#94a3b8', font: { size: 11 } },
                grid: { color: isDark ? 'rgba(51,65,85,0.5)' : 'rgba(226,232,240,0.8)' }
              }
            }
          }
        });
      }

      // Top tags
      var tags = b.top_tags || [];
      var tagsEl = document.getElementById('topTags');
      if (tagsEl) {
        tags.forEach(function(t) {
          var pill = document.createElement('span');
          pill.className = 'pill';
          pill.textContent = t.tag + ' (' + t.count + ')';
          tagsEl.appendChild(pill);
        });
      }
    }).catch(function() { toast('Failed to load stats'); });
  }

  /* ---------- Init ---------- */
  initTheme();
  initSidebar();
  initLightbox();

  /* ---------- Public API ---------- */
  window.DashUI = {
    initDashboard: initDashboard,
    initSearch: initSearch,
    initStats: initStats
  };
})();
