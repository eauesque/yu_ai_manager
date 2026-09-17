/**
 * Bridge Sed — lightweight sed (stream editor) for bridge prompt textareas.
 */

interface ParsedDelimited {
  value: string;
  end: number;
}

interface ParsedAddr {
  re: RegExp;
  end: number;
}

interface SedSubCmd {
  cmd: 's';
  addr: RegExp | null;
  pattern: string;
  replacement: string;
  flags: string;
}

interface SedDeleteCmd {
  cmd: 'd';
  addr: RegExp;
  negate: boolean;
}

interface SedInsertCmd {
  cmd: 'a' | 'i';
  addr: RegExp;
  text: string;
}

interface SedTranslitCmd {
  cmd: 'y';
  source: string;
  dest: string;
}

type SedCmd = SedSubCmd | SedDeleteCmd | SedInsertCmd | SedTranslitCmd;

export interface SedAttachConfig {
  input: HTMLInputElement;
  getInput: () => string;
  setInput: (v: string) => void;
  toast?: (msg: string) => void;
}

interface SedCallbacks {
  toast: (msg: string) => void;
}

function _parseDelimited(expr: string, pos: number, delim: string): ParsedDelimited | null {
  let cur = '';
  let i = pos;
  while (i < expr.length) {
    if (expr[i] === '\\' && i + 1 < expr.length && expr[i + 1] === delim) {
      cur += delim;
      i += 2;
    } else if (expr[i] === delim) {
      return { value: cur, end: i + 1 };
    } else {
      cur += expr[i];
      i++;
    }
  }
  return null;
}

function _parseAddr(expr: string, pos: number): ParsedAddr | null {
  if (pos >= expr.length || expr[pos] !== '/') return null;
  const r = _parseDelimited(expr, pos + 1, '/');
  if (!r) return null;
  try {
    return { re: new RegExp(r.value), end: r.end };
  } catch {
    return null;
  }
}

function _parseSub(expr: string): SedSubCmd | null {
  if (expr.length < 4 || expr[0] !== 's') return null;
  const delim = expr[1];
  const r1 = _parseDelimited(expr, 2, delim);
  if (!r1) return null;
  const r2 = _parseDelimited(expr, r1.end, delim);
  if (!r2) return null;
  const flags = expr.substring(r2.end);
  if (!/^[gi]*$/.test(flags)) return null;
  return { cmd: 's', addr: null, pattern: r1.value, replacement: r2.value, flags };
}

function _parseExpr(expr: string): SedCmd | null {
  if (expr[0] === '/') {
    const addr = _parseAddr(expr, 0);
    if (!addr) return null;
    const rest = expr.substring(addr.end);
    if (rest === '!d') return { cmd: 'd', addr: addr.re, negate: true };
    if (rest === 'd') return { cmd: 'd', addr: addr.re, negate: false };
    const mA = rest.match(/^a\\([\s\S]*)$/);
    if (mA) return { cmd: 'a', addr: addr.re, text: mA[1] };
    const mI = rest.match(/^i\\([\s\S]*)$/);
    if (mI) return { cmd: 'i', addr: addr.re, text: mI[1] };
    if (rest.length >= 4 && rest[0] === 's') {
      const sub = _parseSub(rest);
      if (sub) {
        sub.addr = addr.re;
        return sub;
      }
    }
    return null;
  }
  if (expr.length >= 4 && expr[0] === 'y') {
    const yDelim = expr[1];
    const r1 = _parseDelimited(expr, 2, yDelim);
    if (!r1) return null;
    const r2 = _parseDelimited(expr, r1.end, yDelim);
    if (!r2) return null;
    if (expr.substring(r2.end).trim() !== '') return null;
    return { cmd: 'y', source: r1.value, dest: r2.value };
  }
  if (expr.length >= 4 && expr[0] === 's') {
    return _parseSub(expr);
  }
  return null;
}

function exec(exprStr: string, text: string, callbacks: SedCallbacks): string | null {
  const toast = callbacks.toast || (() => {});
  const parsed = _parseExpr(exprStr);
  if (!parsed) {
    toast('sed error: invalid syntax');
    return null;
  }
  const lines = text.split('\n');

  switch (parsed.cmd) {
    case 's': {
      let re: RegExp;
      try {
        re = new RegExp(parsed.pattern, parsed.flags);
      } catch (err) {
        toast('sed error: ' + (err as Error).message);
        return null;
      }
      let changed = 0;
      const newLines = lines.map((line) => {
        if (parsed.addr && !parsed.addr.test(line)) return line;
        const newLine = line.replace(re, parsed.replacement);
        if (newLine !== line) changed++;
        return newLine;
      });
      if (changed === 0) {
        toast('sed: no match');
        return null;
      }
      toast('sed: ' + changed + ' line(s) changed');
      return newLines.join('\n');
    }
    case 'd': {
      const kept: string[] = [];
      let removed = 0;
      lines.forEach((line) => {
        const match = parsed.addr.test(line);
        if ((match ? 1 : 0) ^ (parsed.negate ? 1 : 0)) {
          removed++;
        } else {
          kept.push(line);
        }
      });
      if (removed === 0) {
        toast('sed: no match');
        return null;
      }
      toast(
        parsed.negate
          ? 'sed: kept ' + kept.length + ' line(s)'
          : 'sed: deleted ' + removed + ' line(s)',
      );
      return kept.join('\n');
    }
    case 'y': {
      if (parsed.source.length !== parsed.dest.length) {
        toast('sed error: y source/dest length mismatch');
        return null;
      }
      const map: Record<string, string> = {};
      for (let ci = 0; ci < parsed.source.length; ci++) {
        map[parsed.source[ci]] = parsed.dest[ci];
      }
      let changed = 0;
      const newLines = lines.map((line) => {
        const newLine = line
          .split('')
          .map((ch) => (map[ch] !== undefined ? map[ch] : ch))
          .join('');
        if (newLine !== line) changed++;
        return newLine;
      });
      if (changed === 0) {
        toast('sed: no match');
        return null;
      }
      toast('sed: transliterated ' + changed + ' line(s)');
      return newLines.join('\n');
    }
    case 'a':
    case 'i': {
      let inserted = 0;
      const newLines: string[] = [];
      lines.forEach((line) => {
        if (parsed.addr.test(line)) {
          if (parsed.cmd === 'i') {
            newLines.push(parsed.text);
            inserted++;
          }
          newLines.push(line);
          if (parsed.cmd === 'a') {
            newLines.push(parsed.text);
            inserted++;
          }
        } else {
          newLines.push(line);
        }
      });
      if (inserted === 0) {
        toast('sed: no match');
        return null;
      }
      toast('sed: inserted ' + inserted + ' line(s)');
      return newLines.join('\n');
    }
    default:
      toast('sed error: unknown command');
      return null;
  }
}

function attach(config: SedAttachConfig): { run: () => void } {
  const sedInput = config.input;
  const getValue = config.getInput;
  const setValue = config.setInput;
  const toast = config.toast || ((msg: string) => alert(msg));

  function run(): void {
    const expr = sedInput.value.trim();
    if (!expr) return;
    const text = getValue();
    const result = exec(expr, text, { toast });
    if (result !== null) setValue(result);
  }

  sedInput.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      run();
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      const bar = sedInput.closest('.bridge-sed-bar') as HTMLElement | null;
      if (bar) bar.style.display = 'none';
    }
  });

  return { run };
}

export const BridgeSed = { exec, attach };
