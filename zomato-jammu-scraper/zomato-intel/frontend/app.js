// ── Global State & Constants ──────────────────────────────────────────────────
const COLORS = ['#FF4D4D','#FFAA00','#00D4AA','#8B5CF6','#3B82F6','#EC4899','#F97316','#10B981','#6366F1','#14B8A6','#F43F5E','#A78BFA'];
let charts = {};
let currentTab = 'scraper';
let dataTable = 'restaurants', dataPage = 1, dataSort = 'rating', dataSortDir = 'desc';
const expandedRows = new Set();

const tableConfigs = {
  master_consolidated: ['id','restaurant_name','item_name','price','category','rating','cuisines'],
  restaurants: ['id','name','dining_rating','dining_votes','delivery_rating','delivery_votes','rating','exact_votes','review_count','cuisines','price_for_two','address'],
  menu_items: ['id','restaurant_name','item_name','price','category','is_veg','bestseller'],
  reviews: ['id','restaurant_name','reviewer_name','rating','review_text','review_timestamp'],
};

function debounce(fn, delay) {
  let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), delay); };
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
const tabs = document.querySelectorAll('.nav-tab');
const screens = document.querySelectorAll('.screen');

tabs.forEach(t => t.addEventListener('click', () => {
  const tab = t.dataset.tab;
  tabs.forEach(x => x.classList.remove('active'));
  screens.forEach(x => x.classList.remove('active'));
  t.classList.add('active');
  document.getElementById('screen-' + tab).classList.add('active');
  currentTab = tab;
  if (tab === 'stats') loadStats();
  if (tab === 'map') {
    initMap();
    if (mapInst) setTimeout(() => mapInst.invalidateSize(), 100);
  }
  if (tab === 'data') loadData();
}));

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast-item toast-${type}`;
  el.textContent = msg;
  document.getElementById('toast').appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

// ── Location Filters ──────────────────────────────────────────────────────────
const filterCity = document.getElementById('filterCity');
const filterState = document.getElementById('filterState');

async function loadLocations() {
  try {
    const r = await fetch('/api/locations');
    const d = await r.json();
    const curCity = filterCity.value;
    const curState = filterState.value;
    filterCity.innerHTML = '<option value="all">All Cities</option>' + d.cities.map(c => `<option value="${c}">${c}</option>`).join('');
    filterState.innerHTML = '<option value="all">All States</option>' + d.states.map(s => `<option value="${s}">${s}</option>`).join('');
    if (d.cities.includes(curCity)) filterCity.value = curCity;
    if (d.states.includes(curState)) filterState.value = curState;
  } catch(e) {}
}
loadLocations();

[filterCity, filterState].forEach(el => el.addEventListener('change', () => {
  if (currentTab === 'stats') loadStats();
  else if (currentTab === 'data') loadData();
  else if (currentTab === 'map') loadMapData();
  toast(`Filtering by ${filterCity.value}`, 'info');
}));

document.getElementById('refreshBtn').addEventListener('click', () => {
  loadLocations();
  if (currentTab === 'stats') loadStats();
  else if (currentTab === 'data') loadData();
  else if (currentTab === 'map') loadMapData();
  loadScraperStatus();
  toast('Refreshed', 'success');
});

// ── Scraper Logic ─────────────────────────────────────────────────────────────
let scraperRunning = false;
let scraperWs = null;
let logLines = [];

function addLog(level, msg) {
  const out = document.getElementById('logOutput');
  const div = document.createElement('div');
  div.className = `log-line log-${level}`;
  div.innerHTML = `<span class="log-time">${new Date().toLocaleTimeString()}</span> <span class="log-msg">${msg}</span>`;
  out.prepend(div);
  logLines.push(`[${new Date().toLocaleTimeString()}] [${level}] ${msg}`);
  if (out.children.length > 200) out.lastChild.remove();
}

function setScraperUI(running) {
  scraperRunning = running;
  document.getElementById('startScraperBtn').disabled = running;
  document.getElementById('stopScraperBtn').disabled = !running;
  document.getElementById('scraperStatusDot').className = 'status-dot ' + (running ? 'status-active' : 'status-idle');
  document.getElementById('scraperStatusText').textContent = running ? 'Scraping...' : 'Ready';
}

document.getElementById('startScraperBtn').addEventListener('click', () => {
  const resetCheck = document.getElementById('chkReset').checked;
  if (resetCheck && !confirm('Are you sure you want to RESET the database before scraping?')) return;

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
  scraperWs = new WebSocket(`${protocol}://${location.host}/ws/scraper`);
  setScraperUI(true);
  document.getElementById('progressCard').style.display = '';

  scraperWs.onopen = () => {
    scraperWs.send(JSON.stringify({
      action: 'start',
      reset: resetCheck,
      url: document.getElementById('targetUrl').value,
      city: document.getElementById('targetCity').value,
      state: document.getElementById('targetState').value,
      max_reviews: parseInt(document.getElementById('maxReviews').value) || 50,
    }));
  };

  let count = 0;
  scraperWs.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'log') {
      addLog(msg.level || 'info', msg.msg);
      if (msg.level === 'success') {
        count++;
        document.getElementById('progressLabel').textContent = `Scraped ${count} restaurants...`;
        document.getElementById('progressPct').textContent = count;
        document.getElementById('progressFill').style.width = Math.min(count * 2, 100) + '%';
      }
    } else if (msg.type === 'done') {
      addLog('success', msg.msg);
      setScraperUI(false);
      loadScraperStatus();
    } else if (msg.type === 'error') {
      addLog('error', msg.msg);
      setScraperUI(false);
    }
  };
  scraperWs.onerror = () => { addLog('error', 'WebSocket error'); setScraperUI(false); };
  scraperWs.onclose = () => { if (scraperRunning) setScraperUI(false); };
});

