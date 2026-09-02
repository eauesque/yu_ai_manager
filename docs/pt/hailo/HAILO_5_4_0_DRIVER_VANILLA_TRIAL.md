# Correção e registro de verificação do julgamento de CMA não liberada no HailoRT / driver 5.4.0

Criado: 2026-08-16 / Última atualização: 2026-08-17 / Versão correspondente: yu_ai_manager 4.623.1

Registro da verificação de hipóteses e do teste A/B entre a versão oficial vanilla e a versão corrigida com `FOLL_LONGTERM` do `hailo-ai/hailort-drivers` v5.4.0 (publicado em 2026-08-16, GPL-2.0, código-fonte aberto) para o evento que vinha sendo julgado como CMA não liberada (ver `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`), com a correção do julgamento incorreto do lado da medição.

---

## 1. Conclusão

**Última reverificação de 2026-08-17 (4ª rodada): o `VERDICT: FAIL` obtido até a 3ª rodada foi um julgamento incorreto, resultante do uso exclusivo da quantidade absoluta de recuperação de `CmaFree` após o carregamento inicial do HEF como critério de vazamento. Comparando em A/B a versão oficial vanilla 5.4.0 e a versão corrigida com `FOLL_LONGTERM`, obtiveram-se sucesso em todos os testes: carregamentos consecutivos a partir de `CmaFree` baixo, liberação e recarregamento dentro do mesmo processo, 20 gerações e a repetição completa dos testes a partir de estados de `CmaFree` baixo. Não houve aumento/diminuição monotônico de RSS e `CmaFree` durante a geração, e zero falhas de alocação de CMA. A queda inicial de `CmaFree` corresponde ao aumento do cache de páginas de HEFs de múltiplos GB, e o `MemAvailable` manteve-se em cerca de 7 GB. Nas condições testadas desta vez — Pi 5 + Hailo-10H + HailoRT/driver 5.4.0, modelo único, dispositivo único, repetição de curta duração —, não se reproduziu um vazamento de CMA de relevância prática, e a correção `FOLL_LONGTERM` também não trouxe melhoria mensurável. Operação contínua de longa duração, uso simultâneo de múltiplos modelos, Hailo-8 e ambientes sob IOMMU não foram testados, e ficam fora do escopo de aplicação desta conclusão.**

### 1.1 Evolução do julgamento

| Rodada | Data | Julgamento naquele momento | Base da atualização/correção |
|---|---|---|---|
| 1ª rodada | 2026-08-16 | Julgamento impossível | Ao atualizar apenas o driver para 5.4.0, a API foi rejeitada pela verificação de correspondência exata de versão com a library 5.3.0 (§3) |
| 2ª rodada | 2026-08-17 | Apenas teste limitado concluído | Driver / library / firmware foram alinhados em 5.4.0, e a repetição do `run2` atingiu um platô, mas a reprodução direta via pyhailort ainda não havia sido executada (§4) |
| 3ª rodada | 2026-08-17 | `FAIL` provisório (posteriormente identificado como julgamento incorreto) | Resultado do diagnóstico antigo, que avaliava apenas a quantidade absoluta de recuperação de `CmaFree` após o carregamento inicial do HEF. Uma medição isolada não conseguia distinguir entre perda de memória e uso do cache de páginas (§5, §7) |
| 4ª rodada | 2026-08-17 | Vazamento de relevância prática não reproduzido | A/B entre vanilla e `FOLL_LONGTERM`, repetição com CMA baixo, recarregamento dentro do mesmo processo, 20 gerações e medição de RSS, `MemAvailable` e falhas de alocação corrigiram a 3ª rodada (§8) |

---

## 2. Diferença de código-fonte v5.3.0 → v5.4.0 (`hailo-ai/hailort-drivers`)

Diff de todos os arquivos entre as duas tags via API do GitHub. Como se trata de um único commit "squash", nada pôde ser extraído da mensagem de commit, e a verificação foi feita pelo diff real dos arquivos. Não houve alteração na **lógica em si** de alocação/liberação de CMA (o par `dma_alloc_coherent`/`dma_free_coherent`); o que se segue é majoritariamente refatoração e correções defensivas:

