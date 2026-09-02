# Autodiagnóstico e Relatório de Problemas

Se o YU AI Manager não funciona ou apresenta comportamento anormal, este guia ajuda você a reunir informações sobre a causa para relatar aos desenvolvedores. Não é necessário ter conhecimento de comandos ou Git.

## 1. Primeiro, clique em "Relatar Problema"

1. Abra o aplicativo no navegador e, no menu do canto superior direito, selecione **Diagnostics** (Diagnósticos).
2. Clique no botão **"Relatar Problema"**.
3. Após algum tempo, uma pasta chamada `repair/2026XXXX-HHMMSS/` será criada. Seu conteúdo é o seguinte conjunto de relatório automático:
   - Informações do ambiente, logs recentes, configurações (informações pessoais e tokens são mascarados)
   - Modelos de prompts para reparo por IA

Clique em **"Abrir Pasta"** para abrir essa pasta no Explorer. Use **"Compactar em ZIP"** para agrupar tudo em um único arquivo zip.

> Sobre o mascaramento: nomes de usuários, e-mails, strings semelhantes a chaves de API e endereços de IP são automaticamente substituídos por `<REDACTED>`. Como isso não é perfeito, revise o conteúdo antes de compartilhar.

## 2. Compartilhe o Arquivo

Anexe o arquivo ZIP a desenvolvedores, suporte ou Discord. O botão **"Copiar Mensagem para Discord"** também oferece um texto curto pronto para colar.

## 3. Soluções Temporárias que Você Pode Tentar

### 3-A. Verificação do Ambiente (doctor)

Na tela de diagnóstico, clique em **"Diagnóstico do Ambiente"** para exibir o status de Python, GPU, banco de dados, etc. em markdown. Siga sequencialmente as sugestões de correção (`fix_hint`) nos itens em vermelho (ERROR) ou amarelo (WARN).

### 3-B. Reiniciar em Safe Mode

Se a inicialização normal não funciona, o aplicativo travar ou ficar carregando indefinidamente, você pode iniciar em **Safe Mode**.

- Windows: clique duas vezes em `start.bat --safe-mode` (ou adicione ` --safe-mode` ao final do atalho)
- macOS / Linux: no terminal, execute `./start.sh --safe-mode`

Em Safe Mode, você pode:

- Verificar as configurações
- Usar "Relatar Problema" e "Diagnóstico do Ambiente"
- Aplicar **pacotes de atualização seguros (update.zip)** fornecidos pelos desenvolvedores (apenas substituição de arquivos, scripts de reparo automático desabilitados)

O Safe Mode permanece ativo até a próxima inicialização normal. Reinicie normalmente para retornar ao modo normal.

### 3-C. Aplicar Pacote de Atualização (update.zip)

Se você recebeu `update.zip` dos desenvolvedores:

1. Vá para Diagnóstico → seção **"Aplicar Atualização"**
2. Selecione o arquivo e confirme que **Validação (Verify)** fica verde
3. Clique em **Aplicar** no diálogo de confirmação
4. Siga as instruções exibidas para reiniciar

> Nunca aplique um arquivo zip se a validação ficar vermelha. Pode estar corrompido ou ser um pacote para outro aplicativo.

Se algo der errado, use **"Reverter Atualização Anterior (Rollback)"** para voltar ao estado anterior.

## 4. O Que NÃO Fazer

- Não coloque logs brutos (antes do mascaramento) em redes sociais ou fóruns públicos
- Não aplique `update.zip` de origem desconhecida
- Não edite manualmente a pasta `data/` ou `tags.db`

## Se Ainda Não Funcionar

Se o problema persistir, envie o arquivo ZIP junto com uma descrição de "que operação foi realizada e o que aconteceu". Os desenvolvedores usarão `prompt_for_codex.md` / `prompt_for_claude.md` para gerar uma proposta de patch de correção.
