/**
 * QR import dialog — tab handlers for file, camera, and screen snip input.
 * Operates on a shared DialogState object passed from qr-import-dialog.ts.
 */

import type { ThemeData } from './types';
import { ensureJsQR, decodeImageData, imageToCanvas, escapeHtml } from './qr-decode';
import { parsePayload } from './qr-export-dialog';

// ---------------------------------------------------------------------------
// Shared dialog state interface
// ---------------------------------------------------------------------------

export interface DialogState {
  overlay: HTMLElement;
  parsedTheme: ThemeData | null;
  cameraStream: MediaStream | null;
  cameraAnimFrame: number;
  previewDiv: HTMLElement;
  statusDiv: HTMLElement;
  importBtn: HTMLButtonElement;
}

// ---------------------------------------------------------------------------
// Status / preview helpers
// ---------------------------------------------------------------------------

export function showStatus(st: DialogState, msg: string, isError = false): void {
  st.statusDiv.style.display = 'block';
  st.statusDiv.textContent = msg;
  st.statusDiv.style.color = isError ? '#e55' : 'var(--muted)';
}

export function clearStatus(st: DialogState): void {
  st.statusDiv.style.display = 'none';
  st.statusDiv.textContent = '';
}

export function showPreview(st: DialogState, theme: ThemeData): void {
  st.parsedTheme = theme;
  st.previewDiv.style.display = 'block';
  st.previewDiv.innerHTML = `<div style="padding:8px;border:1px solid var(--border);border-radius:8px;">
    <div style="font-size:13px;font-weight:600;">${escapeHtml(theme.name)}</div>
    <div style="font-size:11px;color:var(--muted);margin-top:2px;">Base: ${theme.base}</div>
    <div style="display:flex;gap:3px;margin-top:6px;">
      ${Object.values(theme.colors).filter(v => v).map(c =>
        `<span style="width:18px;height:18px;border-radius:50%;background:${c};border:1px solid rgba(128,128,128,0.3);display:inline-block;"></span>`
      ).join('')}
    </div>
  </div>`;
  st.importBtn.disabled = false;
  showStatus(st, 'QR decoded successfully!');
}

export function handleDecodedText(st: DialogState, text: string): void {
  const theme = parsePayload(text);
  if (theme) {
    showPreview(st, theme);
  } else {
    showStatus(st, 'Invalid theme data. Expected yu://theme/1 format.', true);
    st.previewDiv.style.display = 'none';
    st.importBtn.disabled = true;
  }
}

// ---------------------------------------------------------------------------
// File decode
// ---------------------------------------------------------------------------

export async function decodeFile(st: DialogState, file: File): Promise<void> {
  showStatus(st, 'Reading image...');
  try {
    await ensureJsQR();
  } catch {
    showStatus(st, 'Cannot load QR reader library', true);
    return;
  }
  try {
    const img = new Image();
    img.src = URL.createObjectURL(file);
    await new Promise<void>(r => { img.onload = () => r(); });
    const data = imageToCanvas(img);
    URL.revokeObjectURL(img.src);
    if (!data) { showStatus(st, 'Canvas error', true); return; }
    const text = decodeImageData(data);
    if (!text) { showStatus(st, 'QR code not found in image', true); return; }
    handleDecodedText(st, text);
  } catch (e) {
    showStatus(st, 'Error: ' + (e instanceof Error ? e.message : String(e)), true);
  }
}

// ---------------------------------------------------------------------------
// Camera
// ---------------------------------------------------------------------------

export function stopCamera(st: DialogState): void {
  if (st.cameraAnimFrame) { cancelAnimationFrame(st.cameraAnimFrame); st.cameraAnimFrame = 0; }
  if (st.cameraStream) {
    st.cameraStream.getTracks().forEach(t => t.stop());
    st.cameraStream = null;
  }
  const video = st.overlay.querySelector('#qr-camera-video') as HTMLVideoElement | null;
  if (video) video.srcObject = null;
  const startBtn = st.overlay.querySelector('#qr-camera-start') as HTMLElement | null;
  const stopBtn = st.overlay.querySelector('#qr-camera-stop') as HTMLElement | null;
  if (startBtn) startBtn.style.display = '';
  if (stopBtn) stopBtn.style.display = 'none';
}

function scanCameraFrame(st: DialogState, video: HTMLVideoElement): void {
  if (!st.cameraStream) return;
  const data = imageToCanvas(video);
  if (data) {
    const text = decodeImageData(data);
    if (text) {
      stopCamera(st);
      handleDecodedText(st, text);
      return;
    }
  }
  st.cameraAnimFrame = requestAnimationFrame(() => scanCameraFrame(st, video));
}

export async function startCamera(st: DialogState): Promise<void> {
  try {
    await ensureJsQR();
  } catch {
    showStatus(st, 'Cannot load QR reader library', true);
    return;
  }
  try {
    const video = st.overlay.querySelector('#qr-camera-video') as HTMLVideoElement;
    const startBtn = st.overlay.querySelector('#qr-camera-start') as HTMLElement;
    const stopBtn = st.overlay.querySelector('#qr-camera-stop') as HTMLElement;
    st.cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'environment', width: { ideal: 640 }, height: { ideal: 480 } },
    });
    video.srcObject = st.cameraStream;
    startBtn.style.display = 'none';
    stopBtn.style.display = '';
    showStatus(st, 'Scanning...');
    scanCameraFrame(st, video);
  } catch {
    showStatus(st, 'Camera access denied or not available', true);
  }
}

