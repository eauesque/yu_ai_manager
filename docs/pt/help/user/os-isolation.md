# Guia de Isolamento em Nível de SO

Função que limita, pelos mecanismos de segurança do SO, o impacto que uma Extension pode ter sobre o sistema.

## 1. O que é o isolamento de SO

Quando instalamos um app no smartphone, aparece algo como "Este aplicativo está solicitando acesso à câmera", certo? O isolamento de SO segue a mesma ideia.

Com base nas permissões declaradas pela Extension (leitura/gravação de arquivo, comunicação de rede, execução de comando externo etc.), **o kernel do SO bloqueia fisicamente as operações não autorizadas**. Não importa qual técnica o código Python use: as restrições no nível do kernel não podem ser contornadas.

> **Atenção**: esta função é voltada principalmente para usar Extensions de terceiros com segurança. Extensions `builtin-*` são tratadas como confiáveis (L0) e operam sem restrições.

---

## 2. Plataformas suportadas

| SO | Modo de isolamento | Maturidade |
|----|---------|--------|
| **Linux** | AppArmor (Mandatory Access Control) | Recomendado, pronto para produção |
| **macOS** | sandbox-exec (Seatbelt) | Experimental (desencorajado pela Apple) |
| **Windows** | Restricted Token + Job Object | Restrições básicas de recursos |

O AppArmor do Linux é o mais maduro e é o ambiente recomendado.

---

## 3. Setup no Linux (AppArmor)

### 3.1 O que é o AppArmor

AppArmor é um módulo de segurança embutido no kernel Linux. Para cada processo, define em um profile "quais arquivos podem ser lidos/escritos" e "se a comunicação de rede é permitida", e o kernel impõe essas regras.

Em Ubuntu / Debian ele costuma vir ativado por padrão, mas em algumas distribuições, como o Raspberry Pi OS, é preciso ativar manualmente.

### 3.2 Setup automático

É possível configurar de uma só vez com o script de setup incluído.

```bash
sudo bash scripts/setup-apparmor.sh
```

Esse script faz o seguinte:

1. **Verifica/instala pacotes do AppArmor** — instala automaticamente `apparmor`, `apparmor-utils` se não existirem
2. **Adiciona parâmetro de kernel** — adiciona `lsm=apparmor` em `/boot/firmware/cmdline.txt` (com backup)
3. **Instala regra de sudoers** — permite executar apenas o comando `apparmor_parser` sem senha (princípio do menor privilégio)
4. **Habilita o serviço do AppArmor** — configura auto-start via systemd

> **Para sistemas diferentes do Raspberry Pi OS**: em ambientes que usam GRUB, adicione manualmente `lsm=apparmor` em `GRUB_CMDLINE_LINUX` em `/etc/default/grub` e execute `sudo update-grub`, como o script indica.

### 3.3 Reiniciar

Após adicionar o parâmetro de kernel, é necessário reiniciar.

```bash
sudo reboot
```

### 3.4 Confirmação de funcionamento

Após reiniciar, confirme se o AppArmor está ativo com o comando abaixo.

```bash
# Verifica se o módulo de kernel está ativo
cat /sys/module/apparmor/parameters/enabled
# → se aparecer "Y", está ativo

# Lista dos profiles carregados
sudo aa-status
```

### 3.5 Ativação em config.json

Após confirmar que o AppArmor está ativo, adicione o seguinte em `config.json`.

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    }
  }
}
```

Com isso, ao iniciar Extensions de terceiros, um profile do AppArmor é gerado e carregado automaticamente.

---

## 4. Referência dos itens de configuração

Controlado pela seção `os_isolation` de `config.json`.

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    },
    "macos": {
      "sandbox_exec": false
    },
    "windows": {
      "restricted_token": true,
      "job_object": true,
      "job_limits": {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10
      }
    }
  }
}
```

