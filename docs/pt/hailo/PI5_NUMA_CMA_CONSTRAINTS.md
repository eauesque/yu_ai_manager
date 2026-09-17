# Restrições de CMA no Pi 5 sob `numa=fake=8`

Conhecimentos práticos sobre a alocação de CMA no Raspberry Pi 5 (8 GB) ao executar cargas de trabalho Hailo-10H.
Descreve o limite de `cma=`, o motivo pelo qual valores acima de 512M falham silenciosamente, e como recuperar o CMA consumido pelo driver de vídeo.

**Público-alvo**: desenvolvedores que executam modelos Hailo GenAI (LLM, Speech2Text) no Raspberry Pi 5
(usando AI HAT / AI HAT+).

---

## ⚠️ Aviso sobre a regressão de firmware de 2026-05

**A partir do lançamento de 2026-05-13 do `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11`**, escrever `cma=` em `/boot/firmware/cmdline.txt` — independentemente do tamanho — silencia completamente o mailbox do firmware VC (`vcgencmd ioctl_set_msg failed:-1`, `raspberrypi-clk -22`, HEVC `-517`, ausência do cpufreq sysfs).

**Método definitivo recomendado a partir de 2026-05-16**: em vez de `cma=` na cmdline, escreva `dtoverlay=cma,cma-512` em `/boot/firmware/config.txt`. Como a alocação é feita via o nó de memória reservada `linux,cma` do DT, não há conflito com o novo firmware. Veja detalhes em §6 e em [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md).

A descrição antiga abaixo (recomendando `cma=512M` na cmdline) reflete os resultados de verificação de 2026-04-15. O conhecimento sobre o valor-limite (512M) imposto pelas fronteiras dos nós NUMA continua válido, mas **o local de configuração migrou da cmdline para o argumento de overlay em config.txt**.

---

## TL;DR