| Arquivo | Conteúdo da alteração |
|---|---|
| `linux/utils/compact.h` → `compat.h` | Renomeação de arquivo da camada de compatibilidade de kernel |
| `linux/vdma/memory.c` | Adição de verificação NULL em `hailo_desc_list_release()`, com limpeza do ponteiro para NULL após a liberação (correção defensiva de **prevenção de double-free**) |
| `linux/vdma/vdma.h` | Remoção do campo redundante `kernel_address` de `hailo_descriptors_list_buffer` (integrado a `desc_list.descs`) |
| `common/vdma_common.c` | Reescrita do julgamento de conclusão de transferência DMA, do cálculo direto via `hw_num_proc` para a comparação `num_proc`/`num_avail` (possível correção de bug no rastreamento de conclusão de transferência) |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync` (acompanhamento do novo nome de API do kernel) |
| `common/pcie_common.c` | Remoção do campo md5 do protocolo de controle de FW, reforço do julgamento de corrupção de log SCU de "apenas os 4 primeiros bytes" para "verificação completa das 5 primeiras words" |

O texto das mensagens de erro também foi alterado (de uma explicação longa para o texto abreviado `out of CMA memory.`), mas o fluxo de controle de alocação/liberação é o mesmo. **Apenas a partir deste diff, não é possível identificar nenhuma alteração correspondente à hipótese vigente à época (CMA não liberada ao recarregar o modelo)**.

---

## 3. Trabalho de substituição no equipamento real e pontos de bloqueio (2026-08-16, 1ª tentativa)

Em um Raspberry Pi 5 + Hailo-10H, com `hailo1x_pci 5.3.0` (gerenciado via dkms) em operação, tentou-se a substituição para v5.4.0 via compilação manual.

### 3.1 `make install` não depende de `all`

O alvo `install` do `linux/pcie/Makefile` executa apenas `modules_install`, e completa sem aviso mesmo sem o artefato de compilação (`.ko`) existir (para ser exato, há um aviso de ausência de `System.map`, mas não fica claro que a causa é a compilação não ter sido executada).

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**Sempre executar na ordem `make all && sudo make install`.**

### 3.2 Os cabeçalhos do kernel do Raspberry Pi não incluem `System.map`

Ao executar `modules_install`, o seguinte aviso é exibido e o `depmod` é pulado silenciosamente:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

Porque `/usr/src/linux-headers-<kernelver>/System.map` não existe. Como `/boot/System.map-<kernelver>` existe, o problema é resolvido copiando-o:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

Se isso não for feito, o `modprobe` não consegue resolver o `.ko` recém-instalado e ocorre `FATAL: Module hailo1x_pci not found` (mesmo com o arquivo `.ko` existindo em `/lib/modules/<kernelver>/kernel/drivers/misc/`).

### 3.3 As regras udev não são refletidas imediatamente sem reload/trigger

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

Imediatamente após a substituição do módulo, `/dev/h1x-0` fica como `crw-------` (exclusivo do root). Resolvido com:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 A incompatibilidade de versão entre driver e library é fatal

Ao executar `hailortcli` com apenas o driver do kernel atualizado para 5.4.0:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

A library HailoRT exige **correspondência exata** com o driver do kernel; se apenas um lado for atualizado primeiro, todas as chamadas de API são rejeitadas imediatamente. A verificação vanilla apenas do driver é impossível, sendo necessário atualizar simultaneamente também o pacote de espaço de usuário `hailort` (o SDK principal).

- `apt-cache policy hailort` → candidato 5.3.0 (na data em questão, 5.4.0 ainda não distribuído no apt oficial)
- `gh api repos/hailo-ai/hailort/releases` → a tag `v5.4.0` existe, mas `assets` está vazio (sem deb pré-compilado, apenas código-fonte)

Ou seja, **a verificação de campo do 5.4.0 só é possível instalando o HailoRT propriamente dito via deb ou compilando-o integralmente a partir do código-fonte**. A compilação completa envolve um build de grande porte com C++ CMake + bindings Python, com risco de envolver também pacotes de dependência como `hailo-tappas`, `python3-hailort`, etc.; por isso, na 1ª rodada optou-se por adiar e aguardar a distribuição do deb oficial.

---

## 4. Registro do procedimento de compilação própria (2026-08-17, 2ª tentativa)

Sem aguardar a distribuição do apt/deb oficial, procedimento e pontos de bloqueio ao compilar a partir do código-fonte do GitHub (driver: GPL-2.0, `hailort` principal: MIT) e aplicar no sistema.

### 4.1 Ambiente de compilação

- Instalado o `checkinstall` (`sudo apt-get install -y checkinstall`). Porém, a etapa de compressão `xz` do módulo do kernel entra em conflito com o `installwatch` (o mecanismo de rastreamento de arquivos baseado em LD_PRELOAD do checkinstall), e ao executar `make install` via checkinstall, ocorreu falha repetida (arquivo ou diretório inexistente no `xz`). **Para empacotar o módulo do kernel, não usar checkinstall; usar dkms (para o driver propriamente dito) ou o `make install` puro (para a library de espaço de usuário)**
- Memória liberada antes da compilação: processos duplicados do `headroom mcp serve` e o `rust-analyzer` foram pausados temporariamente (liberando cerca de 1 GB no total). A memória do Pi é de 7,9 Gi, e mesmo durante a compilação foi possível manter cerca de 3,8 Gi disponíveis

### 4.2 Compilação do `hailort` (library de espaço de usuário)

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # criar o diretório antes
cmake .. -DCMAKE_BUILD_TYPE=Release   # obtém automaticamente dependências externas (protobuf/spdlog/eigen etc.) via FetchContent, ~4 min
cmake --build . -j2   # limitado a -j2 (para evitar pressão de memória), ~15 min
sudo make install     # instalado em /usr/local/{include,lib,bin}. Coexiste com a versão do apt (5.3.0, em /usr)
```

Como os valores padrão de `option()` deixam todos os componentes pesados (GStreamer, testes, servidor, integração com Ollama, etc.) em OFF, apenas `libhailort.so`, `hailortcli` e `libhailopp` foram compilados — uma configuração relativamente leve.

**Nota**: o artefato do `make install` é colocado em `/usr/local`, sem sobrescrever a versão do apt (em `/usr`, 5.3.0). Ao verificar o funcionamento, é necessário especificar o caminho explicitamente, como em `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`.

### 4.3 Substituição do driver (módulo do kernel) e atualização do firmware

O driver em si foi compilado e instalado via dkms (mesmo procedimento do apêndice A, trocando para `-v 5.4.0`), com recarregamento via `rmmod`/`modprobe`. Nesse ponto, o `hailortcli` retornou `HAILO_DRIVER_OPERATION_FAILED(36)` / no dmesg `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`, revelando que **o firmware no dispositivo (lado SoC, pci_ep) também precisa ser atualizado separadamente para 5.4.0**.

