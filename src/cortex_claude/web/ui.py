def get_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Cortex Claude</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.28.1/cytoscape.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg: #0a0a0f;
    --bg-card: #12121a;
    --bg-hover: #1a1a2e;
    --border: #1e1e30;
    --text: #e0e0e8;
    --text-dim: #6b6b80;
    --accent: #f97316;
    --accent-dim: #c2410c;
    --accent-glow: rgba(249, 115, 22, 0.15);
    --green: #22c55e;
    --blue: #3b82f6;
    --purple: #a855f7;
    --red: #ef4444;
    --font: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
}

body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    height: 100vh;
    overflow: hidden;
}

.layout {
    display: grid;
    grid-template-columns: 320px 1fr;
    grid-template-rows: 56px 1fr;
    height: 100vh;
}

/* Header */
.header {
    grid-column: 1 / -1;
    background: var(--bg-card);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 12px;
}

.logo {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.5px;
}

.logo span { color: var(--accent); }

.header-stats {
    display: flex;
    gap: 24px;
}

.stat {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--text-dim);
}

.stat-value {
    color: var(--text);
    font-weight: 600;
    font-family: var(--font);
}

/* Sidebar */
.sidebar {
    background: var(--bg-card);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.search-box {
    padding: 12px;
    border-bottom: 1px solid var(--border);
}

.search-box input {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 12px;
    color: var(--text);
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s;
}

.search-box input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-glow);
}

.search-box input::placeholder { color: var(--text-dim); }

.tab-bar {
    display: flex;
    border-bottom: 1px solid var(--border);
}

.tab {
    flex: 1;
    padding: 10px;
    text-align: center;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
}

.tab:hover { color: var(--text); background: var(--bg-hover); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

.list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}

.list::-webkit-scrollbar { width: 4px; }
.list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.list-item {
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 4px;
    transition: background 0.15s;
    border: 1px solid transparent;
}

.list-item:hover { background: var(--bg-hover); border-color: var(--border); }
.list-item.active { background: var(--accent-glow); border-color: var(--accent-dim); }

.list-item-title {
    font-size: 13px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.list-item-meta {
    display: flex;
    gap: 8px;
    margin-top: 4px;
    font-size: 11px;
    color: var(--text-dim);
}

.tag {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    color: var(--text-dim);
}

.fact-item {
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 4px;
    font-family: var(--font);
    font-size: 12px;
    cursor: pointer;
    transition: background 0.15s;
}

.fact-item:hover { background: var(--bg-hover); }

.fact-subject { color: var(--blue); }
.fact-relation { color: var(--text-dim); }
.fact-object { color: var(--green); }
.fact-arrow { color: var(--accent); margin: 0 4px; }

/* Main area */
.main {
    position: relative;
    background: var(--bg);
}

#graph {
    width: 100%;
    height: 100%;
}

/* Entity detail panel */
.detail-panel {
    position: absolute;
    top: 12px;
    right: 12px;
    width: 340px;
    max-height: calc(100% - 24px);
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow-y: auto;
    display: none;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}

.detail-panel.visible { display: block; }

.detail-header {
    padding: 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.detail-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--accent);
}

.detail-close {
    background: none;
    border: none;
    color: var(--text-dim);
    font-size: 18px;
    cursor: pointer;
    padding: 4px;
    line-height: 1;
}

.detail-close:hover { color: var(--text); }

.detail-section {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
}

.detail-section:last-child { border-bottom: none; }

.detail-section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    margin-bottom: 8px;
}

.detail-fact {
    font-family: var(--font);
    font-size: 12px;
    padding: 4px 0;
    line-height: 1.5;
}

.detail-memory {
    font-size: 13px;
    line-height: 1.5;
    padding: 8px;
    background: var(--bg);
    border-radius: 6px;
    margin-bottom: 6px;
}

/* Graph controls */
.graph-controls {
    position: absolute;
    bottom: 12px;
    left: 12px;
    display: flex;
    gap: 6px;
}