document.getElementById('stopScraperBtn').addEventListener('click', () => {
  if (!scraperWs) return;
  scraperWs.send(JSON.stringify({ action: 'stop' }));
  setTimeout(() => setScraperUI(false), 500);
});

// ── Stats / Charts ────────────────────────────────────────────────────────────
async function loadStats() {
  try {
    const city = filterCity.value;
    const state = filterState.value;
    const r = await fetch(`/api/stats?city=${city}&state=${state}`);
    const d = await r.json();
    const o = d.overview;
    document.getElementById('sKpiRestaurants').textContent = o.restaurants.toLocaleString();
    document.getElementById('sKpiReviews').textContent = o.reviews.toLocaleString();
    document.getElementById('sKpiMenu').textContent = o.menu_items.toLocaleString();
    document.getElementById('sKpiRating').textContent = o.avg_rating + '★';
    document.getElementById('sKpiPrice').textContent = '₹' + o.avg_price;
    document.getElementById('sKpiDb').textContent = o.db_size_mb + ' MB';
    renderChart('chartCuisine', 'doughnut', d.cuisines.map(x=>x.name), d.cuisines.map(x=>x.count), COLORS);
    renderChart('chartPrice', 'bar', d.price_distribution.map(x=>x.range), d.price_distribution.map(x=>x.count), '#3B82F6');
    renderHBar('chartArea', d.area_stats.map(x=>x.area), d.area_stats.map(x=>x.avg_rating));
    renderChart('chartVeg', 'doughnut', ['Veg', 'Non-Veg'], [d.veg_nonveg.veg, d.veg_nonveg.nonveg], ['#00D464','#FF4D4D']);
    renderHBar('chartDishes', d.top_dishes.map(x=>x.name), d.top_dishes.map(x=>x.count), '#FFAA00');
    renderChart('chartRating', 'bar', d.rating_distribution.map(x=>x.rating), d.rating_distribution.map(x=>x.count), '#8B5CF6');
  } catch(e) { 
    console.error(e);
    toast('Failed to load stats: ' + e.message, 'error'); 
  }
}

function renderChart(id, type, labels, data, colors) {
  if (charts[id]) charts[id].destroy();
  const el = document.getElementById(id);
  if (!el) return;
  const ctx = el.getContext('2d');
  charts[id] = new Chart(ctx, {
    type,
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: colors,
        borderColor: 'transparent',
        borderRadius: type === 'bar' ? 6 : 0,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#A0AABF', font: { size: 11 } } } },
      scales: type === 'bar' ? {
        x: { ticks: { color: '#6B7A99' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: '#6B7A99' }, grid: { color: 'rgba(255,255,255,0.05)' } }
      } : {}
    }
  });
}

function renderHBar(id, labels, data, color = '#3B82F6') {
  if (charts[id]) charts[id].destroy();
  const el = document.getElementById(id);
  if (!el) return;
  const ctx = el.getContext('2d');
  charts[id] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data, backgroundColor: color, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#6B7A99' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: '#A0AABF', font: { size: 10 } }, grid: { display: false } }
      }
    }
  });
}

