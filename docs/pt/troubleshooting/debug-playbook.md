# Manual de Depuração do YU AI Manager

## Quick start

```bash
# Executar todo o diagnóstico
python debug_check.py

# Especificar DB
python debug_check.py --db /path/to/tags.db

# Checagem simplificada (omite sintaxe/Extensions)
python debug_check.py --quick
```

---

## Problemas comuns e soluções

### 1. config.json corrompido (problema de backslash)

**Sintoma:** JSONDecodeError na inicialização do servidor
**Causa:** digitação manual de paths do Windows gera escapes inválidos como `\U`, `\w`
**Solução:** é reparado automaticamente na inicialização. Para reparar manualmente:
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. scan-all pula uma pasta específica

**Sintoma:** no "scan de todas as pastas", alguma pasta não é processada
**Como verificar:**
```bash
# Inspecionar o conteúdo de scan_roots
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**Itens a verificar:**
- O path não está curto demais (não ficou só `\\wsl.localhost\`)?
- Não tem `\` no final?
- `os.path.exists(path)` retorna True?

### 3. Compartilhamento QR "sem conteúdo"

**Sintoma:** botão de compartilhar QR → Positive/Negative em branco
**Causas candidatas:**
1. Não existe registro na tabela `templates` (meta_source=unknown)
2. Key mismatch na resposta da API (corrigido na v2.7.0)

**Checagem:**
```bash
# Verificar existência de template para o file_id
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # ID com problema
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. Scan falha em paths WSL/UNC

**Sintoma:** falha de probe em paths `\\wsl.localhost\...`
**Checagem:**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**Atenção:** `pathlib.Path.exists()` tem bug em UNC paths no WSL. Use `os.path.exists()`.

### 5. Extension não carrega

**Sintoma:** não aparece na lista de Extensions
**Checagem:**
```bash
python debug_check.py  # ver a seção de checagem de Extensions
```
**Itens a verificar:**
- `extension.json` ou `extension.yml` existe?
- O JSON/YAML é válido? (verifique com `safe_load_config`)
- Existe o campo `name`?

### 6. Bloqueio por falha na autenticação PIN

**Sintoma:** 5 falhas → lockout de 60s
**Solução:** esperar 60 segundos ou reiniciar o servidor para reset.
**Checagem:** DevTools do navegador → Network → verificar a mensagem de erro em `/_pin_check`

### 7. Quero conferir o relato de bug por QR/Bundle na página 500

**Sintoma:** a página inteira retorna 500 e a tela de erro dedicada aparece
**Alvo:** exceções não tratadas no servidor, falhas em páginas HTML inteiras

**Itens mínimos a verificar:**
- QR Code aparece na tela
- Botão "Copiar Bundle JSON" aparece
- Botão "Baixar Bundle (.json.gz)" aparece
- Ao abrir o destino do QR em `docs/bugreport.html`, é possível ver o `AI Error Bundle`

**Procedimento:**
```bash
# Iniciar o servidor normalmente
venv\Scripts\python.exe web_ui.py
```

1. No navegador, faça uma operação que provoque um 500 intencionalmente
2. Confirme se a página de 500 exibe QR e botões de Bundle
3. Clique em "Copiar Bundle JSON" e confira se `schema`, `error_id`, `request`, `error`, `state` estão no JSON
4. Clique em "Baixar Bundle (.json.gz)" e verifique se `err_*.json.gz` é salvo
5. Leia o QR com um celular ou abra a URL da string do QR e vá até `bugreport.html`
6. Na relay page, confirme se o `AI Error Bundle` aparece por completo e se, ao criar uma Issue no GitHub, esse JSON entra no corpo

**Pontos a observar:**
- `bundle.error.class` e `bundle.error.message` não estão vazios
- `bundle.request.path` corresponde à URL real que falhou
- `bundle.error.frames` contém file/line/function do ponto da falha
- `bundle.state.server_info` e `bundle.state.extensions` não estão faltando
- Mesmo com QR longo, a relay page consegue decodar

**Isolamento:**
- QR aparece, mas a relay page falha ao decodar
  Verifique pack/shrink em `core/web/error_bundle.py` e a gzip decode em `docs/bugreport.html`
- Botões Copy/Download não aparecem
  Verifique em `core/web/error_handlers.py` se `bundle_json` / `bundle_download_b64` são passados ao template
- Apenas o download está quebrado
  Verifique em `ui/default/templates/error.html` a base64 decode e a criação do Blob `application/gzip`

**Arquivos relacionados:**
- `core/web/error_bundle.py`
- `core/web/error_handlers.py`
- `ui/default/templates/error.html`
- `docs/bugreport.html`
- `docs/ja/features/qr-protocol-v1.md`

