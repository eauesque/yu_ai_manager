# Guia de Configuração de Inferência Distribuída

> Versão alvo: v4.67.0 e posterior

## O que é Inferência Distribuída?

Um recurso em que vários nós yu_ai_manager colaboram para **paralelizar e distribuir** o processamento de inferência como marcação, CLIP, YOLO e reconhecimento de fala. Você pode compartilhar varreduras de arquivos grandes em várias máquinas ou delegar marcação a um Pi5 com Hailo NPU.

```
┌──────────────┐   Lote de Imagens ┌──────────────┐
│    Local     │ ──────────────────► │  Pi5 (Hailo) │  tagger × 200 imagens
│  (Varredura) │ ──────────────────► │Máquina GPU   │  tagger × 300 imagens
│              │ ──────────────────► │    Local     │  tagger × 100 imagens
└──────────────┘   Trabalho        └──────────────┘
                  Compartilhado
```

---

## Pré-Requisitos

As seguintes condições devem ser atendidas em cada nó:

1. yu_ai_manager está em execução
2. **A extensão LAN Cowork está habilitada** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. Os nós estão **pareados entre si** ([Guia de Autenticação de Pares](../lan-cowork/peer-auth.md))
4. Os mecanismos de inferência a serem usados estão configurados em cada nó (ONNX / Hailo / Whisper, etc.)

---

## Etapas de Configuração

### Etapa 1: Habilitar LAN Cowork em cada Nó

Em `config.json` em todos os nós:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

Após reiniciar, os nós se descobrirão automaticamente via mDNS.

### Etapa 2: Concluir o Pareamento

Realize o pareamento entre todos os pares de nós (bidirecional).
Detalhes: [Autenticação PIN de Pares e Pareamento de Token](../lan-cowork/peer-auth.md)

### Etapa 3: Verificar a Matriz de Inferência Distribuída

Abra `/mesh-inference` em qualquer nó.

Os nós pareados aparecem como linhas, os tipos de inferência aparecem como colunas:

| Nó | tagger | clip | yolo | whisper |
|---|---|---|---|---|
| Local | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado |
| pi5-hailo | ☑ Habilitado | ☑ Habilitado | — Não Disponível | — Não Disponível |
| gpu-win | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado | ☑ Habilitado |

- **☑ Habilitado**: Use este nó para inferência
- **☐ Desabilitado**: Pular (pode ser alternado manualmente)
- **—**: Este nó não possui o mecanismo de inferência alvo (não pode ser operado)

### Etapa 4: Verificar o Funcionamento

Execute um lote de marcação e confirme nos logs que vários nós estão sendo usados:

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## Requisitos por Tipo de Inferência

| Tipo | Mecanismo Requerido | Descrição |
|---|---|---|
| `tagger` | ONNX (WD14, etc.) ou Hailo NPU | Marcação em estilo Danbooru para imagens |
| `clip` | ONNX CLIP ou Hailo | Vetores de incorporação semântica para imagens (para busca semântica) |
| `yolo` | ONNX YOLO | Detecção de objetos em imagens |
| `whisper` | faster-whisper ou remoto | Transcrição de fala para texto para áudio/vídeo |

Os nós sem um mecanismo configurado mostrarão "—" para esse tipo e não serão roteados para esse tipo.

---

## Exemplos de Design de Função

### Exemplo 1: Dedicar Pi5 + Hailo NPU para Marcação

Aloque Pi5 exclusivamente para marcação para reduzir a carga em outros nós.

Configuração da matriz:
- Pi5: tagger ☑, outros ☐
- Local: clip ☑, yolo ☑, whisper ☑, tagger ☐ (delegar para Pi5)

### Exemplo 2: Varredura em Massa Rápida

Habilite o tagger na máquina GPU e na máquina local, compartilhando automaticamente os arquivos via trabalho compartilhado. Nenhuma divisão manual necessária.

### Exemplo 3: Modo Somente Local (Temporário)

Clique no botão "Modo Somente Local" em `/mesh-inference` para desabilitar todos os pares remotos de uma vez. Útil quando a rede está desconectada.

---

## Solução de Problemas

### O Par Não Aparece na Matriz

1. Verifique se o par é reconhecido com `/api/lan/peers`
2. Confirme que o pareamento está completo ([peer-auth.md](../lan-cowork/peer-auth.md))
3. Verifique se LAN Cowork está habilitado no nó remoto

### O Roteamento para um Nó Específico Não Funciona

- Verifique se o tipo alvo para esse nó mostra ☑ na matriz
- Verifique se a resposta de `/api/lan/peers` mostra `status: "online"` para esse nó
- Verifique se o batimento cardíaco do nó remoto está sendo recebido (procure por `heartbeat` nos logs)

### Tudo É Processado Localmente

Se todos os pares remotos estão offline ou desabilitados, ocorre fallback local automático.
Este é um funcionamento normal (não é um erro).

### Erro `no_enabled_peers`

Esse tipo está desabilitado em todos os nós.
Habilite pelo menos 1 nó para esse tipo na matriz.

---

## Documentação Relacionada

- [Arquitetura de Inferência Distribuída](overview.md) — Design interno de trabalho compartilhado e DisableAwareStrategy
- [Matriz de Inferência Distribuída](toggle.md) — Detalhes da operação WebUI
- [Visão Geral de LAN Cowork](../lan-cowork/README.md) — Configuração geral de LAN Cowork
- [Autenticação PIN de Pares](../lan-cowork/peer-auth.md) — Procedimento de pareamento
