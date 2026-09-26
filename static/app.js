    // State management
    let sampleData = null;
    let lastApiResponse = null;
    let isAnalyzing = false;

    // DOM Elements
    const traceTextarea = document.getElementById('trace-textarea');
    const timelineRowsEl = document.getElementById('timeline-rows');
    const timelineCountBadge = document.getElementById('timeline-count-badge');
    const jsonStatusEl = document.getElementById('json-status');
    const editorErrorMsg = document.getElementById('editor-error-msg');
    const editorErrorText = document.getElementById('editor-error-text');
    const tabTimelineBtn = document.getElementById('tab-timeline-btn');
    const tabEditorBtn = document.getElementById('tab-editor-btn');
    const viewTimeline = document.getElementById('view-timeline');
    const viewEditor = document.getElementById('view-editor');
    const runBtn = document.getElementById('run-btn');
    const resetBtn = document.getElementById('reset-btn');
    const heroAnalyzeBtn = document.getElementById('hero-analyze-btn');
    const heroResetBtn = document.getElementById('hero-reset-btn');
    const phaseBadge = document.getElementById('phase-badge');
    const resultContainer = document.getElementById('result-container');
    const sampleTitleEl = document.getElementById('sample-title');
    const sampleIssueEl = document.getElementById('sample-issue');
    const heroStripCaption = document.getElementById('equation-caption');
    const heroStripDisplay = document.getElementById('equation-display');
    const workspaceMain = document.getElementById('workspace-main');
    const announcer = document.getElementById('a11y-announcer');

    // Utility: HTML Escaper
    function esc(s) {
      if (s === null || s === undefined) return '';
      return String(s).replace(/[&<>"']/g, c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
      }[c]));
    }

    // Utility: Action formatting
    function formatActionText(step) {
      if (!step || typeof step !== 'object') return 'Invalid step';
      const action = step.action || '';
      switch (action) {
        case 'view_catalog': return 'View catalog';
        case 'add_item': return `Add item · ${step.item || 'item'}`;
        case 'remove_item': return `Remove item · ${step.item || 'item'}`;
        case 'set_card': return `Select card · ${step.card || 'card'}`;
        case 'begin_checkout': return 'Begin checkout';
        case 'retry_payment': return 'Retry payment';
        case 'view_receipt': return 'View receipt';
        case 'refresh_cart': return 'Refresh cart';
        default: return action.replace(/_/g, ' ');
      }
    }

    function getActionBadge(step) {
      if (!step || typeof step !== 'object') return '';
      if (step.card) return `<span class="badge badge-card">${esc(step.card)}</span>`;
      if (step.item) return `<span class="badge badge-item">${esc(step.item)}</span>`;
      if (step.action === 'retry_payment') return `<span class="badge badge-bounded">retry</span>`;
      if (step.action === 'begin_checkout') return `<span class="badge badge-sample">checkout</span>`;
      return '';
    }

    // Render readable timeline from parsed actions
    function renderTimeline(trace) {
      if (!Array.isArray(trace)) {
        timelineRowsEl.innerHTML = '<div style="padding:16px;color:var(--sp-text-muted);">Trace must be a JSON array of steps</div>';
        timelineCountBadge.textContent = '0';
        return;
      }
      timelineCountBadge.textContent = String(trace.length);
      timelineRowsEl.innerHTML = trace.map((step, idx) => `
        <div class="timeline-row">
          <div class="timeline-step-left">
            <span class="timeline-idx">${String(idx + 1).padStart(2, '0')}</span>
            <span class="timeline-label">${esc(formatActionText(step))}</span>
          </div>
          <div>${getActionBadge(step)}</div>
        </div>
      `).join('');
    }

    // Tab switching
    function switchTab(mode) {
      if (mode === 'timeline') {
        tabTimelineBtn.classList.add('active');
        tabTimelineBtn.setAttribute('aria-selected', 'true');
        tabEditorBtn.classList.remove('active');
        tabEditorBtn.setAttribute('aria-selected', 'false');
        viewTimeline.classList.add('active');
        viewEditor.classList.remove('active');
      } else {
        tabEditorBtn.classList.add('active');
        tabEditorBtn.setAttribute('aria-selected', 'true');
        tabTimelineBtn.classList.remove('active');
        tabTimelineBtn.setAttribute('aria-selected', 'false');
        viewEditor.classList.add('active');
        viewTimeline.classList.remove('active');
      }
    }

    tabTimelineBtn.addEventListener('click', () => switchTab('timeline'));
    tabEditorBtn.addEventListener('click', () => switchTab('editor'));

    // Textarea input handling & live validation
    traceTextarea.addEventListener('input', () => {
      try {
        const parsed = JSON.parse(traceTextarea.value);
        if (!Array.isArray(parsed)) throw new Error('Trace must be a JSON array of actions');
        traceTextarea.setAttribute('aria-invalid', 'false');
        traceTextarea.removeAttribute('aria-describedby');
        editorErrorMsg.style.display = 'none';
        jsonStatusEl.textContent = `Valid JSON (${parsed.length} steps)`;
        jsonStatusEl.classList.remove('err');
        renderTimeline(parsed);
      } catch (err) {
        traceTextarea.setAttribute('aria-invalid', 'true');
        traceTextarea.setAttribute('aria-describedby', 'editor-error-msg');
        editorErrorMsg.style.display = 'flex';
        editorErrorText.textContent = err.message;
        jsonStatusEl.textContent = 'Invalid JSON syntax';
        jsonStatusEl.classList.add('err');
      }
    });

    // Keyboard shortcut: Ctrl/Cmd + Enter
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        runAnalysis();
      }
    });

    // Phase badge helper
    function setPhase(label, className = 'phase-ready') {
      phaseBadge.textContent = label;
      phaseBadge.className = `phase-tag ${className}`;
    }

    // Load initial sample from /api/sample
    async function loadSample() {
      try {
        const res = await fetch('/api/sample');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        sampleData = await res.json();

        if (sampleData.title) sampleTitleEl.textContent = sampleData.title;
        if (sampleData.issue) sampleIssueEl.textContent = sampleData.issue;

        traceTextarea.value = JSON.stringify(sampleData.trace, null, 2);
        traceTextarea.setAttribute('aria-invalid', 'false');
        traceTextarea.removeAttribute('aria-describedby');
        editorErrorMsg.style.display = 'none';
        jsonStatusEl.textContent = `Valid JSON (${sampleData.trace.length} steps)`;
        jsonStatusEl.classList.remove('err');

        renderTimeline(sampleData.trace);
        setPhase('Ready', 'phase-ready');
        renderReadyState();
      } catch (err) {
        sampleIssueEl.textContent = `Could not load sample: ${err.message}`;
        setPhase('Unavailable', 'phase-error');
      }
    }

    // Reset sample button
    function resetToSample() {
      if (!sampleData) return;
      traceTextarea.value = JSON.stringify(sampleData.trace, null, 2);
      traceTextarea.setAttribute('aria-invalid', 'false');
      traceTextarea.removeAttribute('aria-describedby');
      editorErrorMsg.style.display = 'none';
      jsonStatusEl.textContent = `Valid JSON (${sampleData.trace.length} steps)`;
      jsonStatusEl.classList.remove('err');

      renderTimeline(sampleData.trace);
      setPhase('Ready', 'phase-ready');
      renderReadyState();

      heroStripCaption.textContent = 'Trace verification workflow';
      heroStripDisplay.innerHTML = `
        <span class="eq-item">Ready to verify this trace</span>
        <span class="eq-arrow">·</span>
        <span class="eq-item">Fresh-state replay</span>
        <span class="eq-arrow">·</span>
        <span class="eq-item">Exact failure identity</span>
        <span class="eq-arrow">·</span>
        <span class="eq-item">Fix verification</span>
      `;

      announcer.textContent = 'Sample trace reset to original state.';
    }

    resetBtn.addEventListener('click', resetToSample);
    heroResetBtn.addEventListener('click', resetToSample);

    // Initial Honest Ready View
    function renderReadyState() {
      resultContainer.innerHTML = `
        <div class="ready-state">
          <div class="ready-icon" aria-hidden="true">⌁</div>
          <h3 class="ready-title">Ready to verify this trace</h3>
          <p class="ready-desc">Analyze this stateful checkout sequence to determine whether it reproduces a failure, can be reduced to a smaller valid sequence, and whether the corrected implementation stops it.</p>
          <div class="ready-preview-card">
            <div class="ready-preview-header">Verification protocol</div>
            <div class="ready-preview-equation">Every candidate replay starts from fresh state and must preserve the exact observed failure ID.</div>
          </div>
        </div>
      `;
    }

    // Honest pending progression display (no fake timers/streaming)
    function showPendingState() {
      isAnalyzing = true;
      setPhase('Analyzing…', 'phase-analyzing');
      runBtn.disabled = true;
      resetBtn.disabled = true;
      heroAnalyzeBtn.disabled = true;
      heroResetBtn.disabled = true;
      workspaceMain.setAttribute('aria-busy', 'true');
      announcer.textContent = 'Analyzing trace: replaying from fresh state and evaluating candidate reductions.';

      resultContainer.innerHTML = `
        <div class="pending-panel" role="status" aria-label="Analyzing trace">
          <div class="pending-header">
            <div class="pending-spinner" aria-hidden="true"></div>
            <div>
              <h3 class="pending-title">Analyzing trace…</h3>
              <p class="pending-subtitle">Replaying from fresh state on local Python server…</p>
            </div>
          </div>
          <div class="pending-stages-card">
            <div class="pending-stages-title">Evaluation steps</div>
            <ul class="pending-stage-list">
              <li class="pending-stage-item"><span class="pending-stage-bullet">1.</span> Schema and state protocol validation</li>
              <li class="pending-stage-item"><span class="pending-stage-bullet">2.</span> Fresh-state replay</li>
              <li class="pending-stage-item"><span class="pending-stage-bullet">3.</span> Validity-aware candidate reduction (≤250 checks)</li>
              <li class="pending-stage-item"><span class="pending-stage-bullet">4.</span> Five fresh confirmation trials</li>
              <li class="pending-stage-item"><span class="pending-stage-bullet">5.</span> Corrected-behavior verification</li>
            </ul>
          </div>
          <p class="pending-note">Analyzing up to 40 steps with ≤250 candidate checks. No fabricated timings or percentages.</p>
        </div>
      `;
    }

    function clearPendingState() {
      isAnalyzing = false;
      runBtn.disabled = false;
      resetBtn.disabled = false;
      heroAnalyzeBtn.disabled = false;
      heroResetBtn.disabled = false;
      workspaceMain.removeAttribute('aria-busy');
    }

    // Main analysis invocation
    async function runAnalysis() {
      if (isAnalyzing) return; // Prevent double-submission

      let trace;
      try {
        trace = JSON.parse(traceTextarea.value);
        if (!Array.isArray(trace)) throw new Error('Trace must be a JSON array of step objects');
        traceTextarea.setAttribute('aria-invalid', 'false');
        traceTextarea.removeAttribute('aria-describedby');
        editorErrorMsg.style.display = 'none';
      } catch (err) {
        traceTextarea.setAttribute('aria-invalid', 'true');
        traceTextarea.setAttribute('aria-describedby', 'editor-error-msg');
        editorErrorMsg.style.display = 'flex';
        editorErrorText.textContent = err.message;
        switchTab('editor');
        renderJsonErrorState(err.message);
        return;
      }

      showPendingState();

      try {
        const bodyStr = JSON.stringify({ trace });
        if (new TextEncoder().encode(bodyStr).length > 32768) {
          throw new Error('Request exceeds 32 KiB payload limit.');
        }

        const res = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: bodyStr
        });

        let data;
        try {
          data = await res.json();
        } catch (_) {
          throw new Error(`Invalid JSON received from server (HTTP ${res.status})`);
        }

        clearPendingState();

        if (!res.ok) {
          renderTransportError(data.error || `Server responded with HTTP ${res.status}`);
          return;
        }

        lastApiResponse = data;
        renderVerdict(data);
      } catch (err) {
        clearPendingState();
        renderTransportError(err.message || 'Network request failed');
      }
    }

    runBtn.addEventListener('click', runAnalysis);
    heroAnalyzeBtn.addEventListener('click', runAnalysis);

    // Route verdict rendering
    function renderVerdict(data) {
      if (data && data.status === 'REPRODUCED') {
        renderVerifiedResult(data);
      } else if (data && data.status === 'INVALID_TRACE') {
        renderInvalidTrace(data);
      } else if (data && data.status === 'NOT_REPRODUCED') {
        renderNotReproduced(data);
      } else if (data && data.status === 'FLAKY') {
        renderFlaky(data);
      } else {
        renderTransportError(`Unexpected response format from server`);
      }
    }

    // Subsequence Ambiguity Detector:
    // Finds all ordered subsequence embeddings of `red` in `orig`.
    // Only if exactly one embedding exists is row alignment unambiguous.
    function checkSubsequenceAlignment(orig, red) {
      if (!Array.isArray(orig) || !Array.isArray(red) || red.length === 0) {
        return { isUnique: false, keptIndices: new Set() };
      }
      const results = [];
      function search(oIdx, rIdx, currentIndices) {
        if (rIdx === red.length) {
          results.push([...currentIndices]);
          return;
        }
        const target = JSON.stringify(red[rIdx]);
        for (let i = oIdx; i < orig.length; i++) {
          if (JSON.stringify(orig[i]) === target) {
            currentIndices.push(i);
            search(i + 1, rIdx + 1, currentIndices);
            currentIndices.pop();
            if (results.length > 1) return; // Discovered ambiguity early
          }
        }
      }
      search(0, 0, []);
      if (results.length === 1) {
        return { isUnique: true, keptIndices: new Set(results[0]) };
      }
      return { isUnique: false, keptIndices: new Set() };
    }

    // Render verified REPRODUCED state
    function renderVerifiedResult(data) {
      setPhase('Verified', 'phase-verified');

      const original = data.original_steps || [];
      const reduced = data.reduced_steps || [];
      const pctReduction = original.length > 0 ? Math.round(100 * (1 - reduced.length / original.length)) : 0;
      const matchingTrials = (data.trials || []).filter(t => t.status === 'REPRODUCED' && t.failure_id === data.failure_id).length;
      const totalTrials = (data.trials || []).length;
      const mismatches = data.original && Array.isArray(data.original.mismatches)
        ? data.original.mismatches
        : [];
      const minimality = data.minimality || { certified: false, kind: 'bounded-local', checks: 0 };

      // Update hero strip strictly with REAL response values
      heroStripCaption.textContent = 'Live verified result';
      heroStripDisplay.innerHTML = `
        <span class="eq-item">${original.length} actions</span>
        <span class="eq-arrow">→</span>
        <span class="eq-item eq-proof">${reduced.length} proof steps</span>
        <span class="eq-arrow">→</span>
        <span class="eq-item">${matchingTrials}/${totalTrials} confirmed</span>
        <span class="eq-arrow">→</span>
        <span class="eq-item">${data.fixed_passes ? 'fix passes' : 'fix needs review'}</span>
      `;

      announcer.textContent = `Analysis complete: Same failure verified. ${original.length} actions reduced to ${reduced.length} proof steps. ${data.failure_id} confirmed in ${matchingTrials} of ${totalTrials} fresh replays.`;

      // Subsequence ambiguity check
      const alignment = checkSubsequenceAlignment(original, reduced);

      // Build complete mismatch evidence. Compatibility fields still point to
      // the first mismatch, but the UI presents every mismatching retry.
      let failureMomentHtml = '';
      if (data.original && (data.original.expected !== undefined || data.original.actual !== undefined)) {
        const visibleMismatches = mismatches.length ? mismatches : [{
          attempt: 1,
          step: '—',
          expected: data.original.expected,
          actual: data.original.actual
        }];
        const mismatchRows = visibleMismatches.map((attempt, idx) => `
          <div class="retry-mismatch-row">
            <div class="retry-mismatch-meta">Retry ${esc(attempt.attempt || idx + 1)} · trace step ${esc(attempt.step || '—')}</div>
            <div class="failure-moment-grid">
              <div class="failure-col">
                <span class="failure-label">Expected at retry</span>
                <span class="failure-val expected">${esc(attempt.expected)}</span>
              </div>
              <div class="failure-col">
                <span class="failure-label">Actually charged</span>
                <span class="failure-val actual">${esc(attempt.actual)}</span>
              </div>
            </div>
          </div>
        `).join('');
        failureMomentHtml = `
          <div class="failure-moment-card">
            <div class="failure-moment-header">
              <span class="failure-moment-title">Observed failure ${visibleMismatches.length === 1 ? 'moment' : 'moments'}</span>
              <span class="badge badge-failure">${esc(data.failure_id)}</span>
            </div>
            <div class="retry-mismatch-list">${mismatchRows}</div>
            <div class="failure-moment-oracle-note">Every mismatching retry from this replay is listed. The top-level expected and actual fields retain the first mismatch for API compatibility.</div>
          </div>
        `;
      }

      // Build trial cells
      const trialCellsHtml = (data.trials || []).map((t, idx) => {
        const isMatch = t.status === 'REPRODUCED' && t.failure_id === data.failure_id;
        const cls = isMatch ? 'trial-pass' : 'trial-fail';
        const label = `Trial ${idx + 1}: ${esc(t.status)} (${esc(t.failure_id || 'none')})`;
        return `
          <div class="trial-cell ${cls}" title="${label}" aria-label="${label}">
            <span>#${idx + 1}</span>
            <span>${isMatch ? '✓ Verified' : '✗ Diverged'}</span>
          </div>
        `;
      }).join('');

      // Corrected behavior callout
      const fixedCalloutHtml = data.fixed_passes ? `
        <div class="status-callout callout-success">
          <div class="callout-icon">✓</div>
          <div>
            <strong>Corrected behavior: target failure not reproduced</strong>
            <div class="callout-desc">${esc(data.fixed_result ? data.fixed_result.detail : 'Charges current active card on retry')}</div>
          </div>
        </div>
      ` : `
        <div class="status-callout callout-warning">
          <div class="callout-icon">⚠</div>
          <div>
            <strong>Corrected behavior still needs review</strong>
            <div class="callout-desc">${esc(data.fixed_result ? data.fixed_result.detail : 'Result did not confirm fix')}</div>
          </div>
        </div>
      `;

      // Original trace list: conservative alignment
      const origListHtml = original.map((step, idx) => {
        let cls = 'step-neutral';
        let badgeHtml = '';
        if (alignment.isUnique) {
          const isKept = alignment.keptIndices.has(idx);
          cls = isKept ? 'step-retained-orig' : 'step-pruned';
          badgeHtml = isKept ? '<span class="badge badge-bounded">retained</span>' : '';
        }
        return `
          <div class="step-item ${cls}">
            <div class="step-item-left">
              <span class="step-item-idx">${String(idx + 1).padStart(2, '0')}</span>
              <span class="step-item-text">${esc(formatActionText(step))}</span>
            </div>
            <div>${badgeHtml}</div>
          </div>
        `;
      }).join('');

      // Ambiguity note if mapping wasn't strictly unique
      const ambiguityNoticeHtml = alignment.isUnique ? '' : `
        <div class="comparison-ambiguity-note">
          ⚠ Original-row alignment is ambiguous because identical actions repeat. Showing original trace and verified reduced sequence separately without claiming specific row provenance.
        </div>
      `;

      // Reduced trace list
      const reducedListHtml = reduced.map((step, idx) => `
        <div class="step-item step-proof">
          <div class="step-item-left">
            <span class="step-item-idx">${String(idx + 1).padStart(2, '0')}</span>
            <span class="step-item-text">${esc(formatActionText(step))}</span>
          </div>
          <div>${getActionBadge(step)}</div>
        </div>
      `).join('');

      // Events table in drawer
      const eventsTableHtml = (data.original && data.original.events ? data.original.events : []).map(ev => {
        const isMismatch = ev.is_mismatch === true;
        return `
          <tr>
            <td>${esc(ev.step)}</td>
            <td><code>${esc(ev.action)}</code></td>
            <td>${esc(ev.current_card || '—')}</td>
            <td>${esc(ev.pending_card || '—')}</td>
            <td>${esc(ev.expected_card || '—')}</td>
            <td class="${isMismatch ? 'cell-diff' : ''}">${esc(ev.charged_card || '—')}</td>
            <td class="${isMismatch ? 'cell-diff' : ''}">${ev.action === 'retry_payment' ? (isMismatch ? 'Mismatch' : 'Matched') : '—'}</td>
          </tr>
        `;
      }).join('');

      // Construct Result Panel HTML
      resultContainer.innerHTML = `
        <div class="result-view" tabindex="-1">
          <!-- Result Hero -->
          <div class="result-hero">
            <div class="result-hero-top">
              <span class="badge badge-success">Same failure verified</span>
              <span class="reduction-pill">${pctReduction}% fewer steps</span>
            </div>
            <div class="equation-large">
              <span>${original.length} actions</span>
              <span class="arrow">→</span>
              <span class="steps-reduced">${reduced.length} proof steps</span>
            </div>
            <div class="result-hero-badges">
              <span class="badge badge-failure">${esc(data.failure_id)}</span>
              <span class="badge badge-sample">${matchingTrials}/${totalTrials} fresh confirmations</span>
              <span class="badge badge-bounded">${esc(mismatches.length || 1)} retry mismatch${(mismatches.length || 1) === 1 ? '' : 'es'}</span>
              <span class="badge badge-bounded">${minimality.certified ? '1-minimal certified' : 'bounded local reduction'}</span>
            </div>
            <div class="result-hero-meta">
              ${esc(data.attempts)} candidate checks · ${esc(data.orphan_steps_pruned)} orphan steps pruned · ${esc(data.duration_ms)} ms execution
            </div>
          </div>

          <!-- Failure Moment -->
          ${failureMomentHtml}

          <!-- Confirmation Strip -->
          <div class="confirmation-section">
            <div class="confirmation-header">
              <span class="confirmation-title">Fresh Confirmation Trials</span>
              <span class="confirmation-count">${matchingTrials} of ${totalTrials} confirmed</span>
            </div>
            <div class="trial-strip" role="group" aria-label="Trial confirmations">
              ${trialCellsHtml}
            </div>
          </div>

          <!-- Corrected Behavior Callout -->
          ${fixedCalloutHtml}

          <!-- Comparison Section -->
          <div class="traces-comparison">
            <div class="comparison-col">
              <div class="col-header">
                <span class="col-title">Original trace · ${original.length} steps</span>
              </div>
              <div class="step-list">
                ${origListHtml}
              </div>
              ${ambiguityNoticeHtml}
              <div class="comparison-footnote">
                ${alignment.isUnique ? 'Pruned noise struck out. No steps reordered.' : 'Complete original execution trace.'}
              </div>
            </div>
            <div class="comparison-col">
              <div class="col-header">
                <span class="col-title">Reduced proof · ${reduced.length} steps</span>
                <span class="badge badge-bounded">verified</span>
              </div>
              <div class="step-list">
                ${reducedListHtml}
              </div>
              <div class="comparison-footnote">${minimality.certified
                ? 'Pruned without insertion or reordering. No single retained step can be removed while preserving the exact failure ID.'
                : 'Pruned without insertion or reordering. One-minimality was not certified before the candidate-check budget ended.'}</div>
            </div>
          </div>

          <!-- Proof Drawer -->
          <details class="proof-drawer" id="proof-drawer">
            <summary>
              <span>Inspect execution proof & diagnostics</span>
              <span class="drawer-arrow" aria-hidden="true">▼</span>
            </summary>
            <div class="drawer-content">
              <div class="drawer-stats-grid">
                <div class="stat-card">
                  <span class="stat-label">Original Status</span>
                  <span class="stat-val">${esc(data.original ? data.original.status : '—')}</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Failure ID</span>
                  <span class="stat-val" style="color:var(--sp-failure);">${esc(data.failure_id)}</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Candidate Checks</span>
                  <span class="stat-val">${esc(data.attempts)}</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Orphans Pruned</span>
                  <span class="stat-val">${esc(data.orphan_steps_pruned)}</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Duration</span>
                  <span class="stat-val">${esc(data.duration_ms)} ms</span>
                </div>
                <div class="stat-card">
                  <span class="stat-label">Minimality</span>
                  <span class="stat-val">${minimality.certified ? '1-minimal certified' : 'bounded local'}</span>
                </div>
              </div>

              <div class="drawer-subhead">Replay Event Log (Original Trace)</div>
              <p class="comparison-footnote" style="margin-bottom:8px;">Retry rows identify the expected card, charged card, and whether that attempt mismatched.</p>
              <div class="events-table-wrap">
                <table class="events-table">
                  <thead>
                    <tr>
                      <th>Step</th>
                      <th>Action</th>
                      <th>Current Card</th>
                      <th>Pending Card</th>
                      <th>Expected Card</th>
                      <th>Charged Card</th>
                      <th>Retry Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${eventsTableHtml}
                  </tbody>
                </table>
              </div>

              <div class="drawer-actions">
                <button type="button" class="btn btn-secondary" id="download-proof-btn">
                  <svg class="btn-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" aria-hidden="true">
                    <path d="M8 2v9M4 7l4 4 4-4M2 13h12"/>
                  </svg>
                  Download proof JSON
                </button>
                <span class="drawer-hint">Tied directly to latest /api/analyze response.</span>
              </div>

              <div class="scope-note">
                This result is locally reduced within a bounded search. ${esc(minimality.statement || '')} Every accepted candidate is replayed from fresh state and must preserve the exact observed failure ID. The sample uses synthetic data.
              </div>
            </div>
          </details>
        </div>
      `;

      // Move programmatic focus to result container
      const rv = resultContainer.querySelector('.result-view');
      if (rv) rv.focus();

      // Attach download listener
      const dlBtn = document.getElementById('download-proof-btn');
      if (dlBtn) dlBtn.addEventListener('click', downloadProofJson);
    }

    // Download proof JSON handler
    function downloadProofJson() {
      if (!lastApiResponse) return;
      const blob = new Blob([JSON.stringify(lastApiResponse, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'sequenceproof-evidence.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    // Negative State: INVALID_TRACE
    function renderInvalidTrace(data) {
      setPhase('Invalid trace', 'phase-error');
      announcer.textContent = `Analysis complete: Invalid trace. ${data.original ? data.original.detail : ''}`;

      resultContainer.innerHTML = `
        <div class="negative-card state-invalid" tabindex="-1">
          <div class="negative-head">
            <span class="badge badge-error">INVALID_TRACE</span>
            <h3 class="negative-title">Invalid trace</h3>
          </div>
          <div class="negative-detail">
            ${esc(data.original ? data.original.detail : 'State protocol validation error')}
            ${data.original && data.original.at_step ? ` (at step ${esc(data.original.at_step)})` : ''}
          </div>
          <div class="negative-explanation">
            <p>SequenceProof rejects invalid traces and protocol violations immediately. In order to preserve mathematical and causal integrity, <strong>invalid candidates are never counted as reproduction evidence</strong>, and no reduction is attempted.</p>
          </div>
          <div class="negative-actions">
            <button type="button" class="btn btn-secondary" onclick="resetToSample()">Reset to valid sample</button>
          </div>
        </div>
        <div class="scope-note">
          This result is locally reduced within a bounded search. Every accepted candidate is replayed from fresh state and must preserve the exact observed failure ID. The sample uses synthetic data.
        </div>
      `;
      const nc = resultContainer.querySelector('.negative-card');
      if (nc) nc.focus();
    }

    // Negative State: NOT_REPRODUCED
    function renderNotReproduced(data) {
      setPhase('Not reproduced', 'phase-neutral');
      announcer.textContent = `Analysis complete: Target failure not reproduced. ${data.original ? data.original.detail : ''}`;

      resultContainer.innerHTML = `
        <div class="negative-card state-not-reproduced" tabindex="-1">
          <div class="negative-head">
            <span class="badge badge-neutral">NOT_REPRODUCED</span>
            <h3 class="negative-title">Target failure not reproduced</h3>
          </div>
          <div class="negative-detail">${esc(data.original ? data.original.detail : 'No wrong card charge occurred')}</div>
          <div class="negative-explanation">
            <p>The trace executed cleanly from fresh state without reproducing the <code>WRONG_CARD_CHARGED</code> failure. SequenceProof only reduces traces that demonstrate the target failure, so no reduced proof was produced.</p>
          </div>
          <div class="negative-actions">
            <button type="button" class="btn btn-secondary" onclick="resetToSample()">Reset to sample</button>
          </div>
        </div>
        <div class="scope-note">
          This result is locally reduced within a bounded search. Every accepted candidate is replayed from fresh state and must preserve the exact observed failure ID. The sample uses synthetic data.
        </div>
      `;
      const nc = resultContainer.querySelector('.negative-card');
      if (nc) nc.focus();
    }

    // Negative State: FLAKY (distinct warning amber state)
    function renderFlaky(data) {
      setPhase('Flaky', 'phase-warning');
      announcer.textContent = 'Analysis complete: Confirmation inconsistent. Candidate trace was flaky and not verified.';

      const trialsHtml = (data.trials || []).map((t, idx) => {
        const isMatch = t.status === 'REPRODUCED' && t.failure_id === data.failure_id;
        return `
          <div class="trial-cell ${isMatch ? 'trial-pass' : 'trial-fail'}">
            <span>#${idx + 1}</span>
            <span>${esc(t.status)} (${esc(t.failure_id || 'none')})</span>
          </div>
        `;
      }).join('');

      resultContainer.innerHTML = `
        <div class="negative-card state-flaky" tabindex="-1">
          <div class="negative-head">
            <span class="badge badge-warning">FLAKY</span>
            <h3 class="negative-title">Confirmation inconsistent (FLAKY)</h3>
          </div>
          <div class="negative-detail">The failure did not reproduce consistently in 5 fresh replays. This candidate cannot be verified as proof.</div>
          <div class="trial-strip" style="margin-bottom: 14px;">
            ${trialsHtml}
          </div>
          <div class="negative-explanation">
            <p>SequenceProof requires all 5 fresh replays to yield the exact original failure ID. Because one or more replays produced a different outcome, this candidate is marked flaky and no reduction evidence is claimed.</p>
          </div>
          <div class="negative-actions">
            <button type="button" class="btn btn-secondary" onclick="runAnalysis()">Retry analysis</button>
            <button type="button" class="btn btn-secondary" onclick="resetToSample()">Reset sample</button>
          </div>
        </div>
      `;
      const nc = resultContainer.querySelector('.negative-card');
      if (nc) nc.focus();
    }

    // Editor JSON error state
    function renderJsonErrorState(errMsg) {
      setPhase('JSON error', 'phase-error');
      announcer.textContent = `JSON needs correction: ${errMsg}`;

      resultContainer.innerHTML = `
        <div class="negative-card state-invalid" tabindex="-1">
          <div class="negative-head">
            <span class="badge badge-error">SYNTAX ERROR</span>
            <h3 class="negative-title">JSON needs correction</h3>
          </div>
          <div class="negative-detail">${esc(errMsg)}</div>
          <div class="negative-explanation">
            <p>The editor contains invalid JSON syntax. Please correct the trace syntax before analyzing. No request was sent to the backend, and your editor input has been preserved.</p>
          </div>
          <div class="negative-actions">
            <button type="button" class="btn btn-secondary" onclick="switchTab('editor')">Return to editor</button>
            <button type="button" class="btn btn-secondary" onclick="resetToSample()">Reset to valid sample</button>
          </div>
        </div>
      `;
      const nc = resultContainer.querySelector('.negative-card');
      if (nc) nc.focus();
    }

    // Transport / Server error state
    function renderTransportError(errMsg) {
      setPhase('Unavailable', 'phase-error');
      announcer.textContent = `Analysis unavailable: ${errMsg}`;

      resultContainer.innerHTML = `
        <div class="negative-card state-error" tabindex="-1">
          <div class="negative-head">
            <span class="badge badge-error">TRANSPORT ERROR</span>
            <h3 class="negative-title">Analysis unavailable</h3>
          </div>
          <div class="negative-detail">${esc(errMsg)}</div>
          <div class="negative-explanation">
            <p>The server could not complete the request. Ensure the backend server is running and that request payload does not exceed 32 KiB. Your editor input has been preserved.</p>
          </div>
          <div class="negative-actions">
            <button type="button" class="btn btn-secondary" onclick="runAnalysis()">Retry</button>
            <button type="button" class="btn btn-secondary" onclick="resetToSample()">Reset sample</button>
          </div>
        </div>
      `;
      const nc = resultContainer.querySelector('.negative-card');
      if (nc) nc.focus();
    }

    // Initialize application on load
    loadSample();