.graph-btn {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    padding: 8px 12px;
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
}

.graph-btn:hover { background: var(--bg-hover); border-color: var(--accent); }

/* Empty state */
.empty-state {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-dim);
    font-size: 14px;
    text-align: center;
    padding: 40px;
    line-height: 1.6;
}

/* Loading */
@keyframes pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }
.loading { animation: pulse 1.5s infinite; color: var(--text-dim); }
</style>
</head>
<body>

<div class="layout">
    <div class="header">
        <div class="header-left">
            <div class="logo">corte<span>x</span></div>
        </div>
        <div class="header-stats" id="stats">
            <div class="stat"><span>memories</span> <span class="stat-value" id="stat-memories">-</span></div>
            <div class="stat"><span>facts</span> <span class="stat-value" id="stat-facts">-</span></div>
            <div class="stat"><span>scopes</span> <span class="stat-value" id="stat-scopes">-</span></div>
            <div class="stat"><span>storage</span> <span class="stat-value" id="stat-size">-</span></div>
        </div>
    </div>

    <div class="sidebar">
        <div class="search-box">
            <input type="text" id="search" placeholder="Search memories...">
        </div>
        <div class="tab-bar">
            <div class="tab active" data-tab="memories">Memories</div>
            <div class="tab" data-tab="facts">Facts</div>
        </div>
        <div class="list" id="list"></div>
    </div>

    <div class="main">
        <div id="graph"></div>

        <div class="graph-controls">
            <button class="graph-btn" onclick="cy.fit(undefined, 50)">Fit</button>
            <button class="graph-btn" onclick="cy.zoom(cy.zoom() * 1.3)">+</button>
            <button class="graph-btn" onclick="cy.zoom(cy.zoom() * 0.7)">-</button>
            <button class="graph-btn" onclick="resetLayout()">Reset</button>
        </div>

        <div class="detail-panel" id="detail">
            <div class="detail-header">
                <div class="detail-title" id="detail-title">Entity</div>
                <button class="detail-close" onclick="closeDetail()">&times;</button>
            </div>
            <div id="detail-content"></div>
        </div>
    </div>
</div>

<script>
let cy;
let currentTab = 'memories';
let allMemories = [];
let allFacts = [];

