# API de Sweeps

Endpoints para histórico de execução de sweep do Bridge (eixos de parâmetros NAI / SD WebUI / ComfyUI).

As informações de execução foram persistidas nas tabelas `sweeps` / `sweep_axes` (migração 68) desde v4.183.0. A lista de histórico da página `/sweep/<id>` é renderizada através desta API.

## GET /api/sweeps/history

Retorna sweeps recentes. Usado por `/sweep/<id>` para mostrar filtros "mesmas condições do sweep atual".

### Parâmetros de consulta

| Parâmetro | Tipo | Padrão | Descrição |
|---|---|---|---|
| `limit` | int (1..500) | 50 | Máximo de entradas retornadas |
| `ref` | string | — | ID de sweep de referência; obrigatório quando `match` está definido |
| `match` | CSV | — | Lista separada por vírgulas de campos para comparar com a referência |
| `tol_steps` | string | `exact` | Tolerância para etapas: `exact` / `5` / `10` / `20` (percentual) |
| `tol_cfg` | string | `exact` | Tolerância para CFG (mesmos valores) |
| `completed_only` | `0`/`1` | `0` | `1` mantém apenas `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` mantém apenas linhas com `first_file_id` não nulo |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### Chaves `match` permitidas

- `bridge` / `checkpoint` / `vae` / `sampler` — igualdade de string
- `positive` / `negative` — igualdade de `prompt_template` / `negative_template`
- `axisX` / `axisY` / `axisZ` — `sweep_axes.param` no axis_index 0/1/2 deve corresponder
- `resolution` — correspondência de `width` E `height`
- `steps` / `cfg` — correspondência numérica (`tol_*` controla a tolerância)
- `baseSeed` — correspondência de `base_seed`

Chaves para as quais o sweep de referência não tem valor são silenciosamente ignoradas (na interface do usuário, a caixa de seleção correspondente é desativada).

### Resposta

```json
{
  "ok": true,
  "data": {
    "entries": [
      {
        "id": "uuid-xxxx",
        "bridge": "nai",
        "base_seed": 1234567,
        "created_at": 1714992000,
        "prompt_template": "best quality, ...",
        "negative_template": "worst quality, ...",
        "checkpoint": "nai-anime-v3",
        "vae": null,
        "sampler": "k_euler",
        "width": 832,
        "height": 1216,
        "steps": 28,
        "cfg": 5.5,
        "axis_count": 1,
        "first_file_id": 12345,
        "last_file_id": 12399,
        "file_count": 6,
        "status": "completed",
        "updated_at": 1714992100,
        "axes_params": ["cfg_rescale"]
      }
    ],
    "total": 142
  }
}
```

`total` é a contagem de linhas não filtradas de `sweeps`, usada para o badge "{shown} / {total} match".

## GET /api/sweep/info/<file_id>

Lê o pacote XMP de `file_id` e retorna os metadados de sweep estruturados. Consulte `core/bridge_core/sweep_xmp.py`.

## GET /api/sweep/files/<sweep_id>

Verifica a pasta principal do `file_id` dica e retorna cada arquivo cujo XMP carrega o mesmo ID de sweep.

## Como as linhas são preenchidas

- **No momento do salvamento**: `core/bridge_core/bridge_save_batch.py` chama `upsert_sweep_from_meta()` após a importação automática. O cabeçalho de execução e os eixos são escritos à primeira vista; lotes subsequentes apenas atualizam `last_file_id` / `file_count` / `updated_at`.
- **Preenchimento retroativo para arquivos antigos**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`. Percorre arquivos `has_sweep=1` e reconstrói linhas a partir de atributos XMP. Idempotente.

## Limitações conhecidas

- O caminho de salvamento assincrónico (`return_file_ids=False`) pode deixar `first_file_id` NULL. A interface do usuário renderiza a linha como um item não clicável.
- `prompt_template` / `negative_template` são armazenados uma vez por execução. As substituições de estilo S/R por eixo não são reconstruídas; os valores dos eixos por imagem permanecem no pacote XMP e são lidos por `/api/sweep/info/<file_id>`.
