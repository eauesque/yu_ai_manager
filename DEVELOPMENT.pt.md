# Guia de desenvolvimento

Um manual para estender, personalizar e depurar este software por conta própria.

---

## A ideia básica

Este software foi criado por um ser humano que dava instruções e reclamações a um agente de IA.
Cada linha de código foi escrita pela IA.

Em outras palavras: **você pode fazer a mesma coisa.**

Você não precisa ser programador. Você não precisa perguntar ao autor. Tudo o que você precisa é a vontade de pensar claramente, explicar com precisão e repetir.

Você não precisa daquela coisa com texto branco rolando em uma tela preta.
Abandone primeiro esse preconceito.
Tudo pode ser feito visualmente agora. Que época para se viver.

---

## Antes de começar

### Obter o YU AI Manager

Basta executar o instalador.
Siga as instruções na tela. É isso.

Uma coisa a lembrar:
Não há atualização automática no momento. Quando uma nova versão sair, execute o instalador novamente para substituí-la.

### Conectar o MCP

Abra o YU AI Manager e vá para **Configurações → Chaves de API**.
Há uma seção chamada **Snippet de conexão MCP**. Copie o JSON com um clique.

Em seguida, abra o Claude Desktop e vá para **Configurações (ícone de engrenagem) → Desenvolvedor → Editar configuração**.
Cole o JSON copiado, salve e reinicie o Claude Desktop.

É isso. Isso é tudo que é preciso para conectar.

**Sobre as chaves de API:** Se quiser configurar manualmente sem o Snippet, crie uma chave nas mesmas **Configurações → Chaves de API**. As chaves que começam com `sk_...` são mostradas apenas uma vez na criação. Copie-a no momento.

### Verificar seu ambiente

1. O YU AI Manager está em execução? — Inicie-o e verifique
2. O servidor MCP está em execução? — Verifique nas configurações do Claude Desktop
3. Você tem acesso a um agente de IA? — Claude Desktop, ou algo equivalente

É isso. Você está pronto.

---

## Usar o MCP

Se o servidor MCP estiver em execução, use-o. Ponto.

O YU AI Manager tem endpoints de ajuda integrados para agentes de IA.
Através do MCP, você pode acessar diretamente o banco de dados, logs, configurações e **o próprio código-fonte**.
Deixar a IA olhar diretamente pelo MCP é mais rápido e preciso do que explicar pela interface do navegador.

Diga apenas isso ao agente de IA:

```
Conecte-se ao servidor MCP do YU AI Manager.
Verifique os endpoints de ajuda e me diga o que você pode fazer.
```

### Deixar o MCP ler o código-fonte

O YU AI Manager tem ferramentas de referência de código-fonte integradas.

- **source_tree** — Exibe a estrutura de arquivos como uma árvore
- **source_read** — Lê o conteúdo de um arquivo especificado
- **source_search** — Pesquisa de texto completo em todo o código-fonte

Os agentes de IA podem usá-las para ler o código-fonte diretamente no chat.
Não é necessário abrir uma pasta no GitHub Desktop e entregá-la ao Claude Code.

Quando quiser que a IA olhe o código-fonte, diga isto:

```
Verifique a estrutura de arquivos com source_tree,
depois leia os arquivos relevantes com source_read.
```

---

## Adicionar funcionalidades

Não peça ao autor para adicionar funcionalidades ao core. A resposta é não.

Use o sistema de extensões.
**Todo o trabalho pode ser feito inteiramente no chat do Claude Desktop.** Você não precisa sair da sua mesa.

### Passo 1: Decidir o que construir no chat

Não diga apenas "construa isso" do nada.

Primeiro organize o que você quer no chat do Claude Desktop.
"Quero este tipo de funcionalidade", "Quero automatizar este tipo de operação" — verbalize através da conversa com a IA.

Quando estiver claro sobre o que construir, diga isto:

```
Crie um documento de especificação.
```

A IA criará a spec.

### Passo 2: Deixá-la construir

Você não precisa se mover para uma bancada. Continue no mesmo chat:

```
A spec está pronta. Implemente-a como uma Extensão.
Crie o scaffold com create_extension, escreva o código com write_extension_file.
Verifique se não há problemas com validate_extension.
```

A IA criará e editará arquivos de Extensão diretamente pelo MCP.
Na sua mesa, tudo é feito apenas pelo chat.

**Mas se prosseguir é sua decisão.**

Tome as sugestões da IA como referência. Mas você não é obrigado a segui-las.
Você é quem tem o propósito, não a IA.
Não delegue seu julgamento.

Quando concordar, deixe-a implementar. Se algo parecer errado, diga. Repita até funcionar.

