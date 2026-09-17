# SNS Share & Bluesky Monitor

## Visão geral

O SNS Share é uma extensão que permite compartilhar imagens geradas por IA no Bluesky ou no X (Twitter) diretamente a partir do YU AI Manager. O texto da postagem é gerado automaticamente a partir de templates personalizáveis, e variáveis de metadados da imagem são expandidas automaticamente. O Bluesky Monitor adiciona a função de monitorar notificações, com triagem por IA e resposta automática.

## Setup

### Obtenção do App Password do Bluesky

1. Faça login em [bsky.app](https://bsky.app) e abra **Settings > App Passwords**
2. Clique em **Adicionar App Password**
3. Digite um nome (ex.: "YU AI Manager") e clique em **Criar App Password**
4. Copie a senha exibida

> **Atenção**: o App Password só é exibido nesta tela. Copie antes de fechar o diálogo. Nunca use a senha principal do Bluesky.

### Configuração no YU AI Manager

1. No menu de navegação, abra **Settings**
2. Troque para a aba **SNS**
3. Preencha as informações:
   - **Handle do Bluesky**: seu handle (ex.: `yourname.bsky.social`)
   - **App Password**: o App Password obtido acima
   - **Template de postagem**: template do texto da postagem (ver [variáveis de template](#variáveis-de-template))
4. Clique em **Salvar**

### Teste de conexão

Após salvar as credenciais, clique em **Testar conexão** para confirmar a autenticação com o Bluesky. Em caso de sucesso, o handle e o nome de exibição são mostrados.

## Funcionalidades

### Compartilhamento no Bluesky

Compartilhe imagens diretamente no Bluesky pela tela de detalhes da imagem.

1. Abra a modal de detalhes da imagem
2. Clique no botão **SNS**
3. Confira e edite o texto de postagem gerado
4. Clique em **Postar no Bluesky**

- O texto de postagem é gerado expandindo as variáveis de metadados a partir do template configurado
- A imagem é comprimida/redimensionada automaticamente para o limite de upload de 1 MB do Bluesky
- A postagem é limitada a **300 graphemes** (o excedente é automaticamente truncado)
- É possível escolher anexar ou não a imagem

### Compartilhamento no X (Twitter)

Use o Web Intent (abre a tela de postagem do X no navegador) para compartilhar informações da imagem no X.

1. Abra a modal de detalhes da imagem
2. Clique no botão **SNS**
3. Clique em **Compartilhar no X**

Uma nova aba do navegador abre com a tela de postagem do X, com o texto gerado a partir do template preenchido. Você pode editar o texto antes de postar. No X a imagem não é anexada automaticamente, então é necessário anexá-la manualmente.

### Bluesky Monitor

O Bluesky Monitor faz polling das notificações do Bluesky, enfileira localmente, faz triagem e responde.

#### Tipos de notificação

- **Menção**: você foi mencionado em um post
- **Resposta**: sua postagem recebeu uma resposta
- **Quote**: sua postagem foi citada
- **Follow**: alguém começou a te seguir
- **Like**: sua postagem recebeu um like
- **Repost**: sua postagem foi repostada

#### Polling

As notificações são obtidas automaticamente em intervalos configuráveis (padrão: 30 min, mínimo: 5 min). Também é possível disparar um polling imediato pelas Settings ou por ferramentas MCP.

#### Sistema de fila

Cada notificação entra na fila com status **pending** (não processada). Depois, pode transitar para:

- **notified** — já notificado ao cliente MCP (Claude Desktop)
- **dismissed** — dispensada por não precisar de ação

#### Triagem

A classificação por IA julga se cada notificação precisa de ação:

- **valid** — requer ação (pergunta, relato de bug, pedido de colaboração etc.)
- **invalid** — pode ser ignorada (elogio genérico, spam, conteúdo de bot etc.)

Existem prompts de triagem personalizáveis por tipo de notificação (menção, resposta, quote). Os prompts padrão vêm prontos e podem ser restaurados a qualquer momento.

#### Resposta automática

Para menções/respostas/quotes classificadas como valid, é possível enviar respostas automáticas baseadas em template:

- Ative a resposta automática nas configurações do Monitor
- Personalize templates de resposta por tipo de notificação
- Respostas são limitadas a 300 graphemes

#### Descarte automático

Follows, likes e reposts podem ser descartados automaticamente para reduzir o ruído na fila. Cada tipo pode ser alternado individualmente nas Settings.

#### Notificação na conexão MCP

Ao conectar um cliente MCP (Claude Desktop), as notificações não processadas são reportadas em conjunto para que você possa revisá-las durante sessões de desenvolvimento.

### Settings

As configurações de SNS ficam na aba **SNS** da página Settings:

- **Credenciais do Bluesky**: handle e App Password (senha salva criptografada, exibida mascarada)
- **Template de postagem**: texto de template com placeholders de variáveis
- **Configuração do Monitor**:
  - Intervalo de polling (minutos)
  - Descarte automático de follow/like/repost
  - Ativar/desativar resposta automática
  - Prompts de triagem para menção/resposta/quote
  - Templates de resposta automática para menção/resposta/quote

## Integração com MCP

O SNS Share & Bluesky Monitor disponibiliza 15 ferramentas MCP:

**Compartilhamento (6 ferramentas)**:
- `share_to_bluesky` — posta imagem no Bluesky
- `get_x_share_url` — obtém a URL Web Intent do X
- `get_sns_preview` — preview da expansão do template
- `test_bluesky_connection` — testa conexão com a API
- `get_sns_config` / `save_sns_config` — obter/salvar configuração de SNS

**Fila de notificações (5 ferramentas)**:
- `bsky_get_pending_notifications` — obtém notificações não processadas
- `bsky_get_notification_queue` — obtém itens da fila com filtro
- `bsky_triage_notification` — define resultado de triagem (valid/invalid)
- `bsky_send_auto_response` — envia resposta a uma notificação
- `bsky_poll_notifications` — dispara polling imediato

**Configuração do Monitor (4 ferramentas)**:
- `bsky_get_monitor_config` / `bsky_save_monitor_config` — obter/salvar configuração do Monitor
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` — obter/salvar prompts de triagem e templates de resposta

## Variáveis de template

Variáveis disponíveis no template de postagem:

| Variável | Descrição |
|---|---|
| `{positive_short}` | Prompt positivo (primeiros 100 caracteres) |
| `{positive}` | Prompt positivo completo |
| `{negative_short}` | Prompt negativo (primeiros 50 caracteres) |
| `{model}` | Nome do modelo |
| `{seed}` | Valor da seed |
| `{steps}` | Passos de sampling |
| `{cfg}` | Escala CFG |
| `{sampler}` | Nome do sampler |
| `{size}` | Tamanho da imagem |
| `{tags}` | Top 5 tags |
| `{filename}` | Nome do arquivo |

Template padrão: `{positive_short}`

## Dicas

- **Segurança do App Password**: use sempre o App Password, nunca a senha principal do Bluesky. O App Password pode ser desativado a qualquer momento nas configurações do bsky.app
- **Rate limits**: a API do Bluesky possui limites de taxa. Evite postagens consecutivas. Upload de imagem também conta no rate limit
- **Contagem de graphemes**: o limite de 300 caracteres do Bluesky usa grapheme clusters, não caracteres. Caracteres CJK contam como 1 grapheme
- **Compressão de imagem**: imagens acima de 1 MB são redimensionadas automaticamente. Se a preparação da imagem falhar, a postagem é feita apenas com texto
- **Intervalo de polling do Monitor**: configure o intervalo conforme o volume de notificações. Para contas com muitas notificações, intervalos curtos são eficazes
- **Descarte automático**: ative o descarte automático de follow/like/repost para focar nas notificações que requerem ação
- **Prompts de triagem**: personalize os prompts de triagem para combinar com seu estilo de comunicação e os tipos de interação que recebe
