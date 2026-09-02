/**
 * Tools page — SVG Rasterize panel.
 * POST /api/svg/rasterize — convert SVG to PNG or WebP.
 * Returns base64-encoded image; downloads via Blob URL.
 */

interface RasterizeResponse {
  image_b64: string;
  format: string;
  width: number;
  height: number;
}

function setStatus(msg: string, isError = false): void {
  const el = document.getElementById('svgConvertStatus');
  if (!el) return;
  el.textContent = msg;
  el.style.color = isError ? '#dc2626' : '#6b7280';
}

export function initSvgRasterize(): void {
  const convertBtn = document.getElementById('svgConvertBtn');
  if (!convertBtn) return;

  convertBtn.addEventListener('click', () => {
    const fileInput = document.getElementById('svgFileInput') as HTMLInputElement | null;
    const formatEl = document.getElementById('svgFormat') as HTMLSelectElement | null;
    const widthEl = document.getElementById('svgWidth') as HTMLInputElement | null;
    const heightEl = document.getElementById('svgHeight') as HTMLInputElement | null;

    const file = fileInput?.files?.[0];
    if (!file) {
      setStatus('No file selected', true);
      return;
    }

    const format = (formatEl?.value ?? 'png') as 'png' | 'webp';
    const width = widthEl?.value ? parseInt(widthEl.value, 10) : undefined;
    const height = heightEl?.value ? parseInt(heightEl.value, 10) : undefined;

    setStatus('Converting…');
    convertBtn.setAttribute('disabled', '');

    const reader = new FileReader();
    reader.onload = () => {
      const svgData = reader.result as string;
      const body: Record<string, unknown> = { svg_data: svgData, format };
      if (width) body.width = width;
      if (height) body.height = height;

      void fetch('/api/svg/rasterize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
        .then((r) => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          return r.json() as Promise<RasterizeResponse>;
        })
        .then((data) => {
          const byteChars = atob(data.image_b64);
          const bytes = new Uint8Array(byteChars.length);
          for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
          const mime = format === 'webp' ? 'image/webp' : 'image/png';
          const blob = new Blob([bytes], { type: mime });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          const baseName = file.name.replace(/\.svg$/i, '');
          a.href = url;
          a.download = `${baseName}-rasterized.${format}`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          setStatus(`Done — ${data.width}×${data.height}`);
        })
        .catch((err: Error) => setStatus(err.message, true))
        .finally(() => convertBtn.removeAttribute('disabled'));
    };
    reader.readAsText(file);
  });
}