- **O local de configuração é `dtoverlay=cma,cma-512` em `config.txt`** (definido em 2026-05-16; `cma=` na cmdline quebra o mailbox no novo firmware)
- `cma-1024` e `cma-768` **falham silenciosamente** no Pi 5 (8 GB) — `CmaTotal` fica em 0, sem pânico de kernel nem aviso algum (limite imposto pelas fronteiras dos nós NUMA; presume-se que a mesma restrição persista mesmo via overlay)
- **`cma-512` é o valor-limite confirmado e o valor recomendado** (reverificado via overlay em 2026-05-16 no Pi 5 8 GB, confirmando a alocação de `CmaTotal: 524288 kB`)
- Causa raiz: o kernel padrão do Pi 5 aplica `numa=fake=8`, limitando a alocação contígua a um único nó NUMA (1 GB)
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` consomem ~157 MB de CMA na inicialização** — mesmo quando a inicialização do driver DRM falha (verificado em 2026-04-15)
- **`camera_auto_detect=1`** carrega `pisp_be` e `videobuf2_dma_contig`, consumindo CMA adicional. Recomenda-se desativar em sistemas headless
- **Linha de base otimizada para headless** (ambos os overlays desativados): ~98 MB de CMA usados na inicialização, ~414 MB livres para modelos Hailo
- **O YOLO InferModel usa 0 MB de CMA** (confirmado em 2026-04-15) — apenas os modelos GenAI (LLM, Speech2Text) alocam a partir do CMA
- Carregamento simultâneo de LLM (qwen2.5-1.5b) + Whisper-base: total de ~328 MB — cabe dentro da linha de base otimizada para headless
- O CMA não é recuperado com a reinicialização do servidor — só é liberado com uma reinicialização completa do sistema (reenergização do PCIe) (bug do driver `hailo1x_pci`, já reportado à Hailo)
- Trate o VDevice como um **singleton de tempo de vida do processo**. Não expulse nem recarregue.

---

## 1. Sintomas

Ao definir `cma=1G` (ou `cma=768M`) em `/boot/firmware/cmdline.txt` e reiniciar, ocorre o seguinte:

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

O sistema inicializa normalmente. Não há pânico de kernel nem mensagem de erro alguma. A configuração de CMA em `cmdline.txt` é **silenciosamente ignorada**, e tudo que depende de CMA (NPU Hailo-10H, câmeras V4L2, etc.) falha na inicialização.

**Sempre verifique a alocação de CMA após alterar `cmdline.txt`:**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. Causa raiz: as fronteiras de nó do `numa=fake=8`

O kernel padrão do Raspberry Pi OS para o Pi 5 aplica `numa=fake=8`, dividindo os 8 GB de memória física em **8 nós NUMA virtuais de 1 GB cada**:

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

O CMA do Linux (`cma_init_reserved_mem`) precisa ser alocado, na inicialização, como **memória física contígua que não ultrapasse as fronteiras dos nós NUMA**.
Isso impõe um limite rígido de 1 nó = 1 GB. Como o próprio kernel ocupa memória no mesmo nó, não é possível reservar exatamente 1 GB inteiro:

> **A tabela abaixo é um registro de medições feitas em 2026-04-15, sob o método de cmdline.**
> O conhecimento sobre o valor-limite (512M) imposto pelas fronteiras dos nós NUMA continua válido, mas **o `cma=` na cmdline não deve mais ser usado** (veja a regressão de firmware no início do documento).
> O método de configuração atual é `dtoverlay=cma,cma-512` em `config.txt` (§6).

| Configuração em `cmdline.txt` (registro de 2026-04-15) | Resultado |
|---|---|
| `cma=1G` | Tenta consumir o nó inteiro. Não sobra espaço para o kernel → **falha silenciosa**, CmaTotal=0 |
| `cma=768M` | Excede a faixa contígua confiável → **falha silenciosa**, CmaTotal=0 (verificado em 2026-04-15) |
| `cma=512M` | Metade de 1 nó → **estabilidade confirmada** ✓ (verificado em 2026-04-15) ← Recomendação da época. **Atualmente, use `dtoverlay=cma,cma-512`** |
| `cma=384M` | Não verificado (512M já está confirmado; 384M é desnecessário) |
| `cma=256M` | Estável, mas apertado ao usar LLM + Whisper simultaneamente |
| `cma=128M` | Estável, mas insuficiente para o Hailo GenAI (só o LLM já precisa de ~234 MB) |

### Por que a falha é silenciosa

`cma_init_reserved_mem` não entra em pânico quando a alocação falha. O kernel inicializa com `CmaTotal=0` e se comporta como se o CMA nunca tivesse sido solicitado.
O valor escrito em `cmdline.txt` é, na prática, ignorado.

---

## 3. Requisitos de CMA do Hailo-10H

Medido no Raspberry Pi 5, AI HAT+, HailoRT 5.3.0:

| Modelo / combinação | Uso de CMA | Observação |
|---|---|---|
| LLM — qwen2.5-1.5b-chat (isolado) | **~234 MB** | Medido em 2026-04-15 |
| YOLO InferModel (yolov8n, configure + bindings) | **0 MB** | Confirmado em 2026-04-15 |
| Whisper-tiny (isolado) | ~70 MB | Estimado |
| Whisper-base (isolado) | ~100 MB | Estimado |
| Whisper-small (isolado) | ~150 MB | Estimado |
| **LLM + Whisper-tiny (simultâneo)** | **~246 MB** | Medido com CMA 256 MB |
| **LLM + Whisper-base (simultâneo)** | **~334 MB** | Estimado. Espera-se que caiba dentro da linha de base headless |

**O YOLO usa 0 MB de CMA**: no HailoRT 5.3.0, o YOLO InferModel, `configure()` e `create_bindings()` não alocam CMA algum.
Os buffers de DMA de entrada e saída são mapeados a partir de arrays numpy pré-alocados via `set_buffer()`, e não do CMA.
Portanto, o YOLO não entra no cálculo do orçamento de CMA.

Ao aplicar CMA 512 MB com a otimização headless (ver §5), espera-se que as seguintes configurações funcionem:

- Somente LLM (~234 MB, ~180 MB de margem)
- Somente Whisper-tiny / Whisper-base (cabe facilmente)
- LLM + Whisper-base simultâneos (total de ~334 MB, ~80 MB de margem)

A combinação de Whisper-small com LLM (estimada em ~384 MB) se aproxima do limite teórico — confirme com medições reais antes de confiar nela.

Para detalhes, veja os resultados dos testes de carregamento simultâneo em [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md).

---

## 4. O CMA só é recuperado com uma reinicialização completa

O CMA alocado pelo HailoRT permanece em memória até uma reinicialização completa do sistema.
Isso vale independentemente de `VDevice.release()`, do encerramento do processo do servidor, ou de recarregar o módulo do kernel.

**Causa raiz** (confirmada em 2026-04-15): o `hailo1x_pci` mantém as alocações DMA coerentes mesmo depois de fechar o fd do dispositivo ou recarregar o módulo.
Só é liberado com uma reinicialização completa (reenergização do PCIe). O bug já foi reportado à Hailo.

| Fase | CmaFree (CMA 512 MB, otimizado para headless) |
|---|---|
| Inicialização | **~426 MB** |
| Após carregar o LLM (~234 MB) | ~192 MB |
| Após carregar o Whisper-base (~100 MB) | ~92 MB |
| Após `VDevice.release()` | ~92 MB (**não é devolvido**) |
| Após o encerramento do processo do servidor | ~92 MB (**não é devolvido**) |
| Após `rmmod hailo1x_pci && modprobe hailo1x_pci` | ~92 MB (**não é devolvido**) |
| Após reinicialização completa do sistema | **~426 MB (restaurado)** |

**Implicação**: o consumo de CMA se acumula ao longo de reinicializações do servidor dentro da mesma sessão de inicialização.
Não espere que o CMA seja recuperado com a reinicialização do servidor. Projete o VDevice como um **singleton de tempo de vida do processo**.
Se o CMA se esgotar, ele só será restaurado com uma reinicialização completa do sistema.

---

## 5. Otimização headless: `/boot/firmware/config.txt`

O `config.txt` padrão do Pi OS contém duas configurações que consomem uma grande quantidade de CMA mesmo em sistemas headless (sem display).

### 5.1 `dtoverlay=vc4-kms-v3d` e `max_framebuffers=2`

**Efeito**: o firmware do Pi 5 pré-aloca framebuffers de CMA para o pipeline de vídeo na inicialização.
Com `max_framebuffers=2`, isso consome ~157 MB de CMA **antes mesmo de qualquer processo em espaço de usuário ser executado**.

A alocação persiste mesmo que o driver DRM do Linux falhe posteriormente na inicialização (por exemplo, `[drm] Couldn't stop firmware display driver: -22` ou `Couldn't get core clock` no `dmesg`).

| Estado de `config.txt` | CmaFree na inicialização |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` ativados (padrão) | **~257 MB** |
| Ambos comentados | **~305 MB** (+~48 MB) |

