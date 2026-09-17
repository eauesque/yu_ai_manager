const state = {
  repairDir: '',
  zipPath: '',
  updateVerified: false,
};

function tr(key, fallback) {
  if (typeof window.tr === 'function') return window.tr(key, fallback);
  return fallback;
}

function resultEl() {
  return document.getElementById('diagnosticsResult');
}

function setResult(text) {
  const el = resultEl();
  if (el) el.textContent = text;
}

function setDoctorPreview(text) {
  const el = document.getElementById('diagnosticsDoctorPreview');
  if (el) el.textContent = text;
}

async function apiPost(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.error || response.statusText);
  return data;
}

async function apiPostForm(path, formData) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
    body: formData,
  });
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    const err = new Error(data.error || response.statusText);
    err.code = data.code;
    throw err;
  }
  return data;
}

async function confirmAction(message, options) {
  if (typeof window.customConfirm !== 'function') {
    throw new Error('window.customConfirm is not available');
  }
  return window.customConfirm(message, options);
}

function setButtonsEnabled(enabled) {
  for (const id of ['diagnosticsOpenFolder', 'diagnosticsZipRepair', 'diagnosticsCopyDiscord']) {
    const button = document.getElementById(id);
    if (button) button.disabled = !enabled;
  }
}

function selectedUpdateFile() {
  const input = document.getElementById('diagnosticsUpdateFile');
  return input?.files?.[0] || null;
}

function setUpdateResult(text) {
  const el = document.getElementById('diagnosticsUpdateResult');
  if (el) el.textContent = text;
}

async function refreshSafeModeBanner() {
  const banner = document.getElementById('diagnosticsSafeModeBanner');
  if (!banner) return;
  const response = await fetch('/api/diagnostics/safe-mode', {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  });
  const data = await response.json();
  banner.hidden = !(response.ok && data.safe_mode === true);
}

async function verifyUpdate() {
  const file = selectedUpdateFile();
  if (!file) {
    setUpdateResult(tr('diagnostics.update_no_file', 'Please select update.zip file'));
    return;
  }
  const form = new FormData();
  form.append('file', file);
  const data = await apiPostForm('/api/update/verify', form);
  state.updateVerified = true;
  const applyButton = document.getElementById('diagnosticsApplyUpdate');
  if (applyButton) applyButton.disabled = false;
  setUpdateResult(`${tr('diagnostics.update_verified', 'Verification OK')}\n${JSON.stringify(data.manifest || {}, null, 2)}`);
}