```bash
# Obtenção do firmware a partir do S3 oficial (usando o script incluído no repositório do driver)
bash hailort-drivers/download_firmware_hailo10h.sh
# Backup do firmware existente antes de substituir pela nova versão
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <diretório extraído>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

Ao tentar recarregar o módulo neste ponto (`rmmod`/`modprobe`, incluindo com `support_soft_reset=1`), o dmesg retornou consistentemente `SOC Firmware batch was already loaded`. Verificando o código-fonte do driver, constatou-se que `load_soc_firmware()` (o caminho de carregamento do firmware SoC do Hailo-10H) não implementa o processamento de soft reset via `support_soft_reset` (implementado apenas em `load_nnc_firmware()` do Hailo-8), sendo pulado incondicionalmente enquanto `hailo_pcie_is_firmware_loaded()` retornar true. Ou seja, **o estado do firmware no SoC não pode ser alterado por recarregamento do módulo; é indispensável reenergizar o equipamento real**.

Após o reinício, o dmesg registrou a gravação em lote do firmware (`customer_certificate.bin`, `scu_fw.bin`, `u-boot-*.dtb.signed`, `u-boot-spl.bin`, `fitImage`, `image-fs`, nessa ordem, 4064ms) → `SOC Firmware Batch loaded successfully`, e `hailortcli fw-control identify` respondeu normalmente com `Firmware Version: 5.4.0 (release,app)`.

### 4.4 Verificação simplificada do comportamento de CMA e suas limitações

Com `hailortcli run2` (resnet_v1_18.hef, modelo pequeno incluído no pacote `hailo_tutorials`), observou-se a evolução de `CmaFree` (`/proc/meminfo`) em uma execução única de load/run/exit e em 8 execuções consecutivas:

| Execução | CmaFree (kB) |
|---|---|
| baseline (imediatamente após reinício) | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3〜8 | 133744 (sem alteração, platô) |

Alcançou-se um platô em poucas execuções, e nenhum vazamento adicional foi observado até a 8ª execução. No entanto, trata-se de um load/run/exit simples via CLI (inicialização a cada processo separado), um caminho diferente dos dois vazamentos conhecidos relatados em `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — (a) não liberação em `VDevice.release()`/recarregamento de modelo **dentro do mesmo processo**, e (b) vazamento contínuo durante a execução de `generate_stream()` (inferência LLM) — e este resultado não constitui evidência de que o problema foi "resolvido".

A reprodução principal (`tools/diag_hailo_cma_reclaim.py` e o script descrito no doc de acompanhamento do fórum) carrega o LLM GenAI via binding Python `hailo_platform` (pyhailort), e por isso não pôde ser executada diretamente no ambiente 5.4.0:

```
$ o hailo_platform dentro do .venv está fixado (link estático) em libhailort.so.5.3.0 (confirmado com ldd)
$ Ao construir VDevice(), previsão de incidência do mesmo HAILO_INVALID_DRIVER_VERSION por incompatibilidade de versão driver(5.4.0)/library(5.3.0)
```

Nesse ponto, a recompilação do pyhailort (binding Python) a partir do código-fonte 5.4.0 e sua substituição no `.venv` ainda não havia sido iniciada, mas foi realizada na 3ª tentativa (§5).

---

## 5. Recompilação do pyhailort e reexecução da reprodução (2026-08-17, 3ª tentativa)

Esta seção registra o julgamento provisório no momento da 3ª tentativa. O método de julgamento e a conclusão foram corrigidos no teste A/B da 4ª rodada (§8).

### 5.1 Compilação do pyhailort (binding Python)

`hailort/libhailort/bindings/python/platform/` do repositório principal `hailort` é o código-fonte do pacote pip do pyhailort (`pyproject.toml`, baseado em scikit-build-core + pybind11). Compilado vinculando explicitamente o libhailort 5.4.0 já instalado em `/usr/local` em §4.2:

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

Dentro do build isolation, `scikit-build-core`/`pybind11` foram obtidos automaticamente do PyPI para a compilação, substituindo o `hailort` do `.venv` do wheel 5.3.0 para o 5.4.0. Confirmou-se via `ldd` que `_pyhailort*.so` está vinculado a `/usr/local/lib/libhailort.so.5.4.0`, e o construct/release de `VDevice()` também funcionou normalmente isoladamente.

### 5.2 Reexecução da reprodução existente (`tools/diag_hailo_cma_reclaim.py`)

Com o mesmo script de reprodução, o mesmo critério de julgamento e o mesmo HEF (`~/hailo_models/Qwen3-1.7B-Instruct.hef`) de 2026-05, remediu-se no mesmo ambiente, com o `hailo_platform` do `.venv` substituído para 5.4.0:

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

Resultado (`logs/hailo_cma_reclaim_poc.json`):

| Evento | CmaFree (MB) |
|---|---:|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22 (consumo de 137 MB) |
| imediatamente após kill do filho (`terminate`) | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s〜+30s | **0** (queda adicional de cerca de 28,5 MB a partir dos 29 MB, permanecendo em torno de 512 kB mesmo após vários minutos) |

Essa nova queda de 29 MB → cerca de 512 kB não pôde ser confirmada como concorrência com outros processos no mesmo horário, mas permanece como uma observação não elucidada cuja causa não pode ser determinada apenas com esta medição. Apenas o uso do cache de páginas após o carregamento inicial (§8.4) não explica essa evolução intermediária, e como este teste não coletou simultaneamente RSS, `MemAvailable` e falhas de alocação em repetição, não é utilizado como base para o julgamento final de §8.

