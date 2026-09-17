# Registro de Arquivo Drag & Drop

Arraste e solte arquivos de imagem/vídeo na página principal da biblioteca (`/`) para salvá-los
em um diretório de **Drop Inbox** configurado e registrá-los automaticamente na
biblioteca. O caminho de scan normal (`scan_one`) é usado, então extração de metadados,
geração de thumbnail e tagging são executados como seria para um scan normal.

## Comportamento

1. Com a página principal aberta, arraste arquivos do explorador de arquivos ou outro navegador
2. Uma sobreposição aparece na janela mostrando o caminho de destino (Drop Inbox)
3. Ao soltar, cada arquivo é copiado para o Drop Inbox e registrado
4. Um toast mostra o número de sucessos e falhas

## Resolução de Drop Inbox

O Drop Inbox é resolvido nesta prioridade:

1. `drop_inbox_dir` do `config.json` (configuração explícita)
2. Se não configurado: a primeira raiz de scan habilitada é usada como está

**Restrição**: `drop_inbox_dir` **deve** estar dentro de uma das entradas `scan_roots`.
Qualquer caminho fora de scan roots é rejeitado com HTTP 400. Isso preserva
a invariante de que scan roots são a única fonte confiável para arquivos da biblioteca.

## Exemplo de Configuração

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

O `drop_inbox_dir` é criado se não existir (seu pai ainda deve estar
dentro de `scan_roots`).

## Tratamento de Colisão de Nome

Se um arquivo com o mesmo nome já existir no inbox, sufixos `_1`, `_2`,
... são automaticamente acrescentados. Arquivos existentes nunca são sobrescritos.

## Extensões Permitidas

| Categoria | Extensões |
|---|---|
| Imagens | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| Vídeos | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

Arquivos (`.zip` / `.7z` / `.rar`) **não são suportados** via drag & drop. Coloque
arquivos de arquivo diretamente em uma raiz de scan e execute um scan regular em vez disso.

## Limitações

- O tamanho total da requisição é limitado a `MAX_CONTENT_LENGTH` (padrão **100 MB**)
- Nomes de arquivo contendo traversal de caminho (`..`) são rejeitados
- Soltar um diretório inteiro não é atualmente suportado (apenas arquivos individuais)

## API HTTP

### `POST /api/dnd-upload`

Aceita uploads de arquivo multipart, salva-os no Drop Inbox, e registra-os
na biblioteca.

Resposta:

```json
{
  "ok": true,
  "total": 3,
  "success": 2,
  "results": [
    { "ok": true, "status": "added", "file_id": 12345, "path": "...", "filename": "a.png" },
    { "ok": true, "status": "skipped", "path": "...", "filename": "b.png" },
    { "ok": false, "code": "unsupported_type", "error": "...", "filename": "c.xyz" }
  ]
}
```

### `GET /api/dnd-inbox`

Retorna o Drop Inbox atualmente resolvido para a sobreposição da UI exibir.

```json
{ "ok": true, "inbox": "D:/Pictures/AI/inbox", "explicit": true }
```

### `POST /api/files/register-path`

Registra um arquivo já em disco por caminho (sem upload). O caminho deve estar dentro
de `scan_roots`. Usado pela ferramenta MCP `register_file`.

```json
{ "path": "D:/Pictures/AI/inbox/a.png" }
```

## Ferramentas MCP

| Ferramenta | Descrição |
|---|---|
| `register_file(path)` | Registrar um arquivo em um caminho absoluto na biblioteca |
| `drop_inbox_info()` | Retornar o diretório Drop Inbox atualmente resolvido |