**Correção** (modo headless / servidor):

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**Compromisso**: `vc4-kms-v3d` é necessário para exibição com aceleração de hardware e 3D (V3D).
Se o sistema for acessado apenas via SSH ou interface web, é seguro desativá-lo.

### 5.2 `camera_auto_detect=1` e `display_auto_detect=1`

**Efeito**: esses overlays sondam câmeras CSI e displays DSI na inicialização, carregando `pisp_be` (Pi ISP backend) e `videobuf2_dma_contig`.
Os módulos carregados e o hardware detectado pré-alocam CMA adicional variável.

| Estado de `config.txt` | CmaFree na inicialização |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 MB (após desativar vc4) |
| Ambos definidos como 0 | **~426 MB** (+~121 MB) |

**Correção**:

```ini
camera_auto_detect=0
display_auto_detect=0
```

**Observação**: `camera_auto_detect=0` afeta apenas câmeras CSI. Câmeras USB (UVC / `uvcvideo`) não são afetadas e continuam funcionando normalmente.

### 5.3 `config.txt` mínimo recomendado para uso headless com AI HAT+

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

Estimativa de CMA na inicialização com essa configuração: **~98 MB usados**, ~414 MB livres para modelos Hailo.

### 5.4 Resumo do orçamento de CMA (CMA 512 MB, otimizado para headless)

| Configuração | CmaFree | Disponível para o Hailo |
|---|---|---|
| Padrão (vc4-kms-v3d + câmera ativados) | ~257 MB | ~257 MB |
| vc4-kms-v3d + max_framebuffers desativados | ~305 MB | ~305 MB |
| + camera/display_auto_detect=0 | **~426 MB** | **~426 MB** |
| Após carregar o LLM (~234 MB) | ~192 MB | Para o Whisper |
| Após carregar LLM + Whisper-base (~100 MB) | ~92 MB | (margem) |

---

## 6. Configuração recomendada

### Defina `dtoverlay=cma,cma-512` (confirmado em 2026-05-16)