Contudo, essa faixa de cerca de 512 kB é a mesma faixa observada em 464→1.648 kB durante o teste `FOLL_LONGTERM` de §8.3, e a partir desse estado obteve-se sucesso em 20 gerações, liberação e recarregamento. Embora o processo até chegar a valores baixos permaneça não elucidado, **confirmou-se no equipamento real que o `CmaFree` nessa faixa, por si só, não significa imediatamente um estado perigoso ou impossibilidade de carregamento**.

Texto original produzido pela ferramenta de diagnóstico antiga (julgamento provisório do momento da 3ª rodada; o julgamento final foi corrigido em §8):

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

O que foi confirmado nesta tentativa é apenas que o `CmaFree` após o carregamento inicial do HEF não se recuperou de acordo com o critério de julgamento antigo. Não se comprovou perda de memória disponível após o encerramento do processo, nem que o vazamento não foi corrigido na v5.4.0. Na 3ª rodada, interpretou-se provisoriamente como não liberação, mas essa interpretação e o método de julgamento foram corrigidos em §8.

---

## 6. Falha do kernel durante a 3ª tentativa e recuperação do código de depuração de CMA (2026-08-17)

### 6.1 Ocorrência e candidatos a causa

Para investigar o caminho de liberação de CMA, foi adicionado ao código-fonte DKMS local, em `linux/vdma/memory.c`, um include de `linux/mm.h` e um código de medição que chama `virt_to_page()` / `page_count()` imediatamente antes de `dma_free_coherent()`. Ao carregar o módulo contendo essa alteração, o sistema travava ao usar o Hailo, tornando-se impossível de inicializar; por isso, o carregamento automático está atualmente bloqueado via `module_blacklist=hailo1x_pci,hailo_pci` em `/boot/firmware/cmdline.txt`.

Converter diretamente o endereço virtual de CPU retornado por `dma_alloc_coherent()` para uma página via `virt_to_page()` não faz parte do contrato da DMA API. Como o formato de mapeamento do endereço retornado é delegado ao alocador, o `page_count()` obtido a partir daí não constitui um meio correto de observar a contagem de referência de CMA, podendo gerar referências de página inválidas. O código de medição era executado em ambos os caminhos de liberação, tanto da descriptor list quanto do continuous buffer.

O horário de adição foi 10:15:36, e o início da respectiva build DKMS foi 10:15:39, permitindo concluir que o módulo que travou incluía esse código. Não foi possível obter o stack trace imediatamente antes da falha, portanto não se trata de uma determinação estrita da causa, mas é a única alteração de código de execução local inexistente na v5.4.0 vanilla, e é considerada a candidata mais provável.

### 6.2 Estado recuperado

As 7 linhas a seguir (o include de `linux/mm.h` e os dois pontos de log de `virt_to_page()` / `page_count()`) foram removidas, o DKMS foi recompilado e o `depmod` concluído.

- Kernel: `6.18.39+rpt-rpi-2712`
- Módulo recompilado: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- O módulo acima já está registrado em `modules.dep`
- A blacklist permanece mantida; o módulo recompilado ainda não foi carregado

Na próxima vez, o plano é garantir um caminho de recuperação como o console serial antes de remover a blacklist e confirmar o primeiro carregamento por meio de reinicialização. Na investigação do próprio problema de CMA não liberada, a medição que converte o endereço de retorno da DMA API em páginas internas não será reintroduzida; os alvos de observação serão o livro-razão de buffers mantido pelo driver, o tamanho das alocações e o número de chamadas a `dma_free_coherent()`.

**Adendo (2026-08-17, mais tarde)**: com o backup de `cmdline.txt` (`cmdline.txt.bak-blacklisted`) preparado, a blacklist foi removida e o sistema reiniciado, confirmando-se a inicialização normal (com o console serial `console=serial0,115200` também configurado, garantindo o caminho de recuperação). A partir daí, a investigação prosseguiu com a instrumentação segura de §7 (sem inspeção de páginas brutas, apenas saída de log de contadores e tamanhos existentes).

---

## 7. Formação e exclusão de hipóteses de causa — verificação e refutação de `FOLL_LONGTERM` (2026-08-17)

Esta seção registra a formação de hipóteses de causa decorrente da 3ª tentativa, e os candidatos a causa que puderam ser excluídos por experimento. O papel aqui é o refinamento de candidatos; o julgamento final sobre a existência ou não do vazamento de CMA depende do teste A/B da 4ª rodada (§8).

Considerando a falha de §6, a investigação prosseguiu com instrumentação segura que evita acesso direto ao interior de páginas, como `virt_to_page()` (apenas saída de log via `dev_err()`; sem inspeção ou conversão de ponteiros brutos).

### 7.1 Conteúdo da instrumentação

Foram adicionados logs de saída dos contadores atômicos existentes (`controller->desc_cma_in_use` / `controller->cma_in_use`) e do tamanho das alocações (sem qualquer acesso ao interior de páginas) nos seguintes pontos de `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c`:

