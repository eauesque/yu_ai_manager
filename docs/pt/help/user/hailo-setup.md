# Configuração do Hailo-10H

Guia de configuração no lado do host para utilizar o Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) com o YU AI Manager. Como a parte relacionada ao hardware e ao SO não pode ser concluída via PyPI, algumas preparações manuais são necessárias.

> **Destinatários**: Somente se você deseja habilitar as extensões Hailo (GenAI Chat / Semantic Search / YOLO Detect / Tagger / Whisper) em um Raspberry Pi 5 (recomenda-se 8 GB) com hardware Hailo-10H. Em ambientes sem hardware Hailo, nenhuma das operações desta página é necessária.

---

## 1. Pré-requisitos

- Raspberry Pi 5 (8 GB são fortemente recomendados; com 4 GB é difícil carregar vários modelos simultaneamente devido às restrições de CMA)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (fixado em `<3.14` via `requires-python` no `pyproject.toml`; o `uv` seleciona automaticamente a versão 3.13)

---

## 2. Instalação do driver PCIe

O Hailo-10H usa o módulo de kernel dedicado `hailo1x_pci` (renomeado do antigo `hailo_pci` a partir do HailoRT 5.3.0).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

Verificação após a reinicialização:

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

Resultados esperados:

- `hailo1x_pci` está carregado
- O nó de dispositivo `/dev/h1x-0` existe (não o antigo `/dev/hailo0`)
- `dmesg` contém as linhas `Firmware loaded in NNNN ms` e `Device created at /dev/h1x-0`

> **Não há problema se `/dev/hailo0` não aparecer.** A partir do HailoRT 5.3.0, `/dev/h1x-0` é o padrão, e esta aplicação reconhece ambos (`core/llm_router/hailo_detect.py`).

---

## 3. Instalação do HailoRT (lado do sistema)

Binário `hailortcli` e biblioteca compartilhada `libhailort.so`. Estes estão incluídos no pacote `hailo-all`, mas se você precisar da versão mais recente, obtenha o `.deb` no Hailo Developer Zone e instale-o sobre a versão existente.

Verificação:

```bash
hailortcli fw-control identify
```

Saída esperada (pontos principais):

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Preparação do wheel Python (`hailort-*.whl`)

Esta é a parte que não está disponível no PyPI. **O wheel Python Hailo para aarch64 também não está disponível no Hailo Developer Zone, portanto, deve ser compilado manualmente.**

### 4.1 Compilar a partir do código-fonte

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# Ao concluir, hailort-5.3.0-cp313-cp313-linux_aarch64.whl é gerado na árvore de build
```

(Consulte o README oficial do Hailo para detalhes do processo de compilação e dependências.)

### 4.2 Colocar o wheel no diretório home

Copie o wheel compilado para **qualquer um dos seguintes locais**; a aplicação o detectará automaticamente na inicialização:

| Caminho de pesquisa (prioridade) | Finalidade |
|---|---|
| Variável de ambiente `$HAILORT_WHEEL` | Caminho completo arbitrário (prioridade máxima) |
| `$HOME/share/` | **Local recomendado** |
| `$HOME/hailort/` | Quando a árvore de build é mantida no local do código-fonte |
| `$HOME/Downloads/` | Local temporário após o download |
| `$HOME/` (diretamente) | Último recurso |

Procedimento recomendado:

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 Mecanismo de instalação automática

Ao executar `./start.sh`, o `scripts/install_hailo.py` é executado:

1. Verifica se `import hailo_platform` é bem-sucedido no venv
2. Somente em caso de falha: procura um wheel **compatível com a versão Python atual (cp313) + arquitetura (aarch64)** nos caminhos de pesquisa acima
3. Instala o wheel mais recente encontrado com `uv pip install`
4. Se nenhum wheel for encontrado ou já estiver instalado: nenhuma ação (operação silenciosa)

Portanto, não é necessário executar `uv pip install` manualmente. Basta colocar o wheel no diretório home e reiniciar `./start.sh`.

---

## 4.4 Colocação dos arquivos de modelo HEF

Coloque os arquivos HEF (modelos compilados para NPU) utilizados pelas extensões em `~/hailo_models/`.

| Arquivo | Finalidade | Tamanho aproximado |
|---|---|---:|
| `yolov8n.hef` | Detecção de objetos YOLO | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **Semantic Search (imagem CLIP)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | Semantic Search (texto CLIP, opcional) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | Reconhecimento de voz | 75–405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM Chat | 2,9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (imagem+texto) | 3,2 GB |

Download direto sem autenticação do bucket S3 do Hailo Model Zoo (formato de URL):

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

Exemplo (encoder de imagem CLIP):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **Se os arquivos HEF estiverem faltando, a extensão será exibida como `Indisponível`.** Por exemplo, se o status do Semantic Search exibir `hailo-10h (CLIP HEF não colocado)`, significa que `clip_vit_b_16_image_encoder.hef` não está em `~/hailo_models/`. Para facilitar a distinção de problemas de hardware ou de runtime Python, a resposta inclui as causas em três níveis: `runtime_ok` / `hardware_ok` / `hef_ok` (passe o cursor sobre o texto de status para ver os detalhes).

Você também pode especificar outro diretório com a variável de ambiente `HAILO_HEF_DIR`.

---

## 5. Parâmetros do kernel (CMA)

Os modelos GenAI do Hailo (LLM/VLM/Whisper) requerem CMA (Contiguous Memory Allocator) para DMA.

Adicione ao final de `/boot/firmware/cmdline.txt`:

```
cma=256M
```

> **No Pi 5 (8 GB), `cma=1G` ou `cma=512M` falham silenciosamente.** Como o kernel padrão aplica `numa=fake=8`, o CMA deve caber dentro do limite de um único nó NUMA (1 GB), e acima de `256M`, `CmaTotal=0` (sem panic). Detalhes: [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

Verificação após a reinicialização:

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB indica sucesso
```

