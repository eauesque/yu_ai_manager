# Diretrizes de Segurança da API

Use este documento sempre que adicionar ou alterar um endpoint da API.

## Primeira decisão

Cada endpoint deve ser classificado antecipadamente como um dos seguintes:

- `public`
- `session/user`
- `admin`
- `localhost-only`

Se não tiver certeza, escolha `admin`.

## Regras centrais

1. Não assuma que `GET` é seguro.
2. `read-only API keys` são apenas para leituras simples.
3. Caminhos internos, inventários, histórico, conteúdo, logs e resultados de análise são `admin`.
4. As verificações de localhost devem usar auxiliares cientes de proxy.
5. Os endpoints de configuração exigem listas de permissões e validação rigorosa.
6. Os segredos devem ser criptografados e obscurecidos por meio de auxiliares compartilhados.

## Não seguro para chaves somente leitura

- caminhos internos
- inventários de ID de arquivo/membro
- prompts, anotações, transcrições, logs de chat
- resultados OCR / análise
- fila, histórico, auditoria, aprovação, agendador, estado de erro de varredura
- estado de backend de extensão / perfil / backup / webhook / segredo
- resultados buscados com credenciais de terceiros armazenadas

## Verificações de localhost

Não use diretamente:

```
request.remote_addr == "127.0.0.1"
```

Use auxiliares existentes:

- `get_client_ip()`
- `is_local_request()`
- `is_loopback_request()`

## Regras de endpoint de configuração

Obrigatório:

- lista de permissões de chaves
- validação de tipo rigorosa
- validação de intervalo / enumeração / URL
- obscurecimento de segredo em leituras
- armazenamento criptografado para segredos

Proibido:

- `config.update(...)` cego
- `bool(value)` para booleanos de solicitação
- mesclagens genéricas que contornam a manipulação de segredos

## Segredos

- nunca retorne valores de segredo atuais
- nunca inclua tokens/cabeçalhos/blobs secretos em endpoints de lista
- nunca sobrescreva segredos existentes com espaços reservados mascarados
- sempre use um armazenamento dedicado ou auxiliar compartilhado

## Solicitações de saída de APIs

Não faça sondagens upstream ou buscas de descoberta a partir de endpoints `GET`.

Se inevitável:

- requeira `admin`
- mantenha os tempos limite curtos
- bloqueie localhost / IP privado / destinos de metadados

## Testes mínimos

Para endpoints sensíveis, adicione:

1. `read-only key -> 403`
2. `admin key -> 200`
3. `invalid input -> 400`
4. verificações de obscurecimento de segredo
5. testes de regressão de localhost cientes de proxy onde relevante

## Lista de verificação de revisão

- Este `GET` é realmente seguro para acesso público/somente leitura?
- Ele expõe caminhos, inventários, prompts, transcrições, histórico ou metadados brutos?
- Ele vaza segredos?
- Usa auxiliares cientes de proxy?
- Evita coerção booleana implícita?
- Evita mesclagens de configuração cegas?
- Evita solicitações de saída não intencionais?
- Inclui testes de regressão de escopo de administrador?

Política padrão: comece restrito, depois abra deliberadamente apenas quando necessário.