- `hailo_desc_list_create`/`hailo_desc_list_release` (alloc/free da descriptor list)
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free` (alloc/free do continuous buffer)
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl` (caminho ioctl de liberação explícita)
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy` (caminho de mapeamento/desmapeamento DMA de buffer de espaço de usuário; também exibe `buffer_type`/`is_mmio`/`is_dmabuf`)
- `hailo_vdma_file_context_finalize` (limpeza em lote no momento de fops_release, com saída dos contadores em ENTER/EXIT)

### 7.2 Resultado observado

Imediatamente após o reinício (`CmaFree` ≈ 451 MB), executou-se `tools/diag_hailo_cma_reclaim.py --signal terminate`, coletando e agregando todos os logs com `sudo dmesg | grep CMA_DBG` do dmesg.

- **`CmaFree` de `/proc/meminfo`**: 451 MB → 195 MB (**consumo de 256 MB**) → após kill+30s de espera, ainda 204 MB (**247 MB abaixo do baseline**)
- **`desc_cma_in_use` do próprio driver (descriptor list, via `dma_alloc_coherent`)**: no máximo cerca de 2〜4 MB. Retorna a 0 de forma confiável no EXIT de `file_context_finalize`
- **`cma_in_use` (continuous buffer, via `dma_alloc_coherent`)**: permaneceu em 0 durante toda esta sessão (o continuous buffer nunca foi usado)
- **Mapeamento DMA de buffer de espaço de usuário (`hailo_vdma_buffer_map`, `buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`, `is_mmio=0`, `is_dmabuf=0`)**: chamado 621 vezes, das quais **342 vezes com tamanho de 8 MB (`0x800000`)** (total de 2,7 GB em chamadas de mapeamento; presume-se que o mesmo buffer de staging do lado do host esteja sendo reutilizado no processamento do pipeline). `hailo_vdma_buffer_destroy` foi chamado 628 vezes, correspondendo quase 1:1 com `buffer_map`, e **o livro-razão de mapeamento do próprio driver não está corrompido** (`dma_unmap_sg` é chamado corretamente)
- **SWIOTLB (`/sys/kernel/debug/swiotlb/`)**: `io_tlb_used_hiwater=0`. O bounce buffer nunca foi utilizado
- O dispositivo Hailo não está sob IOMMU (`/sys/bus/pci/devices/0001:01:00.0/iommu_group` não existe)

Nesse ponto, interpretou-se como candidato a causa da queda de CMA não as alocações do próprio driver via `dma_alloc_coherent()` (desc list, continuous buffer), mas o caminho tratado por `hailo_vdma_buffer_map()`, que "mapeia memória já alocada pelo espaço de usuário para uso via DMA" (`HAILO_DMA_USER_PTR_BUFFER`). Nesse caminho, o driver não aloca CMA novo; ele fixa (pin) páginas de usuário já existentes para torná-las acessíveis via DMA.

### 7.3 Hipótese de causa: `FOLL_LONGTERM` não especificado em `get_user_pages()`

Ao verificar `prepare_sg_table()` em `linux/vdma/memory.c` (chamado internamente por `hailo_vdma_buffer_map()`):

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages` (como o kernel em questão, 6.18.39, corresponde a `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`) é um simples alias de `get_user_pages()`, e **a flag `FOLL_LONGTERM` não é especificada**. O lado da liberação (`clear_sg_table()`) também chama o correspondente `put_page()`, permanecendo com a API antiga `get_user_pages()`/`put_page()`, e não com a nova série `pin_user_pages()`/`unpin_user_pages()`.

Segundo a prática documentada do kernel Linux (`Documentation/core-api/pin_user_pages.rst`), código que **mantém referências de página por longos períodos**, como transferências DMA, deve usar `pin_user_pages()` com `FOLL_LONGTERM`. Quando `FOLL_LONGTERM` não é especificado, mesmo que páginas de usuário que por acaso estejam dentro da região CMA sejam fixadas via `get_user_pages()`, a propriedade original da CMA de ser "migrável (movable para outros usos quando necessário)" fica desativada por um longo período. O alocador de CMA normalmente migra essas páginas para fora da região CMA antes da fixação de longo prazo, mas em caminhos que não usam `FOLL_LONGTERM` essa migração não ocorre, de modo que, **enquanto a fixação persistir, essa parte é efetivamente perdida da região CMA, e mesmo após a liberação (`put_page()`), não é imediatamente reconhecida como espaço livre de CMA** (pois migração e compactação adicionais são necessárias separadamente).

Esta hipótese era consistente com a medição isolada da 3ª rodada (§7.2):
- Os contadores de CMA do próprio driver são irrelevantes (`get_user_pages` não passa por `dma_alloc_coherent`)
- As chamadas de map/destroy estão corretamente balanceadas (o `put_page()` em si é chamado corretamente; o problema é que o "retorno" à CMA após a liberação é lento/incompleto)
- Ao carregar um LLM grande como o Qwen3-1.7B-Instruct, um grande número de buffers de 8 MB é alocado e mapeado via DMA na memória do host, e o problema se manifesta quando parte deles inclui páginas dentro da região CMA
- É consistente com a recuperação lenta e parcial de `CmaFree` após o kill (cerca de +15〜30MB em 30s, com aumento gradual ao longo de vários minutos adicionais) (o próprio `put_page()` é chamado de forma confiável no encerramento do processo, mas parece necessário processamento adicional para a recuperação como espaço livre de CMA)

### 7.4 Implementação do candidato de correção e verificação no equipamento real → refutação (2026-08-17, continuação)

Substituiu-se efetivamente `prepare_sg_table()` de `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` para `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`, adicionando o include de `<linux/mm.h>`, e concluiu-se compilação, reregistro no dkms e carregamento no equipamento real (confirmou-se que os símbolos `pin_user_pages`/`unpin_user_page` foram resolvidos normalmente via `modprobe --dump-modversions`).

Resultado da execução da mesma reprodução a partir de um estado de `CmaFree` alto (453 MB) imediatamente após o reinício:

