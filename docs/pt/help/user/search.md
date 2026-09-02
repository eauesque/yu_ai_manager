# Busca

## Busca básica

Digite tags separadas por vírgula na barra de busca.

```
1girl, blue_eyes, school_uniform
```

## Filtros de busca

| Filtro | Descrição |
|---------|------|
| Intervalo de datas | Restringe entre data inicial e final |
| Formato de arquivo | PNG / WebP / JPG / GIF |
| Rating | Restringe por estrelas 1 a 5 |
| Favoritos | Exibe apenas os favoritados |
| Coleção | Exibe apenas os de uma coleção específica |

## Busca dentro do prompt

Usando o campo "in_prompt", é possível fazer busca full-text dentro do texto do prompt da imagem.
Quando o FTS (Full-Text Search) está ativo, a busca é rápida.

## Ordem de classificação

| Sort | Descrição |
|--------|------|
| date | Data de registro (mais novo primeiro) |
| date_old | Data de registro (mais antigo primeiro) |
| folder | Ordem por pasta |
| path | Ordem por path |
| random | Aleatório |
| rating_desc | Rating (maior primeiro) |
| rating_asc | Rating (menor primeiro) |

## Busca semântica

Se um modelo Hailo-10H ou CLIP ONNX estiver configurado, é possível buscar imagens em linguagem natural.
Use o botão de busca semântica à direita da barra de busca.

### Aceleração com FAISS (recomendado)

A busca semântica usa por padrão busca brute-force em NumPy, mas
**instalar o FAISS acelera bastante**.

| Tamanho da biblioteca | NumPy (padrão) | FAISS (recomendado) |
|-------------|-------------------|-------------|
| Até 10 mil | Dezenas de ms | Poucos ms |
| 100 mil | 1-3 s | Dezenas de ms |
| 1 milhão+ | Mais de 10 s | Até 100ms |

O FAISS escolhe automaticamente o índice mais adequado conforme a escala:
- **Menos de 50 mil**: IndexFlatIP (busca completa exata, rápida o suficiente)
- **50 mil ou mais**: IndexIVFFlat (busca aproximada de vizinhos mais próximos, rápida mesmo em larga escala)

#### Como instalar

```bash
# Instalar após ativar o venv
source venv/bin/activate

# x86_64 (Intel/AMD) — instalável diretamente pelo pip
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — se não instalar por pip
# Opção 1: via conda
conda install -c conda-forge faiss-cpu

# Opção 2: build a partir do source
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

Após instalar, basta reiniciar o servidor para que seja detectado automaticamente.
Quando aparecer a mensagem abaixo no log de inicialização, o FAISS está ativo:

```
FAISS x.x.x detected — using accelerated vector search
```

Mesmo sem o FAISS instalado, tudo continua funcionando com NumPy, como antes.