```bash
# Verificar o estado atual do CMA
grep CmaTotal /proc/meminfo

# 1) Remover o cma= existente de cmdline.txt (pois quebra o mailbox no novo firmware)
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) Adicionar dtoverlay=cma,cma-512 à seção [all] de config.txt
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) Recomenda-se reinicialização a frio (desconectar e reconectar a energia)
sudo sync && sudo poweroff

# Verificar após reiniciar (confirme os 4 itens a seguir)
vcgencmd version                                # Resposta do Broadcom obrigatória (silêncio = falha)
grep CmaTotal /proc/meminfo                     # Espera-se 524288 kB
journalctl -b -k | grep 'linux,cma'             # Deve exibir "initialized node linux,cma"
journalctl -b -k | grep '0x00030087'            # Não deve exibir nada
```

Se o `dmesg` exibir `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool`, é evidência de que a alocação foi feita pelo caminho do DT.
Por outro lado, se exibir `Reserved memory: bypass linux,cma node, using cmdline CMA params instead`, significa que ainda resta um `cma=` na cmdline — remova-o.

### Caso deseje ativar o `vc4-kms-v3d`

Se o KMS DRM de display for necessário, é possível integrá-lo na forma de argumento de overlay:
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
No entanto, como descrito em §5.1, o vc4-kms-v3d consome ~157 MB de CMA, portanto recomenda-se desativá-lo para uso com o Hailo GenAI.

### Verifique sempre após alterar o kernel, o firmware ou as configurações

Após alterações em `/boot/firmware/cmdline.txt` ou `config.txt`, ou após atualizações de kernel/firmware, o estado do CMA e a resposta do mailbox podem mudar silenciosamente.
Torne a verificação dos 4 itens acima uma rotina pós-reinicialização.

---

## 7. Interação com outros problemas de `numa=fake=8`

O `numa=fake=8` causa pelo menos dois problemas distintos relevantes a este projeto:

| Problema | Sintoma | Causa raiz |
|---|---|---|
| Falha silenciosa do CMA | `CmaTotal=0` após `cma=1G`, `cma=768M` | Fronteiras de nó NUMA limitam a alocação contígua |
| Falha na instalação do Node.js | O instalador npm/node aborta com erro de memória | A memória por nó NUMA (1 GB) é detectada erroneamente como a RAM total. Reportado upstream como [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) |
| Dreno de CMA do `vc4-kms-v3d` | Consome ~157 MB na inicialização. Não é devolvido mesmo se a init do DRM falhar | `max_framebuffers=2` faz o firmware reservar framebuffers de CMA antes da inicialização do driver Linux |

Tanto a falha silenciosa quanto o dreno do vc4 têm origem na mesma restrição subjacente (a zona DMA abaixo de 4 GB, as fronteiras de nó NUMA).
Ao encontrar falhas inesperadas relacionadas à memória, verifique primeiro `/proc/meminfo` e `config.txt`.

---

## 8. Lista de verificação de diagnóstico rápido

```bash
# 1. Resposta do mailbox (verificação prioritária no novo firmware)
vcgencmd version                     # Silêncio sugere que ainda resta um cma= na cmdline

# 2. Verificar a alocação de CMA
grep CmaTotal /proc/meminfo          # 0 kB = falha silenciosa

# 3. Verificar o caminho DT vs. cmdline
journalctl -b -k | grep 'linux,cma'
# Esperado: "initialized node linux,cma, compatible id shared-dma-pool" (caminho DT = normal)
# Errado:   "bypass linux,cma node, using cmdline CMA params instead" (cma= ainda presente na cmdline)

# 4. Verificar a topologia NUMA
numactl --hardware                   # Exibe o número de nós e a memória por nó

# 5. Verificar a cmdline atual e a configuração de overlay
cat /boot/firmware/cmdline.txt       # Confirmar que não contém cma=
grep '^dtoverlay=cma' /boot/firmware/config.txt   # dtoverlay=cma,cma-512 deve estar presente

# 6. Verificar a disponibilidade do dispositivo Hailo
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # Confirmar que o NPU está acessível

# 7. Verificar config.txt quanto a consumidores de CMA
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. Verificar os módulos de kernel carregados (usuários de CMA)
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**Ambiente de verificação**: Raspberry Pi 5 8 GB, Raspberry Pi OS
(Linux 6.12.62+rpt-rpi-2712, aarch64), HailoRT 5.3.0, AI HAT+, CMA=512M
(**revalidado em 2026-05-16**: Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT, com 524288 kB alocados via `dtoverlay=cma,cma-512`, resposta do mailbox confirmada)