| | Antes da correção (n=múltiplas execuções) | Depois da correção (n=1) |
|---|---|---|
| baseline | 436〜451 MB | 453 MB |
| after_llm_loaded | 173〜195 MB (consumo de 256〜263 MB) | 180 MB (consumo de 273 MB) |
| after_post_wait | 188〜204 MB (recuperação de 9〜15 MB) | 190 MB (**recuperação de 10 MB**) |
| `VERDICT` pelo critério de julgamento antigo | `FAIL` | **`FAIL` (sem alteração)** |

> Esta tabela é assimétrica em número de execuções e método de agregação, não sendo uma comparação A/B rigorosa. O julgamento A/B baseia-se no resultado de §8, repetido em condições idênticas.

Verificando `CMA_DBG buffer_map` no `dmesg`, confirmou-se que, mesmo após a correção, os mesmos buffers de tamanho 0x800000 (8 MB) foram mapeados sem problema via `pin_user_pages` (sem nenhuma falha de pin ou aviso do kernel), com o caminho de código sendo executado conforme o esperado. A compactação forçada via `echo 1 > /proc/sys/vm/compact_memory` também não teve efeito. O `MemAvailable` permaneceu saudável em 7,1 GB, e assim como antes da correção, não se tratava de escassez de memória do sistema como um todo, mas apenas da contabilidade específica de `CmaFree` que não se recuperava.

**Conclusão: a hipótese de ausência de `FOLL_LONGTERM` foi refutada pelo experimento.** A substituição de `get_user_pages()` por `pin_user_pages()`+`FOLL_LONGTERM` é uma melhoria legítima alinhada com a prática documentada do kernel Linux, mas não foi a causa direta do sintoma de CMA não liberada observado nesta sessão. A hipótese em si é teoricamente sólida (a interação entre o mecanismo de migração de CMA e a fixação de longo prazo é um tipo de problema conhecido e real), e permanece válida como apontamento de qualidade de código, mas **não é uma causa raiz que explique isoladamente o resultado medido desta vez**.

### 7.5 Exclusão de candidatos a causa (julgamento final em §8)

O que se segue são candidatos a causa claramente **excluídos** por experimento. Esta lista é válida como resultado da verificação de hipóteses, mas não é o julgamento em si sobre a existência de vazamento.

- Alocação do próprio driver via `dma_alloc_coherent()` (desc list, continuous buffer) — apenas alguns MB, retorna corretamente a 0
- Inconsistência nas chamadas de map/destroy do mapeamento SG — está balanceado
- Bounce buffer do SWIOTLB — nunca foi usado (`io_tlb_used_hiwater=0`)
- Ausência de `FOLL_LONGTERM` em `get_user_pages()` — correção implementada e verificada no equipamento real, sem melhoria

O fato que restou até a 3ª tentativa foi que, com o `MemAvailable` saudável, apenas o `CmaFree` caía após o carregamento inicial. Na época, isso foi interpretado como não liberação, mas um único teste não consegue distinguir entre "perda de memória disponível" e "conversão de páginas movable de CMA para o cache de páginas". Na 4ª rodada, repetiu-se o teste mantendo `CmaFree` baixo, medindo a possibilidade real de carregamento, a diminuição líquida em repetições, RSS e falhas de alocação de CMA, corrigindo o julgamento.

---

## 8. 4ª tentativa: reteste A/B vanilla / `FOLL_LONGTERM` e confirmação do julgamento incorreto (2026-08-17)

### 8.1 Objetos de comparação

- Versão corrigida com `FOLL_LONGTERM`: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, `srcversion=C84A00ABB326748A1832CE1` no carregamento
- Oficial vanilla 5.4.0: tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`, `get_user_pages()` / `put_page()`, `srcversion=A260C39C9F2C06DD4FB072E` no carregamento
- Kernel: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef` (2.880.748.478 bytes)

### 8.2 Dois carregamentos consecutivos em processos independentes

| Driver | Tentativa | baseline | carregado | após exit | variação vs. baseline | Carregamento |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB (redução)** | sucesso |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB (aumento)** | sucesso |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB (redução)** | sucesso |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB (redução)** | sucesso |

Em ambos os drivers, `CmaFree` caiu significativamente apenas na primeira vez, e o segundo carregamento a partir desse valor baixo teve sucesso, com a redução líquida chegando a praticamente 0. O diagnóstico anterior julgava apenas "quanto do consumo durante o carregamento foi devolvido em MB", classificando como `FAIL` mesmo casos normais como a 2ª tentativa, em que o `CmaFree` já começava baixo.

### 8.3 Geração, liberação e recarregamento dentro do mesmo processo

| Indicador | `FOLL_LONGTERM` | vanilla 1ª vez | vanilla repetição CMA baixo |
|---|---:|---:|---:|
| Geração concluída | 20/20 | 20/20 | 20/20 |
| 1º carregamento | sucesso | sucesso | sucesso |
| 2º carregamento após liberação | sucesso | sucesso | sucesso |
| `CmaFree` da geração 1→20 | 464→1.648 kB | 115.376→123.728 kB | 82.320→83.296 kB |
| `MemAvailable` da geração 1→20 | 6.706.208→6.788.432 kB | 6.830.352→6.910.560 kB | 6.871.504→6.906.368 kB |
| RSS durante a geração | fixo em 63.888 kB | 63.904〜63.920 kB | 63.936〜63.952 kB |
| Falhas de alocação de CMA | 0 | 0 | 0 |