async function applyUpdate() {
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

async function rollbackUpdate() {
  const ok = await confirmAction(tr('diagnostics.update_rollback_confirm', 'Restore from the latest update backup.'), { danger: true });
  if (!ok) return;
  const data = await apiPost('/api/update/rollback');
  setUpdateResult(`${tr('diagnostics.update_rollback_done', 'Rollback completed. Please restart the app.')}\n${JSON.stringify(data, null, 2)}`);
}

async function createBugReport() {
  const ok = await confirmAction(tr('diagnostics.confirm_create', 'Create a redacted diagnostics repair folder?'));
  if (!ok) return;
  setResult(tr('diagnostics.running', 'Creating diagnostics package...'));
  const data = await apiPost('/api/diagnostics/bug-report');
  state.repairDir = data.repair_dir || '';
  state.zipPath = '';
  setButtonsEnabled(Boolean(state.repairDir));
  setResult(`${tr('diagnostics.created', 'Created repair folder')}\n${state.repairDir}`);
}

let _doctorPollTimer = null;

function _stopDoctorPoll() {
  if (_doctorPollTimer !== null) {
    clearTimeout(_doctorPollTimer);
    _doctorPollTimer = null;
  }
}

async function _pollDoctorJob(jobId, attempt) {
  let data;
  try {
    const response = await fetch(`/api/diagnostics/doctor/${jobId}`, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    data = await response.json();
  } catch (err) {
    setDoctorPreview(`${tr('diagnostics.doctor_poll_error', 'Poll error')}: ${err.message}`);
    _setDoctorRunning(false);
    return;
  }

  if (data.status === 'running') {
    const dots = '.'.repeat((attempt % 3) + 1);
    setDoctorPreview(`${tr('diagnostics.doctor_running', 'Running environment diagnosis')}${dots}`);
    _doctorPollTimer = setTimeout(() => _pollDoctorJob(jobId, attempt + 1), 3000);
    return;
  }

  _setDoctorRunning(false);
  if (data.status === 'error') {
    setDoctorPreview('');
    setResult(`${tr('diagnostics.doctor_failed', 'Diagnosis failed')}: ${data.error}`);
    return;
  }

  const summary = data.summary || {};
  setDoctorPreview(data.report_md || '');
  setResult(`${tr('diagnostics.doctor_created', 'Created doctor report')}\nErrors: ${summary.errors ?? 0}, Warnings: ${summary.warnings ?? 0}`);
}

function _setDoctorRunning(running) {
  const btn = document.getElementById('diagnosticsRunDoctor');
  if (btn) btn.disabled = running;
}

async function runDoctor() {
  const ok = await confirmAction(tr('diagnostics.confirm_doctor', 'Run environment diagnosis?'));
  if (!ok) return;
  _stopDoctorPoll();
  _setDoctorRunning(true);
  setDoctorPreview(tr('diagnostics.doctor_running', 'Running environment diagnosis') + '.');
  setResult('');
  let data;
  try {
    data = await apiPost('/api/diagnostics/doctor');
  } catch (err) {
    _setDoctorRunning(false);
    setDoctorPreview('');
    throw err;
  }
  _pollDoctorJob(data.job_id, 0);
}

async function openFolder() {
  if (!state.repairDir) return;
  const ok = await confirmAction(tr('diagnostics.confirm_open', 'Open the repair folder?'));
  if (!ok) return;
  await apiPost('/api/diagnostics/open-repair-folder', { repair_dir: state.repairDir });
}

async function zipRepair() {
  if (!state.repairDir) return;
  const ok = await confirmAction(tr('diagnostics.confirm_zip', 'Create a zip file for this repair folder?'));
  if (!ok) return;
  const data = await apiPost('/api/diagnostics/zip-repair', { repair_dir: state.repairDir });
  state.zipPath = data.zip_path || '';
  setResult(`${tr('diagnostics.zipped', 'Created zip file')}\n${state.zipPath}`);
}

async function copyDiscordMessage() {
  if (!state.repairDir) return;
  const path = state.zipPath || state.repairDir;
  const message = `YU AI Manager diagnostics package:\n${path}`;
  await navigator.clipboard.writeText(message);
  setResult(`${tr('diagnostics.copied', 'Copied message')}\n${message}`);
}

document.getElementById('diagnosticsCreateBugReport')?.addEventListener('click', () => {
  createBugReport().catch((error) => setResult(String(error.message || error)));
});
document.getElementById('diagnosticsRunDoctor')?.addEventListener('click', () => {
  runDoctor().catch((error) => setResult(String(error.message || error)));
});
document.getElementById('diagnosticsOpenFolder')?.addEventListener('click', () => {
  openFolder().catch((error) => setResult(String(error.message || error)));
});
document.getElementById('diagnosticsZipRepair')?.addEventListener('click', () => {
  zipRepair().catch((error) => setResult(String(error.message || error)));
});
document.getElementById('diagnosticsCopyDiscord')?.addEventListener('click', () => {
  copyDiscordMessage().catch((error) => setResult(String(error.message || error)));
});
document.getElementById('diagnosticsUpdateFile')?.addEventListener('change', () => {
  state.updateVerified = false;
  const applyButton = document.getElementById('diagnosticsApplyUpdate');
  if (applyButton) applyButton.disabled = true;
  setUpdateResult('');
});
document.getElementById('diagnosticsVerifyUpdate')?.addEventListener('click', () => {
  verifyUpdate().catch((error) => setUpdateResult(`${error.code ? `${error.code}: ` : ''}${String(error.message || error)}`));
});
document.getElementById('diagnosticsApplyUpdate')?.addEventListener('click', () => {
  applyUpdate().catch((error) => setUpdateResult(`${error.code ? `${error.code}: ` : ''}${String(error.message || error)}`));
});
document.getElementById('diagnosticsRollbackUpdate')?.addEventListener('click', () => {
  rollbackUpdate().catch((error) => setUpdateResult(`${error.code ? `${error.code}: ` : ''}${String(error.message || error)}`));
});

refreshSafeModeBanner().catch(() => {});