Quando a Extensão estiver completa, reinicie o YU AI Manager.
Uma nova Extensão aparecerá em Configurações → Extensões. Verifique as permissões, aprove-a, e ela roda.

### Passo 3: Compartilhar (Opcional)

Se você construiu algo útil, pode compartilhar.
Se outros vão usá-lo é decisão deles. Nós fizemos, você decide.

---

## Reportar bugs

### Passo 1: Obter os logs

Abra o YU AI Manager e vá para **Configurações → Logs**.
Copie os logs ao redor do momento em que o problema ocorreu.

Se não encontrar os logs, descreva o seguinte com precisão:
- O que você fez
- O que esperava que acontecesse
- O que realmente aconteceu

"Algo está errado" não é uma descrição.

### Passo 2: Tirar um screenshot ou vídeo

Se o problema é visual e as palavras não conseguem descrevê-lo:

- **Screenshot**: `Windows + Shift + S`
- **Gravação de tela**: `Windows + Shift + R`

No Mac: Screenshot é `Cmd + Shift + 4`, gravação é `Cmd + Shift + 5`

Você pode arrastar imagens diretamente para o chat.
Uma imagem vale muito mais do que mil palavras de explicação confusa.

**Você também pode compartilhar o que está acontecendo dentro do navegador.**

Pressione `F12` no navegador. Um painel se abrirá na borda da tela.
Você não precisa entendê-lo agora. Apenas lembre-se disso.

Quando o agente de IA disser "abra o F12 e verifique erros", é aqui.
Se você vir itens vermelhos e amarelos, selecione todos, copie e entregue ao agente como estão.
Isso é tudo que você precisa fazer.

### Passo 3: Postar no GitHub

Poste os logs e screenshots em um issue do GitHub.
O autor pode dar uma olhada. Eventualmente. Sem garantias.

Se quiser que seja corrigido agora, vá para a próxima seção.

---

## Corrigir bugs você mesmo (Recomendado)

Mais rápido do que esperar o autor. De verdade.

### Ferramentas

**Chat do Claude Desktop + MCP.** É isso.

Pensar, investigar, corrigir — tudo feito aqui.
Você pode ler e escrever arquivos de Extensão pelo MCP, e também executar verificações de código.
Nada mais necessário.

### Fluxo de depuração

Descreva o problema no chat do Claude Desktop.
Logs, screenshots, o que estava fazendo, o que esperava — jogue tudo dentro.

Com o MCP, a IA pode ler o código-fonte diretamente e verificar o estado do sistema. Diga a ela:

```
Quando clico em [X] no YU AI Manager, [Y] acontece. Deveria ser [Z].
Verifique os logs do backend e o estado pelo MCP.
Também leia o código-fonte relacionado com source_tree e source_read.
Identifique a causa e corrija.
```

A IA identificará a causa e proporá uma correção.
Aplique a correção com write_extension_file e verifique com validate_extension.
Reinicie o YU AI Manager e verifique o comportamento.

### O que dar ao agente de IA

1. **Logs de erro** — O texto bruto, não parafraseado
2. **Screenshots ou vídeo** — Para bugs visuais
3. **O que estava fazendo** — A operação quando o problema ocorreu
4. **O que esperava** — O que deveria ter acontecido
5. **Propósito** — Não apenas o sintoma, mas por que você precisa disso

### Quando a IA não entende

A IA não é humana. Ela nem sempre preencherá as lacunas que você deixou.

- Pode fazer perguntas — responda com precisão
- Pode não funcionar como esperado — diga exatamente o que é diferente
- Se continuar dando respostas fora do assunto, reformule sua solicitação
- Se perceber que faltam informações, adicione-as
- Se as palavras não chegarem, entregue os arquivos relevantes

Este é um trabalho iterativo. Funciona. Continue.

É essencialmente a mesma coisa que dar instruções a um humano. Exceto que não há ego, nem humor, nem sentimentos para se preocupar — então é muito mais simples.

---

## Limpar o que é visível primeiro

Antes de esmagar bugs invisíveis, arrume o que você pode ver.
Pulverizar inseticida em um campo coberto de ervas daninhas é inútil. Nivele o terreno primeiro.

Você implementou algo. Parece que funciona. Mas se a superfície está realmente funcionando corretamente — muitas vezes você não consegue saber clicando por conta própria. Você perde coisas. Para de notar quando se acostuma.

Use Playwright. O agente de IA operará o navegador e inspecionará a UI de canto a canto.

Diga ao agente de IA:

```
Use Playwright para operar o YU AI Manager e encontrar bugs de UI/UX,
depois avalie e sugira melhorias do ponto de vista de UX.
```

A IA operará o navegador, detectando layouts quebrados, botões mortos, fluxos não naturais, navegação confusa — e reportará. Não apenas correções de bugs, mas também sugestões da perspectiva "isso é difícil de usar" virão também.