A repetição com CMA baixo do vanilla começou com `CmaFree=87,424 kB`, ficando em 79.520 kB imediatamente após a liberação total e retornando a 87.344 kB posteriormente (diferença líquida de 80 kB). Não há comportamento de perda cumulativa ao repetir carregamento, geração e liberação. O `nr_foll_pin_*` do vanilla é 0 porque não usa a API `FOLL_PIN`, e não pode ser usado para comparar o sucesso da liberação de pin.

### 8.4 Interpretação da queda inicial

De imediatamente após o reinício do vanilla até depois de todas as reverificações, `Cached` aumentou de 1.845.872 kB para cerca de 4.988.224 kB, enquanto `MemAvailable` se manteve entre 7.071.280 kB e cerca de 6.962.816 kB. O aumento é consistente com a leitura de HEFs de múltiplos GB, e a queda inicial de `CmaFree` pode ser explicada não como perda de memória inacessível, mas como uso, pelo cache de páginas, de páginas livres incluindo páginas CMA movable.

### 8.5 Conclusão operacional

1. Não se deve rejeitar o carregamento de modelo apenas pelo valor absoluto de `CmaFree`. No equipamento real, obteve-se sucesso no carregamento do Qwen mesmo a partir de menos de 1 MB.
2. Registrar `CmaFree` baixo como telemetria, e usar o erro real de alocação de memória do HailoRT como critério de falha.
3. Não confundir o valor observado de `CmaFree`, a falha real de carregamento e o diagnóstico de vazamento; tratá-los nos três estados a seguir.

| Estado | Condição de julgamento | Tratamento no produto | Reinício/investigação |
|---|---|---|---|
| `INCONCLUSIVE` | Apenas queda inicial, menos de 3 vezes, ou não atende à condição de `FAIL` abaixo | Registra telemetria e tenta o carregamento. Não rejeita apenas por `CmaFree` baixo isoladamente | Não reinicia. Adiciona medições nas mesmas condições |
| `OPERATIONAL_FAIL` | O HailoRT retornou um erro real de host-memory allocation | Falha apenas essa requisição de carregamento, para workloads Hailo desnecessários e tenta novamente | Não reinicia em ocorrência isolada. Segue a política operacional apenas se falhas reais se repetirem e não se recuperarem mesmo após liberação de workload. A Phase 0.5 atual apenas registra o `would_fire`, sem reinício automático |
| `FAIL` | Repetição de 3 vezes nas mesmas condições a partir de um estado de CMA baixo, com **redução líquida vs. baseline após liberação superior a 10 MB em 2 ou mais das 3 tentativas**, soma das reduções líquidas positivas das 3 tentativas **superior a 20 MB**, e acompanhada de aumento monotônico de RSS ou queda de `MemAvailable` superior a 128 MB | Registrado como diagnóstico de vazamento, separado da possibilidade de carregamento individual | Retoma a investigação do lado do kernel/HailoRT e coleta evidências diretas. O diagnóstico isolado não dispara reinício automático |

Este critério de 3 tentativas é para diagnósticos futuros e não é aplicado retroativamente a §8.2 desta seção, onde as tentativas em processos independentes foram apenas 2 por driver. A conclusão da 4ª rodada combina o A/B de §8.2 com as 20 gerações/liberações/recarregamentos no mesmo processo e a repetição com CMA baixo de §8.3.
4. A substituição por `FOLL_LONGTERM` é válida como prática geral da DMA API do Linux, mas não teve efeito neste caso, e o equipamento real foi revertido para o vanilla oficial 5.4.0.
5. O julgamento de reinício automático não dispara apenas por `CmaFree` baixo isolado; a observação de falha real de carregamento é uma condição obrigatória.

---

## 9. Próximas ações (em 2026-08-17)

1. O estudo da correção `FOLL_LONGTERM` e sua refutação no equipamento real estão concluídos. O diff para reprodução e o método de restauração foram salvos no apêndice B, e não serão aplicados ao driver de produção.
2. **O lado do produto já foi corrigido**: `core/hailo_device_core/device_manager_genai.py::acquire_genai` foi ajustado na v4.620.8 para registrar `acquire_low_cma_observed` e continuar o carregamento real mesmo quando `CmaFree` estiver abaixo do valor estimado necessário. Apenas erros reais de host-memory retornados pela factory do HailoRT são registrados no tracker de rejeição, e `tests/test_hailo_cma_false_positive.py` fixa a continuidade do carregamento a partir de valores baixos.
3. A descrição do rascunho antigo do fórum, de que "o `LLM(...)` subsequente foi rejeitado pelo HailoRT por host CMA insuficiente", foi reauditada nos logs e na implementação antiga. A sessão de PID 3237 citada como fonte não possui registro de acquire após o release, e todas as rejeições por CMA baixa rastreáveis nos logs do mesmo dia foram do evento próprio `acquire_rejected_low_cma`, ocorrido antes da chamada ao HailoRT. Uma falha que chegou até a factory em outra sessão teve status 8 (`HAILO_INTERNAL_FAILURE`), e não o status 3 de host-memory error. Portanto, não há evidência de OOM do HailoRT que sustente a descrição antiga, e em `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` está explicitado que uma rejeição originada da própria guarda interna foi indevidamente incluída no relato, sendo este retratado.
4. A postagem de correção integrará os números e o escopo de aplicação de §8, a correção da guarda de implementação, a refutação de `FOLL_LONGTERM` e os avisos de instrumentação em um único rascunho atual, sem deixar o rascunho antigo em inglês em forma copiável.
5. A investigação de vazamento do lado do kernel/HailoRT só será retomada caso uma falha real de carregamento ou uma perda cumulativa de memória disponível por repetição venha a se reproduzir. Nesse caso, evidências diretas como `page_owner`, informações de debug de CMA, status de falha de alocação, RSS e `MemAvailable` serão coletadas.

