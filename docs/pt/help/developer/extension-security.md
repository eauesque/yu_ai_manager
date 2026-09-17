# Modelo de Segurança de Extensions

Este software tem como característica que "qualquer pessoa pode criar Extensions usando IA".
Ao mesmo tempo, vêm embutidos mecanismos que protegem seu sistema contra Extensions maliciosas.

Esta página explica esses mecanismos.
Foi escrita de forma compreensível mesmo para quem não é técnico.

---

## Ideia básica

As Extensions rodam dentro de um **mundo protegido**.

Dentro desse mundo protegido, as Extensions podem se comportar com relativa liberdade.
Adicionar páginas, exibir dados, processar imagens — esse é o trabalho delas.

Contudo, o que está **fora** desse mundo protegido — o núcleo do sistema (core), outras Extensions, todos os arquivos do seu PC — fica inacessível.
Isso não é "proibido por regra": a estrutura é tal que **fisicamente não dá para alcançar**.

---

## Como as permissões funcionam

Para que uma Extension faça algo, ela precisa de **permissão**.

As permissões foram projetadas seguindo o mesmo modelo das permissões de apps de smartphone.

- É natural que um app de câmera peça acesso à câmera
- É estranho que um app de câmera peça acesso aos contatos

O mesmo vale para as Extensions. Se uma Extension que coloca marca d'água em imagens pedir acesso à rede, você deve desconfiar.

### Fluxo de aprovação

1. Instale a Extension (ou peça para a IA criar uma)
2. O YU AI Manager faz uma varredura automática no código e examina o que ela tenta fazer
3. É exibida uma lista das permissões que a Extension está solicitando
4. **A Extension não roda até que você aprove**

Leia com atenção as informações mostradas na tela de aprovação.
Preste atenção especial às permissões exibidas em vermelho.

### Após aprovar as permissões

A Extension opera dentro do escopo das permissões aprovadas.
As permissões não aprovadas não podem ser usadas, por mais que a Extension tente.
Não é que "ela tente usar e seja negada" — para ela, "elas nem existem".

---

## Três monitoramentos independentes

Sua Extension é monitorada por três mecanismos independentes.
Esses três são mutuamente independentes; se um for enganado, os outros dois continuam funcionando.

### 1. Varredura de código

Analisa automaticamente o código da Extension e detecta padrões perigosos.
Execução de programas externos, operações diretas de banco de dados, execução dinâmica de código — tudo isso é detectado imediatamente.

### 2. Controle de permissões

Quando a Extension chama uma API, o sistema verifica se ela possui uma "autorização" válida.
A autorização só é emitida quando você aprova uma permissão.
A própria Extension não consegue forjar a autorização.

### 3. Registro de auditoria

Todas as operações da Extension são registradas.
Esse registro é armazenado em um local independente que a própria Extension não pode alterar.

Se uma anomalia for detectada — por exemplo, tentativa de executar uma ação não declarada — uma notificação é enviada automaticamente e, se necessário, a autorização da Extension é invalidada.

---

## Ao criar Extensions com IA

Quando você cria uma Extension pelo Claude Desktop, a Extension criada é automaticamente registrada no **nível mais restritivo**.

É como não entregar logo a chave do cofre a um funcionário recém-contratado.
Primeiro ela opera com permissões limitadas; depois que você confirma que não há problemas, adiciona as permissões necessárias.

### O que pode ser feito com Extensions criadas por IA

**Sem necessidade de aprovação:**
- Ler e exibir dados
- Adicionar páginas à UI
- Adicionar telas de configuração

**Requer aprovação:**
- Comunicação com serviços externos
- Escrita no banco de dados
- Leitura de arquivos

**Impossível, não importa o que se faça:**
- Ler ou alterar o núcleo do sistema (core)
- Ler ou alterar outras Extensions
- Executar programas externos
- Forjar autorizações

---

## Inspeção periódica

Uma Extension não fica aprovada para sempre.

Se o código for alterado e a quantidade de mudanças ultrapassar um limite, será exigida uma **reaprovação**.
Isso previne o truque de ir fazendo alterações pequenas até que, quando se percebe, a Extension virou algo completamente diferente.

Além disso, uma reinspeção do código é executada automaticamente de tempos em tempos.
Mesmo que não houvesse problema no momento da aprovação, novas regras de inspeção podem revelar problemas.

---

## O que você deve fazer

1. **Leia direito a tela de aprovação de permissões** — aprove depois de entender o que está sendo pedido
2. **Rejeite pedidos de permissão estranhos** — é esquisito um processador de imagens precisar de rede
3. **Não ignore as notificações** — se uma anomalia for detectada, verifique-a
4. **Não instale Extensions de origem não confiável** — é óbvio

Dito inversamente: se você só fizer isso, está seguro.
O resto os mecanismos cuidam.
