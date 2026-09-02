# Armadilhas e soluções de codificação CJK / 2 bytes

Este documento resume bugs específicos das áreas de 2 bytes, focando em japonês (CP932/Shift-JIS), e as soluções adotadas neste projeto.
A intenção é servir de referência para desenvolvedores e agentes de IA que encontrarem problemas semelhantes.

---

## 1. Crash do console Windows com cp932

### Sintoma

Em `cmd.exe` / PowerShell / Git Bash do Windows, a codificação padrão de saída é **cp932 (Shift-JIS)**.
Se você imprimir com `print()` caracteres Unicode que não existem em cp932, ocorre crash imediato com `UnicodeEncodeError`.

```
UnicodeEncodeError: 'charmap' codec can't encode character '—' in position 12
```

### Exemplos de caracteres problemáticos

| Caractere | Nome | Onde foi usado |
|------|------|------------|
| `—` (U+2014) | em dash | Separador em logs |
| `–` (U+2013) | en dash | Exibição de progresso |
| `✓ ✗ ✅ ❌ ⚠️` | checkmarks e emojis | Sucesso/falha |
| `🧹 📦 📁 🔍 🔧` | emojis | Indicar o tipo de processamento |
| `█ ░` | caracteres de bloco | Barra de progresso |

### Solução

- **Use apenas caracteres ASCII-safe em `print()`**: `[OK]`, `[NG]`, `[!]`, `--`, `#`, `-` etc.
- O mesmo vale ao usar logger (`logging`). Se o encoding do handler for cp932, ocorre o mesmo problema
- Configurar `PYTHONIOENCODING=utf-8` contorna o problema, mas como depende do ambiente do usuário, é mais seguro manter-se em ASCII de forma defensiva

### Abrangência do impacto

Neste projeto, corrigimos em massa **19 arquivos** (v2.28.0).
Ao pedir geração de código a IAs (Claude/GPT), a probabilidade de elas usarem emojis ou em dash é alta; portanto,
**é um dos pontos que mais merecem atenção ao revisar código gerado por IA**.

---

## 2. Mojibake CP437 em nomes de arquivos ZIP

### Sintoma

ZIPs criados em Windows antigos (época 95/98/XP) armazenam os nomes em **Shift-JIS (CP932)**, mas a especificação de ZIP não carrega informação de encoding.
O `zipfile` do Python, quando a flag UTF-8 (bit 11) não está ativa, decodifica como **CP437**, e nomes em japonês ficam parecendo `âwâCâèâb`.

### Solução: cadeia de fallback de 10 etapas

Em `core/infra_core/encoding.py` definimos uma lista ordenada de encodings CJK:

```
UTF-8 (zipfile já tenta antes) → CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- **Não usamos** `chardet` / `cchardet`: em nomes de arquivo curtos (10 a 30 bytes), há muitos falsos positivos
- Um esquema de ordem fixa é mais reproduzível e mais fácil de depurar

### Parâmetro `metadata_encoding` do Python 3.11+

```python
# No Python 3.11+, é possível especificar diretamente com metadata_encoding
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

Entretanto, ZIPs em encodings diferentes de CP932 não ficam cobertos; quando falha, reabrimos sem `metadata_encoding` e tentamos reparar com `repair_cp437_name()`.

### Caso do 7z

O 7-Zip tem seu próprio tratamento de nomes. Via CLI do 7z pode ocorrer mojibake CP437, e também aplicamos `repair_cp437_name()` para reconstruir.

---

## 3. Scan trava em ZIP/7z com caracteres de 2 bytes

### Sintoma

Ao ler o central directory de ZIPs antigos em Shift-JIS, o `zipfile.ZipFile()` pode entrar em I/O bloqueante com determinadas sequências de bytes e travar.
É mais fácil de acontecer em arquivos com muitos itens.

### Solução

1. **Proteção por timeout**: introduzimos o helper `run_with_timeout()` em thread daemon
   - Listagem de arquivos: 30 segundos
   - I/O de scan: 60 segundos
2. **Tabela scan_errors** (migration v24): grava no DB timeouts e erros de encoding
   - Classificação de tipo: `encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. Problema de aspas em tokenchars do FTS5 do SQLite

### Sintoma

Ao usar a opção `tokenchars` da diretiva `tokenize` do FTS5 do SQLite, dependendo da combinação de aspas ocorre erro de parse.

```sql
-- NG: aspas simples externas + aspas duplas internas → parse error
tokenize='unicode61 tokenchars "_:."'

-- OK: aspas duplas externas + aspas simples internas
tokenize="unicode61 tokenchars '_:.'"
```

### Causa

O parser do tokenizador FTS5 do SQLite não consegue analisar corretamente aspas duplas dentro de aspas simples externas. Pode haver diferenças por versão do SQLite (confirmado em 3.45.1).

### Solução

No Python, combine os tipos de triple-quotes:

```python
# OK: dentro de ''' do Python, usar tanto " quanto ' em SQL
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### Como descobrimos

