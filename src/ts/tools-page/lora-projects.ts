/**
 * tools-page/lora-projects.ts — LoRA project management UI.
 */

import { apiFetch } from './api';

interface LoraProject {
  id: number;
  name: string;
  concept: string;
  base_model?: string;
  file_count?: number;
  created_at?: string;
}

async function loadLoraProjects(): Promise<void> {
  const list = document.getElementById('loraProjectList');
  if (!list) return;
  try {
    const res = await apiFetch('/ext/lora-dataset/projects');
    const json = await res.json();
    const data = json.data ?? json;
    const projects: LoraProject[] = data.projects ?? [];
    if (projects.length === 0) {
      list.textContent = 'No LoRA projects';
      list.style.color = 'var(--muted)';
      return;
    }
    list.textContent = '';
    list.style.color = '';
    projects.forEach(p => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border,#333);';

      const name = document.createElement('strong');
      name.style.cssText = 'flex:1;font-size:13px;';
      name.textContent = p.name;

      const concept = document.createElement('span');
      concept.style.cssText = 'font-size:11px;color:var(--muted);';
      concept.textContent = p.concept || '';

      const count = document.createElement('span');
      count.style.cssText = 'font-size:11px;color:var(--accent);';
      count.textContent = (p.file_count ?? 0) + ' files';

      const exportBtn = document.createElement('button');
      exportBtn.className = 'btn btn-sm';
      exportBtn.textContent = 'Export';
      exportBtn.style.cssText = 'font-size:10px;padding:2px 6px;';
      exportBtn.addEventListener('click', async () => {
        exportBtn.textContent = '...';
        try {
          await apiFetch(`/ext/lora-dataset/projects/${p.id}/export`, { method: 'POST' });
          exportBtn.textContent = '\u2713';
        } catch { exportBtn.textContent = '\u2717'; }
        setTimeout(() => { exportBtn.textContent = 'Export'; }, 2000);
      });

      const delBtn = document.createElement('button');
      delBtn.className = 'btn btn-sm';
      delBtn.textContent = '\u00d7';
      delBtn.style.cssText = 'font-size:12px;padding:2px 6px;color:#e74c3c;';
      delBtn.addEventListener('click', async () => {
        if (!confirm(`Delete project "${p.name}"?`)) return;
        await apiFetch(`/ext/lora-dataset/projects/${p.id}`, { method: 'DELETE' });
        loadLoraProjects();
      });

      row.appendChild(name);
      row.appendChild(concept);
      row.appendChild(count);
      row.appendChild(exportBtn);
      row.appendChild(delBtn);
      list.appendChild(row);
    });
  } catch {
    list.textContent = 'LoRA extension not available';
    list.style.color = 'var(--muted)';
  }
}

function initLoraCreate(): void {
  const btn = document.getElementById('loraCreateBtn');
  const nameInput = document.getElementById('loraNewName') as HTMLInputElement | null;
  const conceptInput = document.getElementById('loraNewConcept') as HTMLInputElement | null;
  if (!btn || !nameInput) return;
  btn.addEventListener('click', async () => {
    const name = nameInput.value.trim();
    if (!name) return;
    try {
      await apiFetch('/ext/lora-dataset/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          concept: conceptInput?.value.trim() || '',
        }),
      });
      nameInput.value = '';
      if (conceptInput) conceptInput.value = '';
      loadLoraProjects();
    } catch (e) {
      console.error('Failed to create LoRA project:', e);
    }
  });
}

if (document.getElementById('loraCard')) {
  loadLoraProjects();
  initLoraCreate();
}