// ── Map Logic ─────────────────────────────────────────────────────────────────
let mapInst = null, heatLayer = null, markersLayer = null;

function initMap() {
  if (mapInst) return;
  mapInst = L.map('map').setView([32.7266, 74.8570], 13);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { attribution: '&copy; OpenStreetMap' }).addTo(mapInst);
  
  // Event listeners for map controls
  document.querySelectorAll('#mapHeatMode .radio-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('#mapHeatMode .radio-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadMapData();
    };
  });
  
  document.querySelectorAll('#mapLayerBtns .radio-btn').forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll('#mapLayerBtns .radio-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      loadMapData();
    };
  });

  const minR = document.getElementById('mapMinRating');
  const maxP = document.getElementById('mapMaxPrice');
  if (minR) minR.oninput = () => { 
    document.getElementById('valMinRating').textContent = minR.value;
    loadMapData(); 
  };
  if (maxP) maxP.oninput = () => { 
    document.getElementById('valMaxPrice').textContent = maxP.value;
    loadMapData();
  };
  document.getElementById('refreshMapBtn')?.addEventListener('click', loadMapData);

  loadMapData();
}

async function loadMapData() {
  const minRating = document.getElementById('mapMinRating')?.value || 0;
  const maxPrice = document.getElementById('mapMaxPrice')?.value || 2000;
  const city = filterCity.value;
  const state = filterState.value;
  try {
    const r = await fetch(`/api/map?min_rating=${minRating}&max_price=${maxPrice}&city=${city}&state=${state}`);
    const d = await r.json();
    renderMapLayer(d.restaurants);
  } catch(e) {}
}

function renderMapLayer(mapData) {
  if (heatLayer) mapInst.removeLayer(heatLayer);
  if (markersLayer) mapInst.removeLayer(markersLayer);
  
  const layerMode = document.querySelector('#mapLayerBtns .radio-btn.active')?.dataset.layer || 'heat';
  const heatMode = document.querySelector('#mapHeatMode .radio-btn.active')?.dataset.mode || 'rating';
  
  const legendTitle = document.querySelector('#mapLegend .legend-title');
  if (legendTitle) {
    const titles = {
      'rating': 'Customer Satisfaction',
      'price': 'Price Intensity',
      'density': 'Restaurant Density',
      'delivery_votes': 'Popularity Hubs (Delivery Votes)'
    };
    legendTitle.textContent = titles[heatMode] || 'Market Intelligence';
  }

  if (layerMode === 'pins' || layerMode === 'both') {
    markersLayer = L.layerGroup();
    
    // Calculate max votes safely
    let maxV = 1;
    if (heatMode === 'delivery_votes') {
      const votesArray = mapData.map(r => parseInt(r.delivery_votes) || 0);
      maxV = Math.max(...votesArray, 1);
    }

    mapData.forEach(r => {
      if (!r.lat || !r.lng) return;
      
      // Traffic Light Color System (Red-Yellow-Green)
      let color = r.rating >= 4.0 ? '#22C55E' : r.rating >= 3.0 ? '#FACC15' : '#EF4444'; 
      let opacity = 0.8;
      let weight = 1;

      // Dynamic radius logic - MEGA SCALING
      let radius = 7;
      if (heatMode === 'delivery_votes') {
        const v = parseInt(r.delivery_votes) || 0;
        const ratio = maxV > 0 ? v / maxV : 0;
        radius = 8 + (Math.pow(ratio, 0.4) * 62); 
        
        // Popularity Colors: High=Green, Med=Yellow, Low=Red
        color = v > (maxV * 0.5) ? '#22C55E' : v > (maxV * 0.1) ? '#FACC15' : '#EF4444';
        opacity = 0.9;
        weight = 2;
      }

      const marker = L.circleMarker([r.lat, r.lng], { 
        radius: radius, 
        fillColor: color, 
        color: '#fff', 
        weight: weight, 
        fillOpacity: opacity,
        className: 'pop-marker' 
      });
      
      marker.bindTooltip(r.name || 'Unknown', { permanent: false, direction: 'top', className: 'map-tooltip', offset: [0, -5] });
      
      const topItemsHtml = (r.top_items || []).map(i => `<li>${i.name} (₹${i.price})</li>`).join('');
      
      marker.bindPopup(`<div class="map-popup">
        <div class="popup-name">${r.name || 'Unknown'}</div>
        <div class="popup-stats">⭐ ${r.rating || '?'} &nbsp; 💰 ${r.price || '?'}</div>
        <div class="popup-meta">🛵 Delivery Votes: ${r.delivery_votes || '0'}</div>
        <div class="popup-meta">${r.cuisines || ''}</div>
        ${topItemsHtml ? `<hr><ul class="popup-list">${topItemsHtml}</ul>` : ''}
      </div>`);
      markersLayer.addLayer(marker);
    });
    markersLayer.addTo(mapInst);
  }

  if (layerMode === 'heat' || layerMode === 'both') {
    let pts = [];
    if (heatMode === 'rating') {
      pts = mapData.filter(r => r.lat && r.lng).map(r => [r.lat, r.lng, (r.rating || 0) / 5]);
      heatLayer = L.heatLayer(pts, { radius: 30, blur: 20, maxZoom: 17, gradient: { 0.4: 'red', 0.7: 'yellow', 1.0: 'green' } }).addTo(mapInst);
    } else if (heatMode === 'price') {
      const maxP = Math.max(...mapData.map(r => parseFloat(r.price) || 0)) || 1000;
      pts = mapData.filter(r => r.lat && r.lng).map(r => [r.lat, r.lng, (parseFloat(r.price) || 0) / maxP]);
      heatLayer = L.heatLayer(pts, { radius: 30, blur: 20, maxZoom: 17 }).addTo(mapInst);
    } else if (heatMode === 'delivery_votes') {
      const maxV = Math.log10(Math.max(...mapData.map(r => parseInt(r.delivery_votes) || 0)) + 1) || 1;
      pts = mapData.filter(r => r.lat && r.lng).map(r => {
        const v = Math.log10((parseInt(r.delivery_votes) || 0) + 1);
        return [r.lat, r.lng, (v / maxV) * 1.5];
      });
      heatLayer = L.heatLayer(pts, { 
        radius: 35, blur: 20, maxZoom: 17,
        gradient: { 0.2: 'red', 0.6: 'yellow', 1.0: 'green' } 
      }).addTo(mapInst);
    } else { // density
      pts = mapData.filter(r => r.lat && r.lng).map(r => [r.lat, r.lng, 0.6]);
      heatLayer = L.heatLayer(pts, { radius: 30, blur: 15, maxZoom: 17 }).addTo(mapInst);
    }
  }
}

