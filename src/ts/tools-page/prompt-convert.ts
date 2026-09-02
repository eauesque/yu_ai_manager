/**
 * tools-page/prompt-convert.ts — Prompt conversion and analysis UI.
 */

import { apiFetch } from './api';
import { copyToClipboard } from '../shared/clipboard';

function showResult(text: string): void {
  const resultDiv = document.getElementById('promptConvertResult');
  const output = document.getElementById('promptConvertOutput');
  if (!resultDiv || !output) return;
  output.textContent = text;
  resultDiv.style.display = '';
}

async function convert(mode: string): Promise<void> {
  const input = document.getElementById('promptConvertInput') as HTMLTextAreaElement | null;
  if (!input?.value.trim()) return;
  try {
    const res = await apiFetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: input.value, mode }),
    });
    const json = await res.json();
    const data = json.data ?? json;
    showResult(data.converted || data.result || JSON.stringify(data, null, 2));
  } catch (e) {
    showResult('Conversion failed: ' + String(e));
  }
}

async function analyze(): Promise<void> {
  const input = document.getElementById('promptConvertInput') as HTMLTextAreaElement | null;
  if (!input?.value.trim()) return;
  try {
    const res = await apiFetch('/ext/prompt-sim/emphasis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: input.value }),
    });
    const json = await res.json();
    const data = json.data ?? json;
    // Format analysis output
    const lines: string[] = [];
    if (data.tokens) {
      lines.push(`Tokens: ${data.tokens.length}`);
      (data.tokens as Array<{ text: string; weight: number }>)
        .filter(t => t.weight !== 1.0)
        .forEach(t => lines.push(`  ${t.text}: weight ${t.weight.toFixed(2)}`));
    }
    if (data.warnings?.length) {
      lines.push('\nWarnings:');
      (data.warnings as string[]).forEach(w => lines.push(`  ⚠ ${w}`));
    }
    showResult(lines.join('\n') || JSON.stringify(data, null, 2));
  } catch (e) {
    showResult('Analysis failed: ' + String(e));
  }
}

function initPromptConvert(): void {
  document.getElementById('promptToNaiBtn')?.addEventListener('click', () => convert('sd_to_nai'));
  document.getElementById('promptToSdBtn')?.addEventListener('click', () => convert('nai_to_sd'));
  document.getElementById('promptAnalyzeBtn')?.addEventListener('click', () => analyze());
  document.getElementById('promptCopyResultBtn')?.addEventListener('click', () => {
    const output = document.getElementById('promptConvertOutput');
    if (output?.textContent) {
      void copyToClipboard(output.textContent).catch(() => {});
    }
  });
}

if (document.getElementById('promptConvertCard')) {
  initPromptConvert();
}
