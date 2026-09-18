document.addEventListener('DOMContentLoaded', () => {
    // ── Element refs (null-safe throughout) ───────────────────────────────
    const scenarioGrid      = document.getElementById('scenarioGrid');
    const queryForm         = document.getElementById('queryForm');
    const queryInput        = document.getElementById('queryInput');
    const submitBtn         = document.getElementById('submitBtn');
    const loadingIndicator  = document.getElementById('loadingIndicator');
    const resultSection     = document.getElementById('resultSection');
    const confidenceBadge   = document.getElementById('confidenceBadge');
    const stepCountBadge    = document.getElementById('stepCountBadge');
    const bestAnswerText    = document.getElementById('bestAnswerText');
    const gapText           = document.getElementById('gapText');
    const clarificationCard = document.getElementById('clarificationCard');
    const clarificationText = document.getElementById('clarificationText');
    const citationsList     = document.getElementById('citationsList');
    const citationsWrapper  = document.getElementById('citationsWrapper');
    const timelineSteps     = document.getElementById('timelineSteps');
    const toggleTraceBtn    = document.getElementById('toggleTraceBtn');
    const rawTraceWrapper   = document.getElementById('rawTraceWrapper');
    const rawTraceCode      = document.getElementById('rawTraceCode');

    // ── Scrollytelling Reveal Animations ──────────────────────────────────
    const revealObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el));

    // ── Category filter (scenarios section) ───────────────────────────────
    document.querySelectorAll('.cat-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const cat = btn.dataset.cat;
            document.querySelectorAll('.scenario-card').forEach(card => {
                card.classList.toggle('hidden', cat !== 'all' && card.dataset.cat !== cat);
            });
        });
    });

    // ── Suggestion chips (query page) ─────────────────────────────────────
    document.querySelectorAll('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            if (queryInput) {
                queryInput.value = chip.dataset.q;
                queryInput.focus();
            }
        });
    });

    // ── Show / hide loading ───────────────────────────────────────────────
    function showLoading(show) {
        if (loadingIndicator) loadingIndicator.classList.toggle('hidden', !show);
        if (resultSection && show) resultSection.classList.add('hidden');
        if (submitBtn) submitBtn.disabled = show;
    }

    // ── Run scenario ──────────────────────────────────────────────────────
    async function runScenario(id, cardEl) {
        document.querySelectorAll('.scenario-card').forEach(c => c.classList.remove('active'));
        if (cardEl) cardEl.classList.add('active');
        showLoading(true);
        try {
            const res = await fetch(`/api/run-scenario/${id}`, { method: 'POST' });
            if (!res.ok) {
                const err = await res.json().catch(() => ({ detail: res.statusText }));
                throw new Error(err.detail || 'Server error');
            }
            renderResult(await res.json());
        } catch (e) {
            showError(e.message);
        } finally {
            showLoading(false);
        }
    }

    // Attach scenario click handlers if cards rendered by JS (fallback)
    if (scenarioGrid) {
        scenarioGrid.addEventListener('click', e => {
            const card = e.target.closest('.scenario-card');
            if (card) runScenario(card.dataset.id, card);
        });
    }

    // ── Submit custom query ───────────────────────────────────────────────
    if (queryForm) {
        queryForm.addEventListener('submit', async e => {
            e.preventDefault();
            const query = queryInput ? queryInput.value.trim() : '';
            if (!query) return;
            showLoading(true);
            try {
                const res = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query })
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({ detail: res.statusText }));
                    throw new Error(err.detail || 'Server error');
                }
                renderResult(await res.json());
            } catch (e) {
                showError(e.message);
            } finally {
                showLoading(false);
            }
        });
    }

    // ── Inline error display ──────────────────────────────────────────────
    function showError(msg) {
        if (resultSection) {
            resultSection.classList.remove('hidden');
            resultSection.innerHTML = `
                <div style="padding:1.5rem;border:1px solid rgba(239,68,68,0.3);background:rgba(239,68,68,0.06);">
                    <div style="font-family:var(--mono);font-size:0.72rem;text-transform:uppercase;letter-spacing:.1em;color:rgba(239,68,68,0.7);margin-bottom:.5rem;">Error</div>
                    <p style="font-size:.875rem;color:var(--text-muted);">${msg}</p>
                </div>`;
        }
    }

    // ── Render full result ────────────────────────────────────────────────
    function renderResult(data) {
        if (!resultSection) return;
        // Re-inject result structure if we stomped it with an error message
        if (resultSection.querySelector('.result-header') === null) {
            location.reload(); return;
        }
        resultSection.classList.remove('hidden');

        const ans    = data.final_answer || {};
        const traces = data.traces || [];

        // Confidence
        if (confidenceBadge) {
            const level = (ans.confidence || 'low').toLowerCase();
            confidenceBadge.textContent = (ans.confidence || 'LOW').toUpperCase();
            confidenceBadge.className = `confidence-badge ${level}`;
        }
        // Step count
        if (stepCountBadge) {
            stepCountBadge.textContent = `${traces.length} step${traces.length !== 1 ? 's' : ''}`;
        }
        // Answer
        if (bestAnswerText) bestAnswerText.textContent = ans.best_answer_so_far || 'No answer returned.';
        // Gap
        if (gapText) gapText.textContent = ans.confidence_gap || 'None reported.';
        // Clarification
        if (clarificationCard) {
            const show = !!ans.focused_clarification;
            clarificationCard.classList.toggle('hidden', !show);
            if (clarificationText && show) clarificationText.textContent = ans.focused_clarification;
        }
        
        // LangChain Comparison
        const comparisonCard = document.getElementById('comparisonCard');
        const comparisonText = document.getElementById('comparisonText');
        if (comparisonCard && comparisonText) {
            if (data.langchain_comparison) {
                comparisonText.textContent = data.langchain_comparison;
                comparisonCard.classList.remove('hidden');
            } else {
                comparisonCard.classList.add('hidden');
            }
        }

        // Citations
        if (citationsList && citationsWrapper) {
            citationsList.innerHTML = '';
            const hasCitations = ans.citations && ans.citations.length > 0;
            citationsWrapper.classList.toggle('hidden', !hasCitations);
            if (hasCitations) {
                ans.citations.forEach(c => {
                    const el = document.createElement('div');
                    el.className = 'citation-item';
                    el.innerHTML = `
                        <a href="${c.url}" target="_blank" rel="noopener noreferrer" class="citation-link">${c.title}</a>
                        <div class="citation-snippet">${c.snippet || `Retrieved: ${c.retrieved_date || 'N/A'}`}</div>`;
                    citationsList.appendChild(el);
                });
            }
        }
        // Timeline
        renderTimeline(traces);
        // Raw trace
        if (rawTraceCode) rawTraceCode.textContent = traces.map(t => JSON.stringify(t, null, 2)).join('\n\n---\n\n');
        if (rawTraceWrapper) rawTraceWrapper.classList.add('hidden');
        if (toggleTraceBtn) toggleTraceBtn.textContent = 'Raw JSONL';

        resultSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // ── Render execution timeline ─────────────────────────────────────────
    function renderTimeline(traces) {
        if (!timelineSteps) return;
        timelineSteps.innerHTML = '';
        if (!traces.length) {
            timelineSteps.innerHTML = '<p style="font-size:.8rem;color:var(--text-muted);">No trace available.</p>';
            return;
        }
        traces.forEach((t, i) => {
            const action  = t.planned_action || {};
            const toolName = action.tool
                ? action.tool
                : (action.final_answer ? 'final_answer'
                : (action.__raw_malformed__ ? 'malformed_json'
                : (action.force_stop ? 'force_stop' : 'action')));

            const validation = (t.validation || '').toLowerCase();
            const statusClass = validation.startsWith('passed') ? 'passed'
                : validation.startsWith('rejected') ? 'rejected' : 'error';

            const obs     = t.observation || {};
            const summary = obs.summary || obs.error || 'Observation logged.';

            const item = document.createElement('div');
            item.className = `step-item status-${statusClass}`;
            item.innerHTML = `
                <div class="step-dot"></div>
                <div style="flex:1;min-width:0;">
                    <span class="step-tool">Step ${t.step ?? (i + 1)}: ${toolName}</span>
                    <span class="step-status ${statusClass}">${validation.toUpperCase()}</span>
                    <div class="step-summary">${summary.length > 120 ? summary.slice(0, 120) + '…' : summary}</div>
                </div>`;
            timelineSteps.appendChild(item);
        });
    }

    // ── Toggle raw trace ──────────────────────────────────────────────────
    if (toggleTraceBtn && rawTraceWrapper) {
        toggleTraceBtn.addEventListener('click', () => {
            const hidden = rawTraceWrapper.classList.toggle('hidden');
            toggleTraceBtn.textContent = hidden ? 'Raw JSONL' : 'Hide';
        });
    }
});