// ── Data Explorer ─────────────────────────────────────────────────────────────
async function toggleRow(rid, tr) {
  if (expandedRows.has(rid)) {
    expandedRows.delete(rid);
    tr.nextElementSibling.remove();
    tr.querySelector('.expand-btn').textContent = '➕';
    return;
  }
  
  const btn = tr.querySelector('.expand-btn');
  btn.textContent = '⏳';
  
  try {
    const r = await fetch(`/api/restaurant/${rid}/details`);
    const d = await r.json();
    
    expandedRows.add(rid);
    btn.textContent = '➖';
    
    const detailRow = document.createElement('tr');
    detailRow.className = 'detail-row';
    const colCount = tr.cells.length;
    
    let menuHtml = d.menu.length ? `<div class="nested-section">
      <div class="nested-title">🍽️ Menu Items (${d.menu.length})</div>
      <div class="nested-scroll">
        <table class="nested-table">
          <thead><tr><th>Item</th><th>Price</th><th>Category</th></tr></thead>
          <tbody>${d.menu.map(m => `<tr><td>${m.item_name}</td><td>₹${m.price}</td><td>${m.category||'—'}</td></tr>`).join('')}</tbody>
        </table>
      </div>
    </div>` : '<div class="nested-empty">No menu items found.</div>';

    let reviewsHtml = d.reviews.length ? `<div class="nested-section">
      <div class="nested-title">💬 Reviews (${d.reviews.length})</div>
      <div class="nested-scroll">
        ${d.reviews.map(rev => `<div class="nested-rev">
          <div style="display:flex;justify-content:space-between"><strong>${rev.reviewer_name||'Anonymous'}</strong> <span style="color:var(--amber)">⭐ ${rev.rating}</span></div>
          <p>${rev.review_text}</p>
          <small style="color:var(--text3)">${rev.review_timestamp||''}</small>
        </div>`).join('')}
      </div>
    </div>` : '<div class="nested-empty">No reviews found.</div>';

    detailRow.innerHTML = `<td colspan="${colCount}" style="padding:0">
      <div class="expand-pane">
        ${menuHtml}
        ${reviewsHtml}
      </div>
    </td>`;
    tr.after(detailRow);
  } catch(e) {
    btn.textContent = '❌';
    toast('Failed to load details', 'error');
  }
}