Se o valor for `0 kB`, verifique o valor e reduza-o se necessário.

---

## 6. Coexistência com hailo-ollama (opcional)

Se você executar `hailo-ollama` (a versão Hailo NPU do Ollama) no mesmo dispositivo:

- **HailoRT 5.3.0 e posterior**: Inicie com `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` para compartilhar o dispositivo físico com o lado yu_ai_manager (group_id `YU_SHARED`); o escalonador HailoRT realizará time-slicing em ROUND_ROBIN
- **Antes de 5.2.0**: O group_id não é aceito, portanto é necessário parar `hailo-ollama` com `systemctl stop hailo-ollama` antes de iniciar yu_ai_manager

---

## 7. Verificação de funcionamento

Após iniciar `./start.sh`, a configuração é bem-sucedida se os seguintes itens estiverem habilitados na WebUI em **Configurações → Extensões**:

- `builtin_hailo_genai` (Hailo Chat / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP Semantic Search)
- `builtin_hailo_yolo_detect` (Detecção de objetos YOLO)

Ou diretamente pela CLI:

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. Solução de problemas

### Todas as extensões Hailo exibem «não carregado»

→ O wheel Python pode não estar instalado. Verifique:

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

Em caso de `ModuleNotFoundError`: coloque o wheel no diretório home e reinicie `./start.sh` (§4.2).

### `hailortcli fw-control identify` falha com `HAILO_OPEN_FILE_FAILURE`

→ Problema com o driver ou nó de dispositivo. Verifique se `hailo1x_pci` está carregado em `lsmod | grep hailo1x` e se `ls /dev/h1x-0` existe. Se ambos estiverem faltando, repita §2 e reinicie.

### `HAILO_OUT_OF_HOST_MEMORY` ao carregar LLM/VLM / Pi trava

→ CMA insuficiente. Verifique com `grep CmaTotal /proc/meminfo` se há 256 MB disponíveis (§5). Como `VDevice.release()` não devolve CMA, pode ser necessário reiniciar o processo após trocar entre vários modelos repetidamente.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ Outro processo está ocupando VDevice. Identifique o responsável com `lsof /dev/h1x-0` (tipicamente `hailo-ollama` ou um processo anterior que não terminou corretamente com Ctrl+C), execute `kill` e reinicie.

### Python foi atualizado para 3.14 e é incompatível com o wheel

→ Este repositório está fixado no `pyproject.toml` com `requires-python = ">=3.13,<3.14"`. O primeiro `uv sync` após o clone seleciona 3.13.x. Se `.python-version = 3.14` foi definido manualmente, reverta-o.

---

## 9. Documentação relacionada

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Índice da documentação de desenvolvimento Hailo-10H
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — Notas de migração HailoRT 5.2.0 → 5.3.0
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Detalhes sobre restrições CMA do Pi 5
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — Script de detecção automática de wheel