Na migration 29 deste projeto, ao reconstruir a tabela FTS5, ocorreu. Código gerado por IA usou a sintaxe com aspas simples externas e o servidor crashava na inicialização no ambiente SQLite 3.45.1 (corrigido na v2.70.1).

---

## 5. Encoding UTF-16 do EXIF em WebP

### Sintoma

Algumas ferramentas de geração de imagens (especialmente linha NAI) gravam metadados EXIF de WebP em **UTF-16 (com BOM)**.
A decodificação UTF-8 comum gera mojibake.

### Solução

- Detectar BOM (Byte Order Mark) e julgar UTF-16 BE/LE
- Sem BOM, estimar BE/LE por heurística
- Como fallback, tentar UTF-8 e depois latin-1

---

## 6. Encoding de chunks tEXt do PNG

### Sintoma

A especificação PNG define chunks tEXt como **Latin-1 (ISO-8859-1)**, mas a maior parte das ferramentas de IA grava strings UTF-8 diretamente.
Decodificar como `latin-1` causa mojibake em japonês.

### Solução

Priorizar UTF-8 e cair para latin-1 em caso de falha:

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. Backslashes de paths Windows em config.json

### Sintoma

Paths do Windows contêm backslash (`\`), então escrever o path à mão em um JSON cria escape sequences inválidas.

```json
{"scan_roots": ["C:\Users\test"]}  // \U e \t viram escape sequences
```

### Solução

- `_repair_json_backslashes()` faz o reparo automaticamente na inicialização do servidor
- Internamente o path é normalizado antes de ser salvo

---

## 8. pathlib e UNC paths no WSL

### Sintoma

No WSL (Windows Subsystem for Linux), `pathlib.Path.exists()` pode retornar resultado incorreto para UNC paths (`\\server\share\...`).

### Solução

- Para verificar existência de UNC paths, use `os.path.exists()`
- `pathlib` é conveniente, mas confiável demais em paths de rede

---

## 9. BOM UTF-8 em exportação CSV

### Sintoma

Arquivos CSV em UTF-8 abertos no Excel ficam com mojibake se não tiverem BOM.
O Excel, sem BOM, interpreta o UTF-8 como ANSI (CP932 em ambiente japonês).

### Solução

```python
buf.write("﻿")  # UTF-8 BOM for Excel compatibility
```

Adiciona BOM (`﻿`) no início do CSV.
Com isso, o Excel reconhece corretamente como UTF-8.

---

## 10. `ensure_ascii=False` no JSON

### Sintoma

Por padrão, `json.dumps()` do Python escapa caracteres não-ASCII como `\uXXXX`.
Se a resposta de ferramentas MCP aparecer como `タグ`, agentes de IA ficam com dificuldade para entender o conteúdo.

### Solução

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

Neste projeto, usamos de forma unificada em todos os 10 módulos de ferramenta MCP.

---

## 11. Decodificação da saída do diálogo de seleção de pasta

### Sintoma

Ao invocar o diálogo de seleção de pasta pelo PowerShell do Windows, a saída do `subprocess` está codificada em CP932.
A decodificação padrão UTF-8 gera `UnicodeDecodeError`.

### Solução

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

Com `errors='replace'`, tratamos falha de decodificação com segurança.

---

## Observações para agentes de IA

Muitos dos problemas acima são padrões **que passam facilmente despercebidos quando a IA gera código**:

1. **Não usar emojis nem caracteres decorativos em `print()`** — a IA tende a usá-los para melhorar a estética
2. **Não presuma o encoding do nome do arquivo** — escrever supondo UTF-8 quebra em ambiente CP932
3. **Teste no hardware real o uso de aspas no SQLite** — há casos em que nem o que a documentação diz funciona
4. **Use `ensure_ascii=False` em `json.dumps()`** — obrigatório se lidar com dados em japonês
5. **Decodifique a saída de subprocess com o encoding do ambiente** — no Windows costuma ser CP932
6. **CSV com BOM** — para compatibilidade com Excel

---

## Referências: arquivos relacionados neste projeto

| Arquivo | Conteúdo |
|---------|------|
| `core/infra_core/encoding.py` | Cadeia de fallback CJK, reparo de mojibake CP437 |
| `core/schema_core/schema_migrate_steps_29.py` | Forma correta de escrever aspas de tokenchars do FTS5 |
| `core/tools/fs_dialog.py` | Decodificação CP932 do diálogo de seleção de pasta |
| `core/configuration/json_rw.py` | Reparo de backslashes do config.json |
| `routes/collections.py` | Adição de BOM na exportação de CSV |
| `CLAUDE.md` | Seção "Observações do ambiente Windows > saída em console" |