Se aceitar é sua decisão, mas ouça todos primeiro.

Feito isso, passe para as coisas invisíveis.

---

## Matar cada bug invisível

Bugs visíveis podem ser corrigidos. O problema são os bugs invisíveis.

Pense no espaço embaixo da geladeira. Você vê uma barata de frente.
Mas mova a geladeira, e há um mundo inteiro lá embaixo.
Software é igual. Bugs que não aparecem nos logs, bugs que não podem ser reproduzidos, bugs que ninguém ativou — eles definitivamente existem. É quase impossível para um humano encontrá-los todos.

O debug MCP é o inseticida para isso.

### Como

Diga ao agente de IA:

```
Conecte-se ao MCP do YU AI Manager e faça o debug de todo o código-fonte.
Use source_tree para entender a estrutura de arquivos, depois leia os arquivos com source_read.
Reporte todos os bugs potenciais, problemas de consistência e qualquer coisa que possa causar erros.
```

A IA lê o código-fonte, verifica o estado real do sistema pelo MCP e desenterra problemas que não aparecem na superfície.
Quando o relatório chegar, mande-a corrigi-los.

### Ser persistente

Não pare em uma rodada.

Quando a IA disser "é tudo", responda com isto:

```
Há mais alguma coisa?
```

Continue repetindo isso. A IA cava um pouco mais fundo a cada vez.
Quando realmente disser "nada mais", você pode confiar que está genuinamente terminado.

Ser persistente não é uma virtude. Mas quando se trata de bugs, persistência é justiça.

---

## Fazer uma revisão de segurança antes de publicar

Se pretende publicar uma Extensão, execute uma revisão de segurança primeiro.

Não é difícil. É rápido.

Basta dizer ao agente de IA:

```
Faça uma revisão de segurança desta Extensão (ou código).
Também verifique a configuração e informações de sandbox do YU AI Manager pelo MCP.
Leia os arquivos relevantes com source_read e reporte quaisquer problemas.
```

O YU AI Manager tem uma função de verificação de código integrada para Extensões.
Ela é executada automaticamente quando uma Extensão é carregada. Reinicie o servidor e carregue a Extensão uma vez.

A verificação detecta automaticamente:
- Módulos perigosos (`subprocess`, `ctypes`, `importlib`)
- Operações diretas de BD (`sqlite3` — use SandboxedDB)
- Execução dinâmica de código (`eval`, `exec`, `__import__`)
- Acesso à rede (`requests`, `urllib`, etc.)

Problemas críticos impedirão o carregamento da Extensão. Avisos permitirão o carregamento mas serão registrados nos logs.
Verifique os logs e corrija todos os problemas.

Se está publicando código que roda no sistema de outra pessoa, assuma essa responsabilidade.

Para detalhes sobre o modelo de segurança, leia "[Extension Security Model](docs/en/help/developer/extension-security.md)."

---

## Não tocar no core

Com as Extensões, você está em um mundo protegido.
Se você mudar o que está protegendo — core e Extensões integradas — nunca esqueça que afeta tudo, e **você mesmo pode ser pego na explosão.**

Se estiver usando a versão Tauri, ou em qualquer caso, você não pode tocar no core ou Extensões integradas pelo Claude Desktop.
Não "você não deveria" — é **impossível como capacidade**.
O caminho da API não existe. Você não pode tocar o que não pode ver.

Se absolutamente precisar tocá-lo, use a versão Python. É isso.

---

## Sobre paciência

Agentes de IA são poderosos, mas não são mágicos. Alguns problemas requerem múltiplas tentativas.

Quando se sentir frustrado:
- Dê um passo atrás
- Releia o que disse a ela
- Pense sobre qual informação está faltando
- Tente de um ângulo diferente

Os problemas se resolvem. O que você precisa não é gritar, mas pensar claramente.

---

## Palavras finais

O autor construiu este software em 18 dias, dizendo à IA o que fazer.
Cada funcionalidade, cada correção, cada decisão de design nasceu de conversas.

Em outras palavras, o que está escrito apenas neste documento é suficiente para construir algo dessa escala.

Os fundamentos são todos coisas chatas.
Mas são o primeiro passo ao colocar as pedras de um dique.
Como empilhar pedras, como corrigir o ângulo — você aprende no caminho.
Problemas complexos e difíceis eventualmente também se tornarão solucionáveis.

No entanto, se os fundamentos forem negligenciados, as coisas entram em colapso mesmo em escala modesta.

Não descarte o que está escrito acima.
Para tornar o terreno sólido, o mais importante é tornar a base das suas próprias habilidades sólida como rocha.

As ferramentas estão aqui. A documentação está aqui.

**Vá em frente.**