### 8. Quero verificar o client error reporter quando apenas parte da página falha

**Sintoma:** a tela abre inteira, mas só um card, seção ou carga de API falha
**Alvo:** 4xx/5xx de `fetch`, network error, `window.error`, `unhandledrejection`, falha do loader da tools page

**Itens mínimos a verificar:**
- O launcher do error reporter aparece no canto inferior direito
- É possível abrir a modal pelo launcher
- Na modal, funcionam `Copy JSON` / `Download .json.gz` / `GitHub Issue`
- O bundle contém `X-Request-Id` e `ui_events`

**Procedimento:**
1. Abra uma página que use `apiFetch`
2. Faça uma operação que chame uma API que retorna 500 intencionalmente, ou uma API inexistente
3. Verifique se o launcher aparece no canto inferior direito
4. Abra a modal e confira o JSON do bundle
5. Veja se `request.status`, `request.url`, `request.request_id`, `repro.ui_events` estão presentes
6. Clique em `Download .json.gz` e verifique se o bundle comprimido é salvo

**Verificações pelo DevTools:**
- Na aba Network, confira se o response header da API que falhou contém `X-Request-Id`
- Se houver exceção não tratada no console, confira se o bundle do launcher contém o mesmo erro
- `/api/error-report/enrich` retorna 200? Após enrich, o bundle contém `state.server_info` e `artifacts.recent_logs`?

**Exemplos de reprodução rápida:**
- Lance uma exceção propositalmente dentro do loader da tools page
- Temporariamente chame `apiFetch('/api/not-found-for-debug')` ou outra endpoint inexistente
- No servidor, substitua provisoriamente a rota alvo por `api_error(...)` ou raise

**Isolamento:**
- Está falhando, mas o launcher não aparece
  Verifique `src/ts/main/api-utils.ts` ou `src/ts/shared/error-reporter.ts`. É provável que a chamada não esteja passando pelo `apiFetch` comum
- O bundle não tem `request_id`
  Verifique em `core/web/request_hooks.py` se o `X-Request-Id` é adicionado em todas as respostas
- Mesmo após enrich, a informação do servidor está vazia
  Verifique `/api/error-report/enrich` em `routes/server_info.py` e `enrich_error_bundle()` em `core/web/error_bundle.py`
- Falhas parciais na tools page não são capturadas
  Verifique a chamada de `captureThrownError(...)` em `src/ts/tools-page/index.ts`

**Arquivos relacionados:**
- `src/ts/shared/error-reporter.ts`
- `src/ts/main/api-utils.ts`
- `src/ts/tools-page/index.ts`
- `src/ts/nav/index.ts`
- `core/web/request_hooks.py`
- `routes/server_info.py`
- `core/web/error_bundle.py`

---

## Como ler o log de depuração

### Saída do console do servidor

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → executada a correção automática de backslashes em config.json

[DEBUG] scan/start: raw=..., sanitized=...
  → path no início do scan (valor bruto → após sanitização)

[DEBUG] scan-all root 0: repr=..., len=...
  → detalhes de cada root no scan de todas as pastas

[Scan] Auto-registered scan root: /path/to/dir
  → registro automático quando o scan teve sucesso

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → API de compartilhamento QR: arquivo existe mas não há template

[ERROR] file.json: JSON parse failed: ...
  → erro de parse em safe_load_json (o app não cai)
```

---

## Estrutura de arquivos e alvos de depuração

```
web_ui.py          ← entry point (inicialização do servidor)
core/
  config.py        ← gestão de config, safe_load_*
  server.py        ← autenticação PIN, QuickLock
  scanner.py       ← engine de scan
  extensions.py    ← carregamento de Extensions
  db.py            ← gestão de conexões do DB
  schema.py        ← definições de tabelas
routes/
  scan.py          ← API de scan
  search.py        ← API de busca
  share.py         ← API de compartilhamento QR
  tools.py         ← API de tools + Inspect API
  debug.py         ← API de debug
  pages.py         ← roteamento de páginas
  server_info.py   ← API server-info / error-report enrich
core/web/
  error_handlers.py ← página 500 + geração de bug report QR
  error_bundle.py   ← geração / redução / enrich do error bundle
  request_hooks.py  ← atribuição de X-Request-Id
ui/default/templates/
  error.html       ← UI Copy/Download da página 500
static/js/
  main.js          ← UI principal (busca, modais, QR, teclado)
  scan-banner.js   ← progresso do scan + scroll top (todas as páginas)
src/ts/shared/
  error-reporter.ts ← client-side error reporter para falhas parciais
```
