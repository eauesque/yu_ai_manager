# GitHub Integration

## Visão geral

O GitHub Integration é uma extensão que permite gerenciar, a partir do YU AI Manager, repositórios, Issues, Pull Requests, Discussions e Releases do GitHub de forma centralizada. Suporta múltiplas contas do GitHub e os tokens são armazenados criptografados com segurança. No dashboard, é possível conferir notificações e estatísticas de repositórios rapidamente, e também há um recurso de triagem de Issues por IA.

## Setup

### Obtenção do Personal Access Token (PAT) do GitHub

1. Faça login no GitHub e abra **Settings > Developer settings > Personal access tokens > Tokens (classic)**
2. Clique em **Generate new token (classic)**
3. Digite um nome para o token e defina a data de expiração
4. No escopo, marque **`repo`** (necessário para acesso total ao repositório)
5. Clique em **Generate token** e copie o token exibido

> **Atenção**: o token só é exibido nesta tela. Copie antes de fechar.

### Adicionando uma conta

1. Clique no card **GitHub** no Extensions launcher, ou acesse diretamente `/ext/github`
2. Abra a aba **Settings**
3. Clique em **Adicionar conta**
4. Preencha as informações:
   - **Label**: nome de exibição da conta (ex.: "Pessoal", "Trabalho")
   - **Token**: o PAT obtido acima
   - **Repositórios**: repositórios a monitorar no formato `owner/repo` (múltiplos possíveis)
5. Após salvar, selecione a conta no dropdown

## Funcionalidades

### Dashboard

Ao selecionar uma conta, o dashboard é carregado automaticamente.

- **Notificações**: lista as notificações não lidas do GitHub
- **Estatísticas do repositório**: exibe número de stars, forks e issues abertas em formato de card
- **Cards resumo**: panorama dos repositórios monitorados de relance

### Issues

- Filtragem por repositório e estado (open/closed)
- Visualização detalhada da Issue (corpo, comentários, labels)
- Criação de nova Issue
- **Função de triagem**: a IA classifica Issues automaticamente
  - `valid_bug` — relato de bug válido
  - `needs_info` — requer informação adicional
  - `skip` — não requer ação
- **Fila de Issues**: faz polling automático de novas Issues do GitHub e as enfileira localmente. Ao se conectar um cliente MCP (Claude Desktop), notifica em lote as não lidas.

### Pull Requests

- Listagem e filtragem de PRs
- Exibição de estatísticas de diff (linhas adicionadas/removidas, número de arquivos alterados)
- Visualização detalhada das alterações por arquivo

### Discussions

- Obtém a lista de discussions via API GraphQL
- Exibição de badges de categoria e badge de "respondida"

### Releases

- Lista as releases mais recentes dos repositórios monitorados
- Consulta das release notes

### Settings

- Adição, edição, exclusão e ativação/desativação de contas
- Exibição do saldo restante de rate limit da API
- Configuração de filtro de idioma e intervalo do scheduler
- Configuração do intervalo de polling da fila de Issues, auto-fechamento de Issues inválidas e notificação na conexão MCP
- Edição dos prompts de triagem para Issues, PRs e Discussions ([ver exemplos](/help/github-triage-examples))

### Fila de Issues

A fila de Issues faz polling periódico do GitHub e salva as Issues novas localmente.

- **Polling**: executado automaticamente pelo scheduler (intervalo configurável, padrão 60 minutos)
- **Notificação**: ao conectar MCP, notifica o Claude Desktop em lote sobre Issues não processadas
- **Triagem**: cada Issue na fila pode ser classificada como válida ou inválida
- **Auto-fechamento**: fecha automaticamente no GitHub, com comentário de template, Issues julgadas inválidas
- **Polling manual**: ao clicar em "Poll Now" em Settings, a obtenção ocorre imediatamente

### Prompts de triagem

É possível personalizar os textos de instrução à IA usados na triagem de Issues, PRs e Discussions.

- Há prompts editáveis separados para cada tipo (Issue, PR, Discussion)
- Prompts padrão são fornecidos; o "Restaurar padrão" permite recuperá-los a qualquer momento
- Para templates em múltiplos idiomas e estilos, consulte os [exemplos de prompt de triagem](/help/github-triage-examples)
- Os prompts são salvos em config.json (sem criptografia, por não conterem informações sensíveis)

## Integração com MCP

O GitHub Integration oferece 12 ferramentas MCP, que podem ser operadas diretamente a partir do Claude Code.

- Obtenção de lista e detalhes de Issues
- Obtenção de lista e detalhes de PRs
- Obtenção de notificações
- Obtenção e atualização de prompts de triagem
- Gerenciamento da fila de Issues (lista de pendentes, triagem, rejeição, polling)

Com as ferramentas MCP, você pode consultar informações do GitHub sem sair da IDE enquanto edita código.

## Dicas

- **Múltiplas contas**: separar contas por uso (pessoal e trabalho, por exemplo) facilita o gerenciamento
- **Permissão do token**: com o escopo `repo`, todas as funções básicas ficam disponíveis. Para acessar repositórios privados de Organizations, é necessária autorização SSO separada na Organization
- **Uso da triagem**: em repositórios com muitas Issues, a triagem automática por prioridade é eficiente
- **Rate limit**: a API do GitHub possui um limite de requisições por hora. Verifique o saldo na aba Settings
- **Segurança do token**: o token é armazenado criptografado no lado servidor. Ele nunca é salvo em texto plano
- **Atualização do dashboard**: ao trocar de conta, os dados são obtidos novamente de forma automática
