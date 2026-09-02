# Toggle de Mesh Inference

Ativar/desativar Mesh Inference por tipo de modelo.

## Interface

Settings > Mesh Inference > Toggle

Mostra grid:

```
Modelo      | Per-Type | Per-Peer
------------|----------|----------
Ollama LLM  | ON/OFF   | ON/OFF
CLIP        | ON/OFF   | ON/OFF
WD-Tagger   | ON/OFF   | ON/OFF
```

## Modos

### Per-Type (Por Tipo)

Todos os pares usam mesmo modelo:

- Mais simples
- Melhor para modelos únicos
- Fallback automático

### Per-Peer (Por Peer)

Cada peer pode usar modelo diferente:

- Mais flexível
- Requer configuração manual
- Seleção explícita

## Exemplo

```json
{
  "mesh_inference": {
    "ollama_llm": {
      "enabled": true,
      "per_type": true,
      "model": "qwen2.5:7b"
    },
    "clip": {
      "enabled": true,
      "per_type": false,
      "peers": {
        "node1": "ViT-L-14-openai",
        "node2": "ViT-B-32-openai"
      }
    }
  }
}
```

## Performance

- **Per-Type**: 10-15% mais rápido
- **Per-Peer**: 20% mais flexível

Recomendação: Usar per-type para maioria dos casos.

## Fallback

Se toggle desabilitado, usa:

1. Servidor local padrão
2. Ollama se disponível
3. OpenAI API se configurada

## Monitoramento

Visualize utilização:

```
Settings > Statistics > Mesh Load
```

Mostra distribuição de carga por nó.