// ---------------------------------------------------------------------------
// Screen snip
// ---------------------------------------------------------------------------

export async function startSnip(st: DialogState): Promise<void> {
  try {
    await ensureJsQR();
  } catch {
    showStatus(st, 'Cannot load QR reader library', true);
    return;
  }

  let displayStream: MediaStream;
  try {
    displayStream = await navigator.mediaDevices.getDisplayMedia({
      video: { cursor: 'never' } as MediaTrackConstraints,
    });
  } catch {
    showStatus(st, 'Screen capture cancelled', true);
    return;
  }

  // Capture a single frame from the display stream
  const video = document.createElement('video');
  video.srcObject = displayStream;
  video.muted = true;
  await video.play();
  await new Promise(r => requestAnimationFrame(r));

  const captureCanvas = document.createElement('canvas');
  captureCanvas.width = video.videoWidth;
  captureCanvas.height = video.videoHeight;
  const captureCtx = captureCanvas.getContext('2d')!;
  captureCtx.drawImage(video, 0, 0);

  // Stop the display stream immediately
  displayStream.getTracks().forEach(t => t.stop());
  video.srcObject = null;

  // First try to decode the entire screen
  const fullData = captureCtx.getImageData(0, 0, captureCanvas.width, captureCanvas.height);
  const fullText = decodeImageData(fullData);
  if (fullText) {
    handleDecodedText(st, fullText);
    return;
  }

  // Show snipping overlay for region selection
  showSnipOverlay(st, captureCanvas);
}

function showSnipOverlay(st: DialogState, captureCanvas: HTMLCanvasElement): void {
  st.overlay.style.display = 'none';

  const snipOverlay = document.createElement('div');
  snipOverlay.style.cssText = 'position:fixed;inset:0;z-index:100000;cursor:crosshair;';

  // Background: the captured screen image with dim overlay
  const bgCanvas = document.createElement('canvas');
  bgCanvas.width = window.innerWidth;
  bgCanvas.height = window.innerHeight;
  bgCanvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;';
  const bgCtx = bgCanvas.getContext('2d')!;
  bgCtx.drawImage(captureCanvas, 0, 0, bgCanvas.width, bgCanvas.height);
  bgCtx.fillStyle = 'rgba(0,0,0,0.4)';
  bgCtx.fillRect(0, 0, bgCanvas.width, bgCanvas.height);
  snipOverlay.appendChild(bgCanvas);

  // Selection rectangle
  const selDiv = document.createElement('div');
  selDiv.style.cssText = 'position:absolute;border:2px solid #4af;background:rgba(74,143,255,0.1);display:none;pointer-events:none;';
  snipOverlay.appendChild(selDiv);

  // Instructions
  const instructions = document.createElement('div');
  instructions.style.cssText = 'position:absolute;top:16px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.7);color:#fff;padding:8px 16px;border-radius:8px;font-size:13px;pointer-events:none;';
  instructions.textContent = 'Drag to select the QR code area. Press Escape to cancel.';
  snipOverlay.appendChild(instructions);

  let startX = 0, startY = 0, dragging = false;

  snipOverlay.addEventListener('mousedown', (e) => {
    startX = e.clientX; startY = e.clientY; dragging = true;
    selDiv.style.display = 'block';
    selDiv.style.left = startX + 'px';
    selDiv.style.top = startY + 'px';
    selDiv.style.width = '0'; selDiv.style.height = '0';
  });

  snipOverlay.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const x = Math.min(startX, e.clientX);
    const y = Math.min(startY, e.clientY);
    selDiv.style.left = x + 'px'; selDiv.style.top = y + 'px';
    selDiv.style.width = Math.abs(e.clientX - startX) + 'px';
    selDiv.style.height = Math.abs(e.clientY - startY) + 'px';
  });

  snipOverlay.addEventListener('mouseup', (e) => {
    if (!dragging) return;
    dragging = false;
    const x = Math.min(startX, e.clientX);
    const y = Math.min(startY, e.clientY);
    const w = Math.abs(e.clientX - startX);
    const h = Math.abs(e.clientY - startY);

    snipOverlay.remove();
    st.overlay.style.display = '';

    if (w < 10 || h < 10) {
      showStatus(st, 'Selection too small. Please drag a larger area.', true);
      return;
    }

    // Map screen coords to capture canvas coords
    const scaleX = captureCanvas.width / window.innerWidth;
    const scaleY = captureCanvas.height / window.innerHeight;
    const cropCanvas = document.createElement('canvas');
    const cw = Math.round(w * scaleX);
    const ch = Math.round(h * scaleY);
    cropCanvas.width = cw; cropCanvas.height = ch;
    const cropCtx = cropCanvas.getContext('2d')!;
    cropCtx.drawImage(captureCanvas,
      Math.round(x * scaleX), Math.round(y * scaleY), cw, ch,
      0, 0, cw, ch);

    const regionData = cropCtx.getImageData(0, 0, cw, ch);
    const text = decodeImageData(regionData);
    if (text) {
      handleDecodedText(st, text);
    } else {
      showStatus(st, 'QR code not found in selected area. Try a different region.', true);
    }
  });

  // Escape to cancel
  function escHandler(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      snipOverlay.remove();
      st.overlay.style.display = '';
      document.removeEventListener('keydown', escHandler);
    }
  }
  document.addEventListener('keydown', escHandler);
  document.body.appendChild(snipOverlay);
}