---

## Apêndice A. Procedimento de restauração para v5.3.0

Após um `remove --all` do dkms, a restauração falha em `apt-get install --reinstall` se o `.deb` não permanecer no cache do apt (também falhou neste caso, por não ser possível baixar o pacote). Como o dpkg ainda reconhece o pacote `hailort-pcie-driver` como `ii` (instalado), se o destino de extração do código-fonte do pacote, `/usr/src/hailort-pcie-driver/`, não tiver sido removido, é possível reconstruir manualmente a árvore dkms a partir dele:

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# o dkms.conf precisa ser colocado diretamente na raiz da árvore (dentro de linux/pcie/ causa erro)
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

(comandos com privilégio elevado, tal como no original)

Confirmação da restauração:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → se responder normalmente, a recuperação está concluída
```

`cat` do primeiro comando deve retornar `5.3.0`; a resposta normal do segundo indica restauração concluída.

---

## Apêndice B. Procedimento de armazenamento, aplicação e restauração vanilla do patch de driver do experimento de refutação

### B.1 Material armazenado e posicionamento

O diff real do driver usado no A/B foi salvo integralmente no seguinte arquivo.

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- Código-fonte de referência: `hailo-ai/hailort-drivers` tag `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- Arquivos-alvo: `linux/vdma/ioctl.c`, `linux/vdma/memory.c`, `linux/vdma/vdma.c`

Este patch inclui não apenas a substituição para `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, mas também a instrumentação `CMA_DBG` usada em §7.1. Ou seja, trata-se de um **diff completo de verificação** para reproduzir o módulo experimental do A/B, e não um patch recomendado para produção. O experimento não mostrou efeito, e o equipamento real atual já foi restaurado para o vanilla oficial 5.4.0. Nenhuma alteração foi feita na library de espaço de usuário do HailoRT.

Os valores de identificação confirmados no mesmo kernel/código-fonte/ambiente de compilação são os seguintes.

| Estado | `srcversion` |
|---|---|
| patch experimental | `C84A00ABB326748A1832CE1` |
| vanilla oficial 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 Verificação antes da aplicação

O que se segue só deve ser executado quando `/usr/src/hailo1x_pci-5.4.0` no Raspberry Pi apontar para o commit oficial acima e os 3 arquivos-alvo não tiverem alterações locais. Se o commit, o checksum do patch ou o checksum vanilla de `memory.c` não corresponderem, interromper — o patch não deve ser forçado.

```bash
set -euo pipefail

REPO=/home/pi/GitHub/yu_ai_manager
SRC=/usr/src/hailo1x_pci-5.4.0
PATCH="$REPO/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch"
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_PATCH_SHA=7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
printf '%s  %s\n' "$EXPECTED_PATCH_SHA" "$PATCH" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" apply --check "$PATCH"
```

### B.3 Aplicação do patch experimental

Somente se todas as verificações tiverem sucesso, aplicar o patch e instalar o módulo DKMS para o próximo boot. Não trocar manualmente o módulo em execução via `rmmod` / `modprobe`; alternar por meio de uma reinicialização normal após a compilação.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
PATCH=/home/pi/GitHub/yu_ai_manager/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch
KERNEL_VERSION="$(uname -r)"

sudo git -c safe.directory="$SRC" -C "$SRC" apply "$PATCH"
sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -n hailo1x_pci
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

`modinfo` indica o módulo instalado para o próximo boot; `/sys/module/.../srcversion` indica o módulo atualmente carregado. É normal que os valores sejam diferentes neste ponto. Quando estiver pronto, reiniciar e confirmar que ambos coincidem após a inicialização.

```bash
sudo reboot

# após reconectar
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

No mesmo ambiente de verificação, o valor esperado após a aplicação do patch é `C84A00ABB326748A1832CE1`. Se for diferente, não prosseguir com os testes por suposição; verificar o diff do código-fonte, o kernel e os logs de build do DKMS.

### B.4 Restauração para o vanilla oficial 5.4.0

A restauração não depende da aplicação reversa do patch; os 3 arquivos-alvo são explicitamente restaurados a partir do commit verificado. Isso evita um estado com aplicação parcial ou apenas com a instrumentação remanescente.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c
KERNEL_VERSION="$(uname -r)"

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
sudo git -c safe.directory="$SRC" -C "$SRC" restore --source="$EXPECTED_HEAD" -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -

sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

No mesmo ambiente de verificação, o valor esperado para o módulo vanilla instalado é `A260C39C9F2C06DD4FB072E`. Confirmar que o valor atualmente carregado é diferente, reiniciar e, após reconectar, confirmar que ambos passam a ser `A260C39C9F2C06DD4FB072E`.

---

## Referência: documentos relacionados

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — Dados de medição real, script de reprodução e rascunho de postagem no fórum sobre o vazamento de CMA baseados na medição antiga (conclusão corrigida em §8 deste documento)
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — Registro da migração v5.2.0 → v5.3.0 (alteração do nome do nó de dispositivo `/dev/h1x-0`, etc.)
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — Registro do problema de vazamento de CMA baseado no diagnóstico antigo (conclusão corrigida em §8 deste documento)
- Repositório GitHub `hailo-ai/hailort-drivers` (GPL-2.0, código-fonte aberto): https://github.com/hailo-ai/hailort-drivers
