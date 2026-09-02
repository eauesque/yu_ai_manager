# Tag Database - Checklist de Depuração

**Lista de depuração por ordem de prioridade**
**Status**: Legado (registro da era v2.5.x; todos os itens já foram tratados)
**Última atualização**: 2026-02-13

---

## P0 (Critical): corrigir imediatamente (impacta a usabilidade)

### ✅ 1. Correção de desalinhamento de layout da UI

**Problema:**
```
Os campos de busca não cabem lado a lado,
e os botões ficam desalinhados
```

**Como verificar:**
1. Iniciar a WebUI
2. Redimensionar o navegador para 1366x768
3. Checar o alinhamento dos campos de busca

**Local da correção:** `templates/index.html`
```html
<!-- Before -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- After -->
<div class="search-row">
  <!-- add flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**Validação:**
- [ ] Exibição normal em 1920x1080
- [ ] Exibição normal em 1366x768
- [ ] Exibição normal em 768x1024 (tablet)

---

### ✅ 2. Remoção de duplicatas no autocompletar de tags

**Problema:**
```
Candidatos de autocompletar aparecem duplicados

Exemplo de exibição:
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ↑ diferença apenas na presença de espaços
```

**Como verificar:**
1. No campo de tags, digite "sample_creator"
2. Confira o autocompletar
3. Veja se há duplicatas

**Local da correção:** `static/js/main/main.js`
```javascript
// dentro de initTagAutocomplete()
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // Normalize and deduplicate
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // space after comma
      .replace(/\s+/g, ' ')        // multiple spaces → single
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // Sum counts
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**Validação:**
- [ ] Sumiu a duplicidade?
- [ ] Os counts são somados?
- [ ] Sem problema de desempenho?

---

## P1 (High): melhoria (impacta funcionalidades)

### ✅ 3. Teste de normalização de parênteses na busca

**Problema:**
```
Confirmar se \(tag\) e (tag) são equivalentes
```

**Como verificar:**
1. Preparar uma imagem com a tag `\(emphasis\)`
2. Buscar por `(emphasis)` no campo
3. Ver se encontra

**Pontos a verificar:**
- [ ] Buscar `(tag)` também encontra `\(tag\)`
- [ ] Buscar `\(tag\)` também encontra `(tag)`
- [ ] No modo regex, não converter

**Código relacionado:** `web_ui.py` - `normalize_tag_for_search()`

---

### ✅ 4. Teste de leitura de arquivos dentro de ZIP

**Problema:**
```
As imagens dentro do ZIP são exibidas corretamente?
Os metadados são extraídos corretamente?
```

**Casos de teste:**

#### Test 1: comportamento básico
```bash
# 1. Criar um ZIP de teste
zip test.zip image1.png image2.png

# 2. Escanear
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. Conferir
python tagdb_tool.py search --db test.db --q "*"
```

**Verificar:**
- [ ] Arquivos dentro do ZIP registrados no formato `test.zip!image1.png`
- [ ] Metadados extraídos
- [ ] Miniaturas exibidas

#### Test 2: função de extração
```
1. Abrir um arquivo dentro do ZIP na WebUI
2. Clicar em "Extrair e editar"
3. Verificar se o explorer abre
4. Verificar se o arquivo extraído existe
```

**Verificar:**
- [ ] Botão de extração aparece
- [ ] Ao clicar, o explorer abre
- [ ] Extrai para o diretório extracted/
- [ ] O arquivo extraído é registrado no DB

#### Test 3: ZIP muito grande
```bash
# 1) Criar um ZIP de 1,1GB (Zip64)
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) Scan dentro do ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**Verificar:**
- [x] Uso de memória não cresce de forma anormal
- [x] Tempo de scan aceitável (até 5 min)
- [x] Sem erros

**Medido (2026-02-17):**
- Tamanho do ZIP: `1.153.433.914 bytes` (cerca de 1,1GB)
- Tempo: `elapsed=0:00.14`
- RSS máximo: `maxrss_kb=23864`
- Registro no DB: `zip_members=1` (`large_1_1gb.zip!images/sample.png`)

---

### ✅ 5. Teste de busca de checkpoint

**Problema:**
```
O nome do modelo é extraído e busca corretamente?
```

**Casos de teste:**

#### Test 1: extração do nome do modelo
```python
# Verificar se o nome do modelo é extraído em cada formato

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**Verificar:**
- [ ] Extrai do formato NovelAI
- [ ] Extrai do formato SD
- [ ] Extrai do formato ComfyUI

#### Test 2: funcionalidade de busca
```
1. Na WebUI, clicar no campo de checkpoint
2. Confirmar se aparece o autocompletar
3. Buscar por "animagine"
4. Ver se só são exibidas imagens do modelo
```

**Verificar:**
- [ ] Autocompletar funciona
- [ ] Busca por substring funciona
- [ ] Ordenado por frequência de uso

---

## P2 (Medium): tratamento futuro (melhoria de desempenho)

### ✅ 6. Implementar cache de miniaturas

**Problema:**
```
Miniaturas de arquivos dentro de ZIP são geradas a cada vez
→ lento
```

**Proposta de implementação:**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # Build cache path
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # Return cache if present
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # Generate otherwise
    thumbnail = generate_thumbnail(...)

    # Save to cache
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**Validação:**
- [ ] Segundo acesso fica rápido
- [ ] Uso de disco dentro do aceitável
- [ ] Função de limpeza de cache

---

### ✅ 7. Medição de desempenho com grandes volumes

**Casos de teste:**

#### Test 1: 100.000 arquivos
```bash
# Medir tempo de scan
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# Medir tempo de busca
time python tagdb_tool.py search --db large.db --q "1girl"
```

**Metas:**
- [ ] Scan: 50.000 arquivos/hora ou mais
- [ ] Busca: até 1 segundo (em 100.000 itens)

#### Test 2: responsividade da WebUI
```
1. Iniciar a WebUI com um DB de 100.000 itens
2. Executar busca
3. Scroll
```

**Verificar:**
- [ ] Resultados em até 3 segundos
- [ ] Scroll fluido
- [ ] Navegador não trava

---

## Checklist de execução de testes

### Preparação do ambiente
- [ ] Python 3.8+ instalado
- [ ] Dependências instaladas
- [ ] Dados de teste preparados (imagens em cada formato)

### Testes funcionais
- [ ] Leitura de ZIP
- [ ] Scan de múltiplos diretórios
- [ ] Normalização de tags
- [ ] Busca de checkpoint
- [ ] Filtro por modelo

### Testes de UI/UX
- [ ] Layout (várias resoluções)
- [ ] Modo escuro
- [ ] Atalhos de teclado
- [ ] Autocompletar

### Testes de desempenho
- [ ] 10.000 itens
- [ ] 50.000 itens
- [ ] 100.000 itens
- [ ] ZIP grande (500MB+)

### Compatibilidade de navegador
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### Compatibilidade de SO
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## Ferramentas de depuração

### Habilitar logs
```bash
# Add to the top of tagdb_tool.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Medição de desempenho
```python
import time

start = time.time()
# ... processing ...
print(f"Time: {time.time() - start:.2f}s")
```

### Verificação de uso de memória
```python
import tracemalloc

tracemalloc.start()
# ... processing ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**Criado em:** 2026-02-13
**Prioridade:** tratar na ordem P0 → P1 → P2
**Nota:** esta checklist foi criada na época v2.5.x; todos os itens descritos já foram tratados
