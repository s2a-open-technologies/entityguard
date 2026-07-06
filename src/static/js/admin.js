/**
 * Admin Interface JavaScript
 */

document.addEventListener('DOMContentLoaded', function() {
    // Pattern preview functionality
    const previewBtn = document.getElementById('preview-btn');
    const previewText = document.getElementById('preview-text');
    const previewPattern = document.getElementById('preview-pattern');
    const previewResults = document.getElementById('preview-results');
    const previewMatches = document.getElementById('preview-matches');

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

                if (result.success) {
                    if (result.matches.length === 0) {
                        previewMatches.innerHTML = '<p style="color: #64748b;">Keine Treffer gefunden</p>';
                    } else {
                        previewMatches.innerHTML = result.matches.map(m =>
                            `<div class="match-item">
                                <strong>Treffer:</strong> "${escapeHtml(m.match)}"<br>
                                <span style="color: #64748b;">Position: ${m.start}-${m.end}</span>
                            </div>`
                        ).join('');
                    }
                    previewResults.style.display = 'block';
                } else {
                    previewMatches.innerHTML = `<p style="color: #dc2626;">Fehler: ${escapeHtml(result.error)}</p>`;
                    previewResults.style.display = 'block';
                }
            } catch (error) {
                previewMatches.innerHTML = `<p style="color: #dc2626;">Fehler: ${escapeHtml(error.message)}</p>`;
                previewResults.style.display = 'block';
            }
        });
    }

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