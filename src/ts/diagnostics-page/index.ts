export {};

const state = {
  repairDir: '',
  zipPath: '',
  updateVerified: false,
};

function tr(key: string, fallback: string): string {
  return window.tr(key, fallback);
}

function setResult(text: string): void {
  const el = document.getElementById('diagnosticsResult');
  if (el) el.textContent = text;
}

function setDoctorPreview(text: string): void {
  const el = document.getElementById('diagnosticsDoctorPreview');
  if (el) el.textContent = text;
}

async function apiPost(path: string, body?: Record<string, unknown>): Promise<Record<string, unknown>> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    body: JSON.stringify(body ?? {}),
  });
  const data = await res.json() as Record<string, unknown>;
  if (!res.ok || data['ok'] === false) throw new Error(String(data['error'] || res.statusText));
  return data;
}

async function apiPostForm(path: string, form: FormData): Promise<Record<string, unknown>> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    body: form,
  });
  const data = await res.json() as Record<string, unknown> & { code?: string };
  if (!res.ok || data['ok'] === false) {
    throw Object.assign(new Error(String(data['error'] || res.statusText)), { code: data['code'] });
  }
  return data;
}

async function confirmAction(message: string, options?: { danger?: boolean }): Promise<boolean> {
  return window.customConfirm(message, options);
}

function setButtonsEnabled(enabled: boolean): void {
  for (const id of ['diagnosticsOpenFolder', 'diagnosticsZipRepair', 'diagnosticsCopyDiscord']) {
    const btn = document.getElementById(id) as HTMLButtonElement | null;
    if (btn) btn.disabled = !enabled;
  }
}

function selectedUpdateFile(): File | null {
  const input = document.getElementById('diagnosticsUpdateFile') as HTMLInputElement | null;
  return input?.files?.[0] ?? null;
}

function setUpdateResult(text: string): void {
  const el = document.getElementById('diagnosticsUpdateResult');
  if (el) el.textContent = text;
}