async function api(path) {
    const res = await fetch(path);
    return res.json();
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatDate(ts) {
    if (!ts) return '';
    return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function loadStats() {
    const data = await api('/api/stats');
    document.getElementById('stat-memories').textContent = data.total_memories;
    document.getElementById('stat-facts').textContent = data.total_facts;
    document.getElementById('stat-scopes').textContent = data.scopes.length;
    document.getElementById('stat-size').textContent = formatSize(data.total_size);
}

async function loadMemories() {
    allMemories = await api('/api/memories');
    if (currentTab === 'memories') renderMemories(allMemories);
}

async function loadFacts() {
    const graph = await api('/api/graph');
    allFacts = graph.edges.map(e => ({ subject: e.source, relation: e.label, object: e.target, confidence: e.confidence }));
    if (currentTab === 'facts') renderFacts(allFacts);
}

function renderMemories(items) {
    const list = document.getElementById('list');
    if (!items.length) {
        list.innerHTML = '<div class="empty-state">No memories yet.<br>Save something with cortex_save.</div>';
        return;
    }
    list.innerHTML = items.map(m => {
        const content = (m.content || '').substring(0, 120);
        const tags = JSON.parse(m.tags || '[]');
        const tagHtml = tags.slice(0, 3).map(t => '<span class="tag">' + t + '</span>').join('');
        return '<div class="list-item" onclick="showMemoryDetail(\\''+m.id+'\\')"><div class="list-item-title">' + content + '</div><div class="list-item-meta"><span>' + m.scope + '</span><span>' + formatDate(m.created_at) + '</span>' + tagHtml + '</div></div>';
    }).join('');
}

function renderFacts(items) {
    const list = document.getElementById('list');
    if (!items.length) {
        list.innerHTML = '<div class="empty-state">No facts extracted yet.</div>';
        return;
    }
    list.innerHTML = items.map(f =>
        '<div class="fact-item" onclick="focusNode(\\''+f.subject+'\\')">' +
        '<span class="fact-subject">' + f.subject + '</span>' +
        '<span class="fact-arrow"> &rarr; </span>' +
        '<span class="fact-relation">' + f.relation + '</span>' +
        '<span class="fact-arrow"> &rarr; </span>' +
        '<span class="fact-object">' + f.object + '</span></div>'
    ).join('');
}

async function loadGraph() {
    const data = await api('/api/graph');

    const elements = [];

    data.nodes.forEach(n => {
        elements.push({ data: { id: n.id, label: n.label, weight: n.weight } });
    });

    data.edges.forEach((e, i) => {
        elements.push({ data: { id: 'e' + i, source: e.source, target: e.target, label: e.label, confidence: e.confidence } });
    });

    cy = cytoscape({
        container: document.getElementById('graph'),
        elements: elements,
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'background-color': '#f97316',
                    'color': '#e0e0e8',
                    'font-size': '11px',
                    'font-family': "'SF Mono', monospace",
                    'text-valign': 'bottom',
                    'text-margin-y': 6,
                    'width': 'mapData(weight, 1, 20, 16, 48)',
                    'height': 'mapData(weight, 1, 20, 16, 48)',
                    'border-width': 2,
                    'border-color': '#c2410c',
                    'text-outline-width': 2,
                    'text-outline-color': '#0a0a0f',
                }
            },
            {
                selector: 'edge',
                style: {
                    'label': 'data(label)',
                    'width': 'mapData(confidence, 0.5, 1, 1, 3)',
                    'line-color': '#1e1e30',
                    'target-arrow-color': '#1e1e30',
                    'target-arrow-shape': 'triangle',
                    'curve-style': 'bezier',
                    'font-size': '9px',
                    'font-family': "'SF Mono', monospace",
                    'color': '#6b6b80',
                    'text-rotation': 'autorotate',
                    'text-outline-width': 2,
                    'text-outline-color': '#0a0a0f',
                    'arrow-scale': 0.8,
                }
            },
            {
                selector: 'node:active, node:selected',
                style: {
                    'background-color': '#22c55e',
                    'border-color': '#16a34a',
                    'overlay-opacity': 0,
                }
            },
            {
                selector: 'node.highlight',
                style: {
                    'background-color': '#3b82f6',
                    'border-color': '#2563eb',
                }
            },
            {
                selector: 'edge.highlight',
                style: {
                    'line-color': '#f97316',
                    'target-arrow-color': '#f97316',
                    'width': 3,
                }
            },
        ],
        layout: {
            name: 'cose',
            animate: true,
            animationDuration: 800,
            nodeRepulsion: 8000,
            idealEdgeLength: 120,
            gravity: 0.3,
            padding: 50,
        },
        minZoom: 0.2,
        maxZoom: 4,
    });

    cy.on('tap', 'node', async function(evt) {
        const node = evt.target;
        const name = node.data('id');

        cy.elements().removeClass('highlight');
        node.addClass('highlight');
        node.connectedEdges().addClass('highlight');
        node.neighborhood('node').addClass('highlight');

        const data = await api('/api/entity?name=' + encodeURIComponent(name));
        showEntityDetail(name, data);
    });

    cy.on('tap', function(evt) {
        if (evt.target === cy) {
            cy.elements().removeClass('highlight');
            closeDetail();
        }
    });
}

function resetLayout() {
    cy.layout({
        name: 'cose',
        animate: true,
        animationDuration: 800,
        nodeRepulsion: 8000,
        idealEdgeLength: 120,
        gravity: 0.3,
        padding: 50,
    }).run();
}