const searchEl = document.getElementById('dataSearch');
if (searchEl) searchEl.addEventListener('input', debounce(() => { dataPage = 1; loadData(); }, 400));

document.querySelectorAll('.view-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.view-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    dataTable = btn.dataset.view;
    dataPage = 1;
    dataSort = 'id';
    loadData();
  });
});

const perPageEl = document.getElementById('dataPerPage');
if (perPageEl) perPageEl.addEventListener('change', () => { dataPage = 1; loadData(); });

const exportBtn = document.getElementById('exportBtn');
if (exportBtn) exportBtn.addEventListener('click', () => {
    const city = filterCity.value;
    const state = filterState.value;
    window.location = `/api/export/${dataTable}?city=${city}&state=${state}`;
});

async function loadData() {
  const search = document.getElementById('dataSearch')?.value || '';
  const perPage = document.getElementById('dataPerPage')?.value || 25;
  const city = filterCity.value;
  const state = filterState.value;
  try {
    const r = await fetch(`/api/data/${dataTable}?page=${dataPage}&per_page=${perPage}&search=${encodeURIComponent(search)}&sort_by=${dataSort}&sort_dir=${dataSortDir}&city=${city}&state=${state}`);
    const d = await r.json();
    renderTable(d);
  } catch(e) { toast('Data load error: ' + e, 'error'); }
}

function renderTable(d) {
  const allCols = tableConfigs[dataTable];
  const head = document.getElementById('dataTableHead');
  const body = document.getElementById('dataTableBody');
  if (!head || !body) return;

  const activeCols = [...allCols];
  if (dataTable === 'restaurants') activeCols.unshift('expand');

  head.innerHTML = '<tr>' + activeCols.map(c => {
    if (c === 'expand') return '<th style="width:40px"></th>';
    return `<th data-col="${c}" onclick="setSort('${c}')">${c.replace(/_/g,' ').toUpperCase()} <span class="sort-icon">${dataSort===c?(dataSortDir==='asc'?'↑':'↓'):'↕'}</span></th>`
  }).join('') + '</tr>';
  
  if (!d.data || d.data.length === 0) {
    body.innerHTML = `<tr><td colspan="${activeCols.length}" style="text-align:center;padding:40px;color:var(--text3)">No records found.</td></tr>`;
    return;
  }
  
  body.innerHTML = '';
  d.data.forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = activeCols.map(c => {
      if (c === 'expand') return `<td><button class="expand-btn" onclick="toggleRow(${row.id}, this.parentElement.parentElement)">➕</button></td>`;
      
      let val = row[c];
      if (c === 'is_veg') {
        const lv = String(val || '').toLowerCase();
        if (lv === '1' || lv === 'veg') val = '<span class="badge badge-veg">VEG</span>';
        else if (lv === '0' || lv === 'non-veg') val = '<span class="badge badge-nonveg">NON-VEG</span>';
        else val = '—';
      }
      else if (c === 'bestseller') val = val == '1' ? '<span class="badge badge-best">⭐ Best</span>' : '—';
      else if (c === 'rating') val = val ? `<div style="display:flex;flex-direction:column"><span style="color:var(--text3);font-size:10px">OVERALL</span><span style="color:var(--amber);font-weight:700">⭐ ${val}</span></div>` : '—';
      else if (c === 'dining_rating') val = val ? `<div style="display:flex;flex-direction:column"><span style="color:var(--text3);font-size:10px">DINING</span><span style="color:var(--red);font-weight:700">🍽️ ${val}</span></div>` : '—';
      else if (c === 'delivery_rating') val = val ? `<div style="display:flex;flex-direction:column"><span style="color:var(--text3);font-size:10px">DELIVERY</span><span style="color:var(--success);font-weight:700">🛵 ${val}</span></div>` : '—';
      else if (c === 'dining_votes' || c === 'delivery_votes' || c === 'exact_votes') val = val ? `<span style="color:var(--text2);font-size:11px">${val} votes</span>` : '—';
      else if (c === 'price_for_two' || c === 'price') {
        const p = parseFloat(val);
        val = !isNaN(p) && p > 0 ? `₹${p}` : (val || '—');
      }
      else if (c === 'exact_votes') val = `<span style="color:var(--text2)">${val || '0'}</span>`;
      else if (c === 'review_count') val = `<b style="color:var(--success)">${val || '0'}</b>`;
      else if (c === 'name' || c === 'restaurant_name') val = `<span style="color:var(--text1);font-weight:600">${val}</span>`;
      else val = (val !== null && val !== undefined) ? (String(val).length > 50 ? String(val).slice(0,50) + '…' : val) : '—';
      return `<td title="${row[c] || ''}">${val}</td>`;
    }).join('');
    body.appendChild(tr);
  });

  const pag = document.getElementById('dataPagination');
  if (pag) {
    let pagHtml = '';
    if (d.pages > 1) {
      pagHtml += `<button class="btn btn-sm" onclick="changePage(${dataPage-1})" ${dataPage===1?'disabled':''}>Prev</button>`;
      for (let i=Math.max(1, dataPage-2); i<=Math.min(d.pages, dataPage+2); i++) {
        pagHtml += `<button class="btn btn-sm ${i===dataPage?'btn-primary':''}" onclick="changePage(${i})">${i}</button>`;
      }
      pagHtml += `<button class="btn btn-sm" onclick="changePage(${dataPage+1})" ${dataPage===d.pages?'disabled':''}>Next</button>`;
    }
    pag.innerHTML = pagHtml;
  }
}

