/**
 * Admin Interface JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    // Preview / regex tester
    const previewBtn = document.getElementById('preview-btn');
    const previewText = document.getElementById('preview-text');
    const previewPattern = document.getElementById('preview-pattern');
    const previewResults = document.getElementById('preview-results');
    const previewMatches = document.getElementById('preview-matches');
    const previewSummary = document.getElementById('preview-summary');

    if (previewBtn) {
        previewBtn.addEventListener('click', async function() {
            const text = previewText.value;
            const pattern = previewPattern.value;

            if (!text || !pattern) {
                alert('Bitte Text und Muster eingeben');
                return;
            }

            try {
                const formData = new FormData();
                formData.append('text', text);
                formData.append('pattern', pattern);

                const response = await fetch('/admin/preview', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();
                previewResults.style.display = 'block';

                if (result.success) {
                    if (previewSummary) {
                        previewSummary.textContent =
                            result.matches.length === 1
                                ? '1 Treffer'
                                : result.matches.length + ' Treffer';
                    }
                    if (result.matches.length === 0) {
                        previewMatches.innerHTML =
                            '<p style="color: #64748b;">Keine Treffer. Prüfen Sie Muster oder Testtext.</p>';
                    } else {
                        previewMatches.innerHTML = result.matches.map(m =>
                            `<div class="match-item">
                                <strong>„${escapeHtml(m.match)}“</strong>
                                <span style="color: #64748b;"> (Position ${m.start}–${m.end})</span>
                            </div>`
                        ).join('');
                    }
                } else {
                    if (previewSummary) previewSummary.textContent = 'Fehler';
                    previewMatches.innerHTML = `<p style="color: #dc2626;">Ungültiges Muster: ${escapeHtml(result.error)}</p>`;
                }
            } catch (error) {
                previewResults.style.display = 'block';
                if (previewSummary) previewSummary.textContent = 'Fehler';
                previewMatches.innerHTML = `<p style="color: #dc2626;">Fehler: ${escapeHtml(error.message)}</p>`;
            }
        });
    }

    // Keyword/Regex tabs on the entity detail page
    const tabButtons = document.querySelectorAll('.pattern-add-tabs .tab-btn');
    const keywordForm = document.getElementById('keyword-form');
    const regexForm = document.getElementById('regex-form');

    if (tabButtons.length && keywordForm && regexForm) {
        tabButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                tabButtons.forEach(b => b.classList.remove('active'));
                this.classList.add('active');
                const isKeyword = this.dataset.tab === 'keyword';
                keywordForm.style.display = isKeyword ? 'flex' : 'none';
                regexForm.style.display = isKeyword ? 'none' : 'flex';
            });
        });
    }

    // Regex template chips fill the regex form and switch to the regex tab
    document.querySelectorAll('.template-chips .chip').forEach(chip => {
        chip.addEventListener('click', function() {
            if (!regexForm) return;
            if (keywordForm) keywordForm.style.display = 'none';
            if (regexForm) regexForm.style.display = 'flex';
            tabButtons.forEach(b => b.classList.toggle('active', b.dataset.tab === 'regex'));
            const nameInput = document.getElementById('regex-name');
            const regexInput = regexForm.querySelector('input[name="regex"]');
            if (regexInput) regexInput.value = this.dataset.regex || '';
            if (nameInput && !nameInput.value) nameInput.value = this.dataset.name || 'muster';
        });
    });

    // Clicking a pattern row fills the tester
    document.querySelectorAll('.data-table tr[data-pattern-regex]').forEach(row => {
        row.addEventListener('click', function(e) {
            if (e.target.closest('a, button, form')) return;
            if (previewPattern) previewPattern.value = this.dataset.patternRegex || '';
            if (previewText) previewText.focus();
        });
    });

    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    // Checkbox handling for is_active
    const checkboxes = document.querySelectorAll('input[type="checkbox"][name="is_active"]');
    checkboxes.forEach(checkbox => {
        // Add hidden input to handle unchecked state
        const hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = checkbox.name;
        hidden.value = 'false';
        checkbox.parentNode.insertBefore(hidden, checkbox);

        checkbox.addEventListener('change', function() {
            hidden.value = this.checked ? 'true' : 'false';
        });

        // Set initial value
        hidden.value = checkbox.checked ? 'true' : 'false';
    });
});

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}