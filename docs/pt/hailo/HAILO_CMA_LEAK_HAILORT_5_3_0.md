# Vazamento de CMA no HailoRT 5.3.0 — Diagnóstico confirmado e restrições operacionais

> **Nota de correção**: Este documento é um registro do diagnóstico de vazamento de CMA baseado na medição antiga, e a conclusão antiga — de que a CMA não é recuperada mesmo após `release()`, que ela continua vazando cerca de 14 MB/min durante a inferência, e que a única recuperação confiável é reiniciar o próprio Raspberry Pi — foi retratada. O julgamento final, obtido pelo reteste no HailoRT/driver 5.4.0, foi corrigido em [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8. Não referenciar a conclusão antiga deste documento como o julgamento prático atual.

**Criado**: 2026-05-17 (descoberto e registrado na v4.214.11)
**Âmbito afetado**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (caminho `hailo_platform.genai`)
**Sintoma**: Uma vez que um LLM é carregado, a CMA mal é recuperada mesmo após chamar `VDevice.release()` / `LLM.release()`. Além disso, a CMA continua vazando continuamente durante a inferência. Não há forma de recuperação exceto reiniciar o Pi.
**Status**: Confirmado como restrição estrutural do lado do driver. Soluções alternativas estão sendo investigadas.

---

## 1. Base do diagnóstico confirmado

Usando o registrador de eventos CMA introduzido na `v4.214.10` (`logs/hailo_cma.log`, `core/hailo_device_core/device_helpers.py::log_hailo_cma_event`), a seguinte sequência foi medida em 2026-05-17.

### 1-1. Log de observação (raw)

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 minutos de uso em chat (aproximadamente 5 a 10 mensagens de inferência)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. Interpretação

| Fase | Diferença CmaFree | Significado |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB (≈ 0)** | A criação do VDevice em si consome quase nenhuma CMA |
| `acquire_pre` → `acquire_post` (carregamento do Qwen3-1.7B-Instruct) | **−285 MB** | 1 LLM consome 285 MB |
| `acquire_post` → `release_pre` (6 minutos de inferência) | **−84 MB / 6 min ≒ −14 MB/min** | **Vazamento contínuo também durante a inferência** |
| `release_pre` → `release_post` (descarregamento do LLM) | **+1 MB** | **`release()` efetivamente não devolve CMA** |

### 1-3. Comparação com a hipótese anterior

Este é um resultado de medição que contradiz parcialmente a hipótese inicial do §7 de `SQLCIPHER_MMAP_CORRUPTION.md` criado em 2026-05-16 e a hipótese do documento antigo de que "a estratégia de retenção do VDevice (nosso `_maybe_reset_vdevice` vazio) amplifica o vazamento". Como a criação do VDevice = 0 MB / release = 0 MB, **mudar a estratégia de retenção (= mudar `_maybe_reset_vdevice` para reiniciar a cada vez) não teria efeito**.

---

## 2. Restrições estruturais

Com base nos resultados medidos, o HailoRT 5.3.0 (build da comunidade, API `hailo_platform.genai`) apresenta três problemas coexistentes:

1. **`VDevice.release()` / `release()` do modelo GenAI não recupera a CMA do host** (confirmado por medição)
   - Dentro de um único processo, o driver PCIe (`hailo1x_pci`) continua mantendo as regiões DMA, e nenhuma operação equivalente a `munmap` ocorre
2. **Vazamento contínuo de CMA durante a inferência (~14 MB/min)** (confirmado por medição)
   - Observação de hoje: 84 MB perdidos em 6 minutos usando Qwen3-1.7B-Instruct
   - Um caminho separado independente de carga/descarga. O esgotamento ocorre mesmo sem descarregar
3. **Nenhum método confirmado para recuperar CMA de forma confiável exceto reiniciar o Pi** (medição + relatórios da comunidade)
   - Mesmo reiniciar o processo do servidor (equivalente a `systemctl restart yu-ai-manager`) é incompleto pois `hailo1x_pci` mantém DMA até o ciclo de energia PCIe. A recuperação completa requer `sudo reboot` do Pi (medido neste repositório)
   - Existem múltiplos relatórios independentes na comunidade Hailo: <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> e <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (afirma explicitamente que `VDevice.release()` / saída de processo / recarregamento do driver não recupera, somente o reinício do host)
   - Isso já está documentado para os usuários na mensagem de erro de rejeição prévia de `acquire_genai` (`core/hailo_device_core/device_manager_genai.py::acquire_genai`, "a full system reboot is required")

### 2-1. «Matar um processo filho devolve CMA?»: **Refutado por medição** (2026-05-17 Phase 0 PoC)

A versão anterior (rev1) concluiu teoricamente que «o kernel Linux recupera páginas DMA durante o teardown de `mm_struct`, então matar um processo filho recupera completamente a CMA», mas **a medição com Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`) confirmou independentemente duas vezes que matar um processo filho mal recupera CMA**.

**Resultados de medição (2ª execução, versão rigorosa)**:

| Ponto de medição | CmaFree | Δ |
|---|---:|---:|
| Linha base (antes do início do PoC) | 503 MB | — |
| Após criação do VDevice | 372 MB | **-131 MB** (a construção do VDevice consome CMA no processo filho com arranque a frio) |
| Após carregamento do LLM | 372 MB | 0 MB (LLM contido no pool DMA do VDevice, sem novo consumo) |
| Após SIGTERM + join | 378 MB | +6 MB |
| **Após 30 segundos de espera** | **380 MB** | **Apenas +8 MB recuperados no total** |

Contra uma recuperação esperada de ≥250 MB, o valor medido foi apenas +8 MB (+1 MB na primeira medição incidental). Isso está no nível de jitter do sistema — **nenhuma recuperação significativa de CMA ocorreu**.

**Diagnóstico confirmado**:

- O driver `hailo1x_pci` gerencia o pool DMA no **estado global interno do driver** e não no `mm_struct` do processo do usuário (estimado)
- Não é recuperado por `process exit`, `kill` ou `module unload` (consistente com relatórios da comunidade)
- **O único método de recuperação confirmado é `sudo reboot` do Pi (= ciclo de energia PCIe)** ← este é o fato medido indicado em §2 linha 3

Relatório detalhado: `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

Como resultado dessas descobertas, `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` é marcado como **REJECTED**, e a abordagem de mitigação por isolamento de subprocess é abandonada. A abordagem de reinício automático do §4 (D) é adotada como alternativa.

---

## 3. Implicações operacionais

### 3-1. «1 modelo por reinício do Pi» é efetivamente o limite

- Com Pi 5 (limite de CMA 512 MB, não pode ser aumentado conforme especificação do Pi) + LLM Qwen3 (285 MB):
    - CmaFree imediatamente após o reinício ≒ 480 MB
    - Após carregar 1 LLM → CmaFree ≒ 190 MB
    - Após dezenas de minutos de inferência → CmaFree ≒ 50 MB ou menos
    - **Carregar um segundo modelo é permanentemente impossível** (requer 250+ MB mas o restante é insuficiente, e release não o devolve)

### 3-2. O uso simultâneo de LLM + VLM / LLM + S2T não é possível

- Casos de uso que alternam entre VLM (baseado em llava, ~300 MB), S2T (whisper-small, ~175 MB) e LLM são impossíveis devido às restrições acima, a menos que se siga o procedimento de **carregar → reiniciar → carregar**.
- **UX multi-modelo como «anexar uma imagem durante a conversa para mudar para outro modelo» ou «transcrever áudio da conversa» não é estruturalmente possível com HailoRT 5.3.0**.

### 3-3. Sessões longas de inferência contínua são difíceis

- O vazamento de 14 MB/min significa que mesmo começando com 200 MB de CmaFree, metade é perdida em 14 minutos e quase tudo se esgota em 30 minutos.
- Sessões de chat superiores a 30 minutos não podem ser estabilizadas sem um reinício do Pi no meio.

---

## 4. Possíveis contramedidas

Listadas com prioridade e esforço:

| Opção | Efeito | Esforço | Efeitos colaterais / Riscos |
|---|---|---|---|
| ~~(A) Isolar operações do Hailo em um subprocess e matar periodicamente para o kernel recuperar CMA~~ | ❌ **REJECTED** (refutado por Phase 0 PoC, reproduzido duas vezes). A recuperação após kill foi apenas de +8 MB no total — hipótese inválida | — | Não adotado |
| **(B) Atualizar `_CMA_ESTIMATES_MB` para valores medidos + margem** | Melhora a precisão da rejeição prévia (reduz tentativas de carregamento falsos positivos) | ✅ Aplicável imediatamente, 1 linha | Casos que mal funcionavam com a suposição de 250 MB serão rejeitados, mas já estavam falhando |
| **(C) Banner de UI quando `CmaFree < 80 MB` / WARN no error.log quando `< 30 MB`** | Os usuários podem entender a situação e são orientados a reiniciar o Pi | Médio | Risco de fadiga de avisos / notificações excessivas |
| **(D) Detectar `CmaFree < 30 MB` e enviar SIGTERM ao supervisor** | Recuperação automática (embora seja necessário reinício completo do Pi, via `systemctl reboot`) | Médio | Requer permissões de supervisor / interrupção de sessão durante outros trabalhos |
| **(E) Aguardar correção do HailoRT + documentar restrições claramente** | Custo 0 | 0 | Depende do ciclo de lançamento do Hailo (meses+) |
| **(F) Enviar solicitação de correção ao rastreador de problemas / fórum do Hailo** | Possivelmente acelera o tempo de correção | Pequeno | A velocidade de resposta depende do contrato de suporte e do estado da comunidade |

Política de curto prazo (implementada em v4.214.11): **Aplicar (B) + este documento (ponto de partida para E e F)**.
Política de médio prazo (spec separado): Considerar na ordem de **(C) aviso de UI → (A) isolamento de subprocess**.
Longo prazo: Monitorar lançamentos do HailoRT e atualizar este documento para remover as restrições quando corrigidas.

---

## 5. Documentos / Código relacionados

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — A verificação prévia de CmaFree + a mensagem de erro para o usuário expõe explicitamente esta restrição
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — Estimativas de requisitos de CMA por modelo (qwen aumentado de 250 → 300 na v4.214.11)
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — Instrumentação de medição introduzida na v4.214.10. Os dados de medição neste documento provêm daqui
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — Design que mantém VDevice pelo tempo de vida do processo (função vazia). Esta medição confirma que mudá-lo para reiniciar não contribuiria para a recuperação de CMA
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Guia do operador para a fase de observação 0.5. Procedimento para coletar apenas logs `would_fire` com `mode=lazy` + `dry_run=true`
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Limite total de CMA do Pi5 e consumo base de cada driver (camera / KMS / Hailo / HEVC)
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — Contexto da migração para HailoRT 5.3.0 e diferenças conhecidas

---

## 6. Passos de reprodução (para relatórios de problemas do Hailo)

Passos mínimos de reprodução para relatórios de bugs externos:

```bash
# 1. Confirmar a linha base imediatamente após o reinício do Pi
grep CmaFree /proc/meminfo
# CmaFree: ~480000 kB

# 2. Iniciar o servidor + carregar o 1.º LLM (ex.: enviar 1 mensagem via GenAI em /tools)
# 1 requisição para /api/llm/generate ou /api/chat/send

# 3. Verificar CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. Descarregar o modelo
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. Verificar CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (não devolvido ← bug)

# 6. Tentativa de recarregar o mesmo / outro modelo → rejeitado por CMA insuficiente
```

Comportamento esperado: No passo 5, CmaFree deve retornar a um valor próximo à linha base do passo 1 (>400 MB).
Comportamento real: Apenas cerca de +1 MB devolvido, recarregamento impossível.