async function refreshSafeModeBanner(): Promise<void> {
  const banner = document.getElementById('diagnosticsSafeModeBanner');
  if (!banner) return;
  const res = await fetch('/api/diagnostics/safe-mode', { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
  const data = await res.json() as { safe_mode?: boolean };
  banner.hidden = !(res.ok && data.safe_mode === true);
}

async function verifyUpdate(): Promise<void> {
  const file = selectedUpdateFile();
  if (!file) { setUpdateResult(tr('diagnostics.update_no_file', 'Please select update.zip file')); return; }
  const form = new FormData();
  form.append('file', file);
  const data = await apiPostForm('/api/update/verify', form);
  state.updateVerified = true;
  const applyBtn = document.getElementById('diagnosticsApplyUpdate') as HTMLButtonElement | null;
  if (applyBtn) applyBtn.disabled = false;
  setUpdateResult(`${tr('diagnostics.update_verified', 'Verification OK')}\n${JSON.stringify(data['manifest'] ?? {}, null, 2)}`);
}

async function applyUpdate(): Promise<void> {
  const file = selectedUpdateFile();
  if (!file || !state.updateVerified) return;
  const ok = await confirmAction(
    tr('diagnostics.update_apply_confirm', 'Apply the signed update. The app may require a restart after applying.'),
    { danger: true },
  );
  if (!ok) return;
  const form = new FormData();
  form.append('file', file);
  const data = await apiPostForm('/api/update/apply', form);
  setUpdateResult(`${tr('diagnostics.update_applied', 'Update applied. Please restart the app.')}\n${JSON.stringify(data, null, 2)}`);
}

async function rollbackUpdate(): Promise<void> {
  const ok = await confirmAction(tr('diagnostics.update_rollback_confirm', 'Restore from the latest update backup.'), { danger: true });
  if (!ok) return;
  const data = await apiPost('/api/update/rollback');
  setUpdateResult(`${tr('diagnostics.update_rollback_done', 'Rollback completed. Please restart the app.')}\n${JSON.stringify(data, null, 2)}`);
}

async function createBugReport(): Promise<void> {
  const ok = await confirmAction(tr('diagnostics.confirm_create', 'Create a redacted diagnostics repair folder?'));
  if (!ok) return;
  setResult(tr('diagnostics.running', 'Creating diagnostics package...'));
  const data = await apiPost('/api/diagnostics/bug-report');
  state.repairDir = String(data['repair_dir'] ?? '');
  state.zipPath = '';
  setButtonsEnabled(Boolean(state.repairDir));
  setResult(`${tr('diagnostics.created', 'Created repair folder')}\n${state.repairDir}`);
}

let _doctorPollTimer: ReturnType<typeof setTimeout> | null = null;

function _stopDoctorPoll(): void {
  if (_doctorPollTimer !== null) { clearTimeout(_doctorPollTimer); _doctorPollTimer = null; }
}

async function _pollDoctorJob(jobId: string, attempt: number): Promise<void> {
  let data: Record<string, unknown>;
  try {
    const res = await fetch(`/api/diagnostics/doctor/${jobId}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    data = await res.json() as Record<string, unknown>;
  } catch (err) {
    setDoctorPreview(`${tr('diagnostics.doctor_poll_error', 'Poll error')}: ${(err as Error).message}`);
    _setDoctorRunning(false);
    return;
  }
  if (data['status'] === 'running') {
    const dots = '.'.repeat((attempt % 3) + 1);
    setDoctorPreview(`${tr('diagnostics.doctor_running', 'Running environment diagnosis')}${dots}`);
    _doctorPollTimer = setTimeout(() => { void _pollDoctorJob(jobId, attempt + 1); }, 3000);
    return;
  }
  _setDoctorRunning(false);
  if (data['status'] === 'error') {
    setDoctorPreview('');
    setResult(`${tr('diagnostics.doctor_failed', 'Diagnosis failed')}: ${String(data['error'])}`);
    return;
  }
  const summary = (data['summary'] as Record<string, unknown>) ?? {};
  setDoctorPreview(String(data['report_md'] ?? ''));
  setResult(`${tr('diagnostics.doctor_created', 'Created doctor report')}\nErrors: ${summary['errors'] ?? 0}, Warnings: ${summary['warnings'] ?? 0}`);
}

function _setDoctorRunning(running: boolean): void {
  const btn = document.getElementById('diagnosticsRunDoctor') as HTMLButtonElement | null;
  if (btn) btn.disabled = running;
}

async function runDoctor(): Promise<void> {
  const ok = await confirmAction(tr('diagnostics.confirm_doctor', 'Run environment diagnosis?'));
  if (!ok) return;
  _stopDoctorPoll();
  _setDoctorRunning(true);
  setDoctorPreview(tr('diagnostics.doctor_running', 'Running environment diagnosis') + '.');
  setResult('');
  let data: Record<string, unknown>;
  try {
    data = await apiPost('/api/diagnostics/doctor');
  } catch (err) {
    _setDoctorRunning(false);
    setDoctorPreview('');
    throw err;
  }
  void _pollDoctorJob(String(data['job_id']), 0);
}

async function openFolder(): Promise<void> {
  if (!state.repairDir) return;
  const ok = await confirmAction(tr('diagnostics.confirm_open', 'Open the repair folder?'));
  if (!ok) return;
  await apiPost('/api/diagnostics/open-repair-folder', { repair_dir: state.repairDir });
}

async function zipRepair(): Promise<void> {
  if (!state.repairDir) return;
  const ok = await confirmAction(tr('diagnostics.confirm_zip', 'Create a zip file for this repair folder?'));
  if (!ok) return;
  const data = await apiPost('/api/diagnostics/zip-repair', { repair_dir: state.repairDir });
  state.zipPath = String(data['zip_path'] ?? '');
  setResult(`${tr('diagnostics.zipped', 'Created zip file')}\n${state.zipPath}`);
}

async function copyDiscordMessage(): Promise<void> {
  if (!state.repairDir) return;
  const path = state.zipPath || state.repairDir;
  const message = `YU AI Manager diagnostics package:\n${path}`;
  await navigator.clipboard.writeText(message);
  setResult(`${tr('diagnostics.copied', 'Copied message')}\n${message}`);
}

document.getElementById('diagnosticsCreateBugReport')?.addEventListener('click', () => {
  createBugReport().catch((e: unknown) => setResult(String((e as Error).message || e)));
});
document.getElementById('diagnosticsRunDoctor')?.addEventListener('click', () => {
  runDoctor().catch((e: unknown) => setResult(String((e as Error).message || e)));
});
document.getElementById('diagnosticsOpenFolder')?.addEventListener('click', () => {
  openFolder().catch((e: unknown) => setResult(String((e as Error).message || e)));
});
document.getElementById('diagnosticsZipRepair')?.addEventListener('click', () => {
  zipRepair().catch((e: unknown) => setResult(String((e as Error).message || e)));
});
document.getElementById('diagnosticsCopyDiscord')?.addEventListener('click', () => {
  copyDiscordMessage().catch((e: unknown) => setResult(String((e as Error).message || e)));
});
document.getElementById('diagnosticsUpdateFile')?.addEventListener('change', () => {
  state.updateVerified = false;
  const applyBtn = document.getElementById('diagnosticsApplyUpdate') as HTMLButtonElement | null;
  if (applyBtn) applyBtn.disabled = true;
  setUpdateResult('');
});
document.getElementById('diagnosticsVerifyUpdate')?.addEventListener('click', () => {
  verifyUpdate().catch((e: unknown) => {
    const err = e as { code?: string; message?: string };
    setUpdateResult(`${err.code ? `${err.code}: ` : ''}${String(err.message || e)}`);
  });
});
document.getElementById('diagnosticsApplyUpdate')?.addEventListener('click', () => {
  applyUpdate().catch((e: unknown) => {
    const err = e as { code?: string; message?: string };
    setUpdateResult(`${err.code ? `${err.code}: ` : ''}${String(err.message || e)}`);
  });
});
document.getElementById('diagnosticsRollbackUpdate')?.addEventListener('click', () => {
  rollbackUpdate().catch((e: unknown) => {
    const err = e as { code?: string; message?: string };
    setUpdateResult(`${err.code ? `${err.code}: ` : ''}${String(err.message || e)}`);
  });
});

refreshSafeModeBanner().catch(() => {});
