# Guia da UI de perfis do WD-Tagger

Este documento explica como usar a **UI de gerenciamento de perfis** do WD-Tagger (adicionada na v4.197.0+).

## 1. Visão geral

- Um **perfil** agrupa configurações do WD-Tagger: arquivos do modelo, definição de tags, limiares e pré-processamento.
- Abrir: página Tools → seção **WD-Tagger** → `Gerenciar perfis...`.
- No modal você alterna entre **Lista (List)** e **Formulário (Form)**.

## 2. Tela de lista (List)

### 2.1 Selos (Builtin / User)

- `builtin`: perfis integrados (somente leitura)
- `user`: perfis de usuário (criar/editar/excluir)
- `↻`: indica que o perfil **substitui** um perfil integrado com o mesmo `id`

### 2.2 Filtro (All / User / Builtin)

Botões:

- `Todos`
- `Usuário`
- `Integrados`

### 2.3 Botões (ações)

Ações por linha:

- `Duplicar`: copia o perfil e abre o formulário (para ajustar um perfil integrado)
- `Editar`: editar perfil de usuário (integrados não podem ser editados)
- `Excluir`: excluir perfil de usuário (integrados não podem ser excluídos)
- `Exportar`: baixar o perfil como `.json`
- `Testar (download em modo seco)`: verificar sem download real se os arquivos podem ser obtidos do HuggingFace

No canto superior direito:

- `+ Novo`: criar perfil vazio
- `Importar`: criar perfil a partir de JSON (upload / colar)

## 3. Tela de formulário (Form)

O formulário tem 5 seções em acordeão.

### 3.1 Metadata

- `id`: identificador do perfil (não pode ser alterado depois)
- `Nome de exibição`: nome mostrado na lista
- `profile_version`: versão do esquema (normalmente não precisa mudar)

### 3.2 Model & Files

- `model_id`: id do modelo no HuggingFace (ex.: `SmilingWolf/wd-swinv2-tagger-v3`)
- `adapter_family`, `backend`, `hf_subdir`: apenas se necessário
- `Arquivos`:
  - `name`: nome do arquivo (ex.: `model.onnx`)
  - `Obrigatório`: tratado como necessário no teste
  - `size_hint_mb`: opcional
  - `+ Adicionar arquivo` / `Remover`: adicionar/remover linhas

### 3.3 Tag source

Origem das definições de tags.

- `csv`: arquivo(file), delimitador(delimiter), coluna de nome(name_col), coluna de categoria(category_col), mapa(category_map)
- `json_list`: arquivo(file), esquema(schema)
- `json_dict`: arquivo(file), mapeamento(mapping)
- `composite`: combinação de fontes(sources)

### 3.4 Threshold source

Origem dos limiares.

- `global_per_category`: definir por categoria diretamente na UI
- `per_tag`: arquivo + fallback
  - arquivo(file)
  - modo de fallback(fallback.mode): `global` / `category_default`
  - valor de fallback(fallback.value)

### 3.5 Preprocess & Categories

- Pré-processamento(`preprocess_spec`): `input_size`, `dtype`, `layout`, `channel_order`, `resize_strategy` (`letterbox` / `longest_side_pad` / `stretch`), `scale`, `mean`, `std`
- Categorias:
  - `Categorias suportadas`
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. Importar / Exportar

### 4.1 Importar

`Importar` mostra duas abas:

- Enviar JSON: enviar um arquivo `.json`
- Colar JSON: colar JSON na área de texto

Após importar, o formulário abre. Verifique/ajuste e `Salvar`.

### 4.2 Exportar

Na lista, `Exportar` baixa o perfil como JSON.

## 5. Testar (download em modo seco)

- Verifica se os arquivos listados em `files` podem ser obtidos do **HuggingFace**.
- Em sucesso, pode aparecer `Download OK: {n} arquivos ({total} MB)`.
- Em erro, um banner informa a causa (próxima seção).

## 6. Erros comuns (breve)

- `id_conflict`: já existe um perfil de usuário com o mesmo `id`
- `id_immutable`: `id` não pode ser alterado (renomear via Duplicar → Excluir)
- `in_use`: não é possível excluir porque o perfil está ativo
- `validation_failed`: validação falhou (`{detail}` tem detalhes)
- `profile_too_large`: JSON importado > 1MB
- `ssrf_blocked`: redirecionamento fora do HuggingFace bloqueado (proteção SSRF)
- `hf_unavailable`: HuggingFace indisponível / resposta inválida
- `timeout`: tempo esgotado (60s)
- `required_missing`: arquivo obrigatório ausente

## 7. Limitações (importante)

- Perfis integrados (`builtin`) não podem ser editados/excluídos. Use `Duplicar`.
- `id` é imutável. Para renomear: `Duplicar` → `Excluir` o antigo.
- Limite de importação: **1MB**.
- `Testar` só permite hosts do HuggingFace (allowlist SSRF):
  - `huggingface.co`
  - `hf.co`