| Chave | Tipo | Padrão | Descrição |
|------|------|-----------|------|
| `enabled` | bool | `false` | Ativar/desativar toda a função de isolamento de SO |
| `linux.apparmor` | bool | `true` | Usar profile AppArmor |
| `macos.sandbox_exec` | bool | `false` | Usar sandbox-exec do macOS (experimental) |
| `windows.restricted_token` | bool | `true` | Iniciar o processo com token restrito |
| `windows.job_object` | bool | `true` | Limitar recursos com Job Object |
| `windows.job_limits.memory_mb` | int | `512` | Memória máxima por Extension (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | Limite de uso de CPU por Extension (%) |
| `windows.job_limits.max_processes` | int | `10` | Número máximo de processos que uma Extension pode gerar |

---

## 5. Correspondência entre permissões da Extension e regras AppArmor

De acordo com as permissões declaradas em `extension.json`, o profile AppArmor é gerado automaticamente.

| Permissão da Extension | Controle no AppArmor |
|---------------|-------------------|
| `db:read` | Permite apenas leitura do diretório `data/` |
| `db:write` | Permite leitura/gravação do diretório `data/` |
| `fs:read:scan_roots` | Permite leitura das scan roots configuradas |
| `fs:write:any` | Permite leitura/gravação em todos os caminhos |
| `network:local` | Permite sockets TCP/Unix (rejeita UDP) |
| `network:internet` | Permite todos os sockets TCP/UDP/Unix |
| `subprocess` | Permite execução de `/usr/bin/`, `/bin/` etc. |
| Sem permissão de rede | Rejeita explicitamente TCP/UDP, permite apenas Unix socket para IPC |
| Sem permissão de subprocess | Rejeita explicitamente execução de `/usr/bin/`, `/bin/` etc. |

O diretório da própria Extension (`extensions/<name>/`) sempre permanece com permissão de leitura/gravação.

---

## 6. Verificação pela API

É possível verificar o estado do isolamento de SO pela API.

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

Exemplo de resposta (Linux / AppArmor ativo):

```json
{
  "platform": "linux",
  "available": true,
  "method": "apparmor",
  "details": {
    "apparmor_kernel": "enabled",
    "apparmor_tools": true,
    "apparmor_sudoers": true,
    "aa_exec_path": "/usr/sbin/aa-exec"
  }
}
```

Quando `available` é `false`, o campo `setup` contém o procedimento de configuração.

---

## 7. Troubleshooting

### AppArmor não ativa

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" ou o arquivo não existe
```

**Causa**: o parâmetro de kernel não foi aplicado.

**Solução**:
- Raspberry Pi OS: verifique se há `lsm=apparmor` em `/boot/firmware/cmdline.txt` e reinicie
- Ambiente GRUB: confirme `GRUB_CMDLINE_LINUX="... lsm=apparmor"` em `/etc/default/grub`, execute `sudo update-grub && sudo reboot`

### Ao iniciar a Extension aparece "sudoers not configured"

**Causa**: a regra de sudoers com NOPASSWD para `apparmor_parser` não está configurada.

**Solução**:
```bash
sudo bash scripts/setup-apparmor.sh
```

O script instala a regra necessária em `/etc/sudoers.d/yu-ai-apparmor`.

### Extension não funciona por falta de permissão

**Causa**: as permissões necessárias não estão declaradas em `extension.json`.

**Solução**: adicione as permissões necessárias em `permissions.required` no `extension.json` da Extension, ou conceda manualmente pelas Settings > Extensions.

### Verificação manual do profile AppArmor

Os profiles gerados são salvos em `/tmp/yu_ai_apparmor/`.

```bash
# Consultar o conteúdo do profile
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>

# Lista dos profiles do YU AI Manager carregados atualmente
sudo aa-status | grep yu_ai_ext
```

---

## 8. Observações sobre segurança

O isolamento de SO é parte de uma defesa em camadas. O YU AI Manager garante a segurança em várias camadas:

1. **Análise estática** (Fase 1) — analisa a AST do código da Extension no momento da instalação e detecta imports perigosos
2. **Gatekeeper de permissões** (Fase 2-3) — controla os acessos via ServiceRegistry por Proxy com verificação de permissões
3. **Isolamento de SO** (Fase 4) — no nível do kernel, impõe restrições de arquivo, rede e execução de processos

O isolamento de SO sozinho não elimina todos os riscos, mas combinado com as outras camadas de defesa oferece um ambiente para usar com segurança Extensions de terceiros.

Ao instalar Extensions não confiáveis, recomenda-se usá-las em um ambiente Linux com isolamento de SO ativado.