window.setSort = c => {
  if (dataSort === c) dataSortDir = dataSortDir === 'asc' ? 'desc' : 'asc';
  else { dataSort = c; dataSortDir = 'asc'; }
  loadData();
};
window.changePage = p => { if (p > 0) { dataPage = p; loadData(); } };

// ── AI Analyst ────────────────────────────────────────────────────────────────
let aiHistory = [];
const aiInput = document.getElementById('aiInput');
const aiMessages = document.getElementById('aiMessages');

if (aiInput) {
  aiInput.addEventListener('keypress', e => { if (e.key === 'Enter') sendAiQuery(); });
}

async function sendAiQuery(q = null) {
  const query = q || aiInput.value.trim();
  if (!query) return;
  const userDiv = document.createElement('div');
  userDiv.className = 'msg msg-user';
  userDiv.innerHTML = `<div class="msg-bubble">${query}</div>`;
  aiMessages.appendChild(userDiv);
  aiMessages.scrollTop = aiMessages.scrollHeight;
  
  const loading = document.createElement('div');
  loading.className = 'msg msg-ai';
  loading.innerHTML = `<div class="ai-thinking"><div class="ai-dot"></div><div class="ai-dot"></div><div class="ai-dot"></div></div>`;
  aiMessages.appendChild(loading);
  
  try {
    const r = await fetch('/api/ai/query', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ question: query, history: aiHistory, city: filterCity.value, state: filterState.value })
    });
    const d = await r.json();
    loading.remove();
    const botDiv = document.createElement('div');
    botDiv.className = 'msg msg-ai';
    botDiv.innerHTML = `<div class="msg-bubble">${marked.parse(d.answer)}</div>`;
    aiMessages.appendChild(botDiv);
    aiHistory.push({ role: 'user', content: query }, { role: 'assistant', content: d.answer });
    if (aiHistory.length > 10) aiHistory = aiHistory.slice(-10);
  } catch(e) {
    loading.innerHTML = `<div class="msg-bubble" style="color:var(--red)">Error: ${e.message}</div>`;
  }
  aiMessages.scrollTop = aiMessages.scrollHeight;
}

// ── Settings & System ─────────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    const d = await r.json();
    const keyEl = document.getElementById('settingsApiKey');
    if (keyEl) keyEl.placeholder = d.gemini_api_key_masked || 'Not set';
    const profileEl = document.getElementById('settingsChromeProfile');
    if (profileEl) profileEl.value = d.chrome_profile || '';
  } catch(e) {}
}

document.getElementById('saveSettingsBtn')?.addEventListener('click', async () => {
  const key = document.getElementById('settingsApiKey').value;
  const body = { chrome_profile: document.getElementById('settingsChromeProfile').value };
  if (key) body.gemini_api_key = key;
  try {
    const r = await fetch('/api/config', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const d = await r.json();
    toast(d.message, 'success');
    loadConfig();
  } catch(e) { toast('Save failed', 'error'); }
});

async function loadScraperStatus() {
  try {
    const r = await fetch('/api/system/status');
    const d = await r.json();
    document.getElementById('kpiRestaurants').textContent = d.restaurants;
    document.getElementById('kpiReviews').textContent = d.reviews;
    document.getElementById('kpiMenuItems').textContent = d.menu_items;
    document.getElementById('kpiDbSize').textContent = d.db_size_mb + ' MB';
  } catch(e) {}
}

// Init
loadScraperStatus();
loadConfig();
loadStats();
