/* JalDrishti Report Module — PDF/CSV/JSON Export */

class ReportModule {
  constructor() { this.init(); }

  init() {
    this.setupModalToggle();
    this.setupFormSubmit();
  }

  setupModalToggle() {
    const btn = document.getElementById('reportBtn');
    const modal = document.getElementById('reportModal');
    const closeBtn = document.querySelector('.modal-close');
    if (btn) btn.addEventListener('click', () => modal?.classList.add('active'));
    if (closeBtn) closeBtn.addEventListener('click', () => modal?.classList.remove('active'));
    modal?.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
  }

  setupFormSubmit() {
    const form = document.getElementById('reportForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = form.querySelector('button[type="submit"]');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Generating...'; }

      const formData = new FormData(form);
      const params = {
        scope: formData.get('scope'),
        scope_value: formData.get('scope_value'),
        format: formData.get('format'),
        start_year: parseInt(formData.get('start_year')) || null,
        end_year: parseInt(formData.get('end_year')) || null,
        parameters: Array.from(formData.getAll('parameters'))
      };

      try {
        // FIX: was '/report/generate', now '/api/report/generate'
        const response = await app.fetch('/api/report/generate', {
          method: 'POST',
          body: JSON.stringify(params)
        });

        if (response.success && response.data?.report_id) {
          // FIX: download URL also needs /api prefix
          const downloadUrl = `http://localhost:5000/api/report/download/${response.data.report_id}`;
          window.open(downloadUrl, '_blank');
          document.getElementById('reportModal')?.classList.remove('active');
        } else {
          alert('Report generation failed: ' + (response.error || 'Unknown error'));
        }
      } catch (error) {
        alert('Failed to generate report. Make sure the backend is running.');
      } finally {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Generate Report'; }
      }
    });
  }
}
