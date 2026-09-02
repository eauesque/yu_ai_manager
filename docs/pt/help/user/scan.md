# Scan

## Registro de pastas de scan

Adicione as pastas alvo do scan na aba Settings > Scan.

- Reordenável por drag & drop
- Ative/desative pela caixa de seleção
- Possível registrar várias pastas

## Execução do scan

- O scan começa automaticamente ao adicionar uma pasta
- O scan manual pode ser executado pela página Tools ou pelo `trigger_scan` via MCP
- O progresso durante o scan é notificado em tempo real por SSE

## Scan automático (Watcher)

Ao ativar a Extension Auto Scan Watcher, alterações de arquivos nas pastas registradas são detectadas automaticamente e escaneadas.

## Sistemas de arquivos remotos

Ao escanear paths remotos como WSL / NAS / SMB, ajuste as configurações de timeout na aba Settings > Remote FS.

## Scan em bibliotecas grandes

Pontos de atenção ao escanear centenas de milhares a mais de um milhão de arquivos:

- **Busca de imagens possível durante o scan**: a API de busca usa conexão de banco somente leitura, portanto não sofre com o bloqueio de escrita durante o scan
- **Gestão automática do WAL**: durante o scan, a cada 2.000 arquivos é executado automaticamente um checkpoint do WAL, evitando o inchaço do arquivo WAL
- **Evento scan.db_busy**: eventos SSE são enviados no início/fim do scan, permitindo exibir o estado de "ocupado" no front-end

## Processo worker do scan

A partir da v3.27.0, o scan é executado em um processo separado, independente do web_ui.py.
Com isso, **reiniciar o web_ui não interrompe o scan**.

### Como funciona

- Ao iniciar o scan pela WebUI, um processo worker é iniciado em background
- O worker grava arquivos de progresso (JSON) e PID em `/tmp/yu-scan/`
- A WebUI faz polling desse arquivo de progresso e repassa para o front-end via SSE
- Ao reiniciar a WebUI, ela detecta automaticamente o worker em execução e reconecta a exibição de progresso

### Operação via CLI

O worker também pode ser operado diretamente pela CLI. Funciona mesmo com a WebUI parada.

```bash
# Verificar estado
python -m core.scan.scan_worker status

# Parar o scan em execução (graceful shutdown — salva a posição de interrupção no DB)
python -m core.scan.scan_worker stop

# Iniciar scan diretamente pela CLI
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images

# Opções
#   --recursive / --no-recursive  incluir subdiretórios (padrão: recursive)
#   --scan-zips                   também escanear imagens dentro de ZIP/7z
#   --force                       reescanear também arquivos existentes
#   --resume                      retomar um scan interrompido
#   --config config.json          especificar arquivo de configuração
```

### Mecanismos de segurança

- **Monitoramento do processo pai**: o worker iniciado pela WebUI monitora, a cada 60 segundos, se o processo da WebUI continua vivo. Se a WebUI encerrar de forma anormal, o worker salva a interrupção e para automaticamente
- **Suporte a SIGTERM**: ao enviar SIGTERM com `stop` ou `kill`, o worker termina o processamento atual, faz commit no DB, salva a posição de interrupção e encerra
- **Prevenção de duplicidade**: não há múltiplos workers rodando simultaneamente

### Troubleshooting

Se o worker não responder:

```bash
# Confirmar o PID
cat /tmp/yu-scan/worker.pid

# Forçar o término do processo
kill -9 $(cat /tmp/yu-scan/worker.pid)

# Limpar arquivos residuais
rm -f /tmp/yu-scan/worker.pid /tmp/yu-scan/progress.json
```

## Erros de scan

Quando ocorrem erros durante o scan, eles podem ser consultados via `get_scan_errors` do MCP.