function focusNode(id) {
    const node = cy.getElementById(id);
    if (node.length) {
        cy.animate({ center: { eles: node }, zoom: 2 }, { duration: 500 });
        cy.elements().removeClass('highlight');
        node.addClass('highlight');
        node.connectedEdges().addClass('highlight');
        node.neighborhood('node').addClass('highlight');
    }
}

function showEntityDetail(name, data) {
    const panel = document.getElementById('detail');
    const title = document.getElementById('detail-title');
    const content = document.getElementById('detail-content');

    title.textContent = name;

    let html = '';

    if (data.facts && data.facts.length) {
        html += '<div class="detail-section"><div class="detail-section-title">Facts (' + data.facts.length + ')</div>';
        data.facts.forEach(f => {
            html += '<div class="detail-fact"><span class="fact-subject">' + f.subject + '</span><span class="fact-arrow"> &rarr; </span><span class="fact-relation">' + f.relation + '</span><span class="fact-arrow"> &rarr; </span><span class="fact-object">' + f.object + '</span></div>';
        });
        html += '</div>';
    }

    if (data.memories && data.memories.length) {
        html += '<div class="detail-section"><div class="detail-section-title">Related Memories (' + data.memories.length + ')</div>';
        data.memories.forEach(m => {
            html += '<div class="detail-memory">' + (m.content || '').substring(0, 200) + '</div>';
        });
        html += '</div>';
    }

    if (!html) html = '<div class="detail-section"><div class="empty-state">No details found.</div></div>';

    content.innerHTML = html;
    panel.classList.add('visible');
}

function showMemoryDetail(id) {
    const mem = allMemories.find(m => m.id === id);
    if (!mem) return;

    const panel = document.getElementById('detail');
    const title = document.getElementById('detail-title');
    const content = document.getElementById('detail-content');

    title.textContent = 'Memory';

    const tags = JSON.parse(mem.tags || '[]');
    let html = '<div class="detail-section">';
    html += '<div class="detail-memory">' + (mem.content || '') + '</div>';
    html += '<div class="list-item-meta" style="margin-top:8px">';
    html += '<span>Scope: ' + mem.scope + '</span>';
    html += '<span>Score: ' + (mem.decay_score || 0).toFixed(2) + '</span>';
    html += '<span>Accessed: ' + (mem.access_count || 0) + 'x</span>';
    html += '</div>';
    if (tags.length) {
        html += '<div style="margin-top:8px">' + tags.map(t => '<span class="tag">' + t + '</span> ').join('') + '</div>';
    }
    html += '</div>';

    if (mem.summary) {
        html += '<div class="detail-section"><div class="detail-section-title">Summary</div>';
        html += '<div class="detail-memory">' + mem.summary + '</div></div>';
    }

    content.innerHTML = html;
    panel.classList.add('visible');
}

function closeDetail() {
    document.getElementById('detail').classList.remove('visible');
}

// Search
document.getElementById('search').addEventListener('input', async function(e) {
    const q = e.target.value.trim();
    if (q.length < 2) {
        if (currentTab === 'memories') renderMemories(allMemories);
        else renderFacts(allFacts);
        return;
    }

    if (currentTab === 'memories') {
        const results = await api('/api/search?q=' + encodeURIComponent(q));
        renderMemories(results);
    } else {
        const filtered = allFacts.filter(f =>
            f.subject.includes(q.toLowerCase()) ||
            f.object.includes(q.toLowerCase()) ||
            f.relation.includes(q.toLowerCase())
        );
        renderFacts(filtered);
    }
});

// Tabs
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', function() {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        this.classList.add('active');
        currentTab = this.dataset.tab;
        document.getElementById('search').value = '';
        if (currentTab === 'memories') renderMemories(allMemories);
        else renderFacts(allFacts);
    });
});

// Init
Promise.all([loadStats(), loadMemories(), loadFacts(), loadGraph()]);
</script>
</body>
</html>"""
