# Coleção de Exemplos de Prompts de Triagem do GitHub

Prompts de triagem são instruções enviadas à IA para classificar issues / PRs / discussions do GitHub. Você pode editá-los livremente em **GitHub Integration > Settings > Triage Prompts**.

Copie os exemplos abaixo e personalize-os.

---

## Prompt para Issue

### Padrão (inglês, rigoroso)

```
Review the following GitHub issue and determine whether it is a technically valid bug report.

Valid (valid) criteria:
- Concrete reproduction steps are provided
- Error log or stack trace is included
- Environment info (OS, version, etc.) is present

Invalid (invalid) criteria:
- Emotional text only, no technical facts
- Feature request, not a bug
- Written in a language other than English
- No actionable technical information

Return your verdict (valid / invalid) and the reason.
```

### Versão em japonês

```
Examine cuidadosamente a issue do GitHub abaixo e decida se é um relato de bug tecnicamente válido.

Critérios de valid (válido):
- Passos de reprodução descritos concretamente
- Log de erro ou stack trace presente
- Informações de ambiente (OS, versão etc.) presentes

Critérios de invalid (inválido):
- Apenas texto emocional
- Pedido de nova funcionalidade
- Escrita em idioma diferente de inglês
- Sem nenhum fato técnico

Retorne o resultado da decisão e o motivo.
```

### Critério relaxado (aceita também pedidos de funcionalidade)

```
Classifique a issue do GitHub abaixo.

Categorias:
- valid_bug: há passos de reprodução, informações de erro ou descrição clara de comportamento inesperado.
- feature_request: pedido de nova funcionalidade ou melhoria. Tratar como válido.
- needs_info: pode ser válido, mas faltam informações importantes. Tratar como válido e adicionar uma nota.
- invalid: spam, irrelevante ou apenas texto emocional sem conteúdo técnico.

Retorne em uma linha a categoria e o motivo.
```

### Rigoroso (foco em segurança)

```
Avalie esta issue do GitHub do ponto de vista de impacto em segurança e validade técnica.

CRITICAL (ação imediata):
- Relato de vulnerabilidade de segurança, vazamento de dados ou bypass de autenticação
- Inclui PoC ou detalhes de exploit

VALID (bug comum):
- Bug técnico com passos de reprodução e evidência de erro

INVALID (rejeitar):
- Pedido de funcionalidade, perguntas, descontentamento emocional, não inglês, sem fato técnico

Retorne CRITICAL / VALID / INVALID e o motivo.
No caso de CRITICAL, indique que é necessária revisão humana imediata.
```

### Multilíngue (aceita outros idiomas além do inglês)

```
Independentemente do idioma, decida se esta issue do GitHub é um relato de bug válido.

Válido: há passos de reprodução, log de erro ou descrição técnica clara em qualquer idioma.
Inválido: apenas emocional, spam, sem conteúdo técnico.

Retorne a decisão e o motivo em inglês.
```

---

## Prompt para PR

### Padrão (rejeita todos)

```
Do not accept pull requests. Close automatically.
```

### Aceitação com revisão

```
Revise a qualidade de código e a relevância deste pull request.

Aceitar (valid):
- Correção de bug documentado ou atende a uma issue aberta
- Código seguindo as convenções do projeto
- Inclui testes ou plano de testes

Rejeitar (invalid):
- Alterações não relacionadas ou expansão de escopo
- Sem referência a issue
- Quebra de funcionalidade existente

Retorne accept / reject e o motivo.
```

### Aceitar apenas correções de bug

```
Aceite apenas pull requests de correção de bug.

Válido: com referência a issue aberta, correção focada, escopo mínimo.
Inválido: adição de funcionalidade, refatoração, apenas documentação, alterações não relacionadas.

Retorne a decisão e o motivo.
```

---

## Prompt para Discussion

### Padrão (fechar todas)

```
Discussions are closed. No action required.
```

### Monitoramento de relatos de bug

```
Verifique se esta Discussion contém um bug não reportado.

Se houver descrição de bug reproduzível com detalhes de erro,
sinalize como "potential_bug" para criação de issue.
Caso contrário, retorne "no_action".

Retorne potential_bug / no_action e o motivo.
```

### Suporte à comunidade

```
Classifique esta Discussion:

- question: usuário pedindo ajuda. Se houver resposta clara na documentação, responder.
- bug_report: descrição de bug. Sinalizar para criação de issue.
- feature_idea: sugestão interessante de funcionalidade. Sinalizar para revisão.
- off_topic: não relacionada ao projeto. Nenhuma ação necessária.

Retorne a categoria e a ação recomendada (quando aplicável).
```
