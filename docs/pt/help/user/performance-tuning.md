# Guia de Ajuste de Desempenho

Guia de tuning para usar o YU AI Manager com conforto em ambientes que gerenciam mais de 100.000 arquivos.
Mesmo com a configuração padrão, muitas otimizações operam automaticamente, mas é possível melhorar ainda mais ajustando-as ao seu ambiente.

---

## 1. Hardware recomendado

| Item | Mínimo | Recomendado (100k+ arquivos) |
|------|---------|------------------------|
| CPU | 2 núcleos | 4 núcleos ou mais (geração de miniaturas é paralelizada) |
| RAM | 4 GB | 8 GB ou mais |
| Armazenamento | HDD | **SSD fortemente recomendado** — impacta diretamente o tempo de resposta do banco |
| Rede | — | Para uso via LAN, 1 Gbps ou mais |

**Especialmente importante**: coloque o arquivo do banco (`data/tags.db`) sempre em SSD.
As imagens em si podem ficar em HDD sem problemas, mas se o DB estiver em HDD, a busca e a navegação ficam notavelmente lentas.

---

## 2. Otimização do scan inicial

### Divisão de scan roots

Escanear muitos arquivos de uma só vez leva tempo.
Recomenda-se registrar múltiplas scan roots em Settings > Scan Roots e executar o scan em etapas.

- Primeiro escaneie as pastas mais usadas
- Adicione as demais pastas à fila de scan (são processadas automaticamente em ordem)
- Pastas duplicadas são detectadas e puladas automaticamente

### Navegação possível durante o scan

Durante o scan, busca e exibição de miniaturas continuam funcionando normalmente.
Internamente usamos conexões de banco somente leitura, então a escrita do scan não bloqueia a navegação.

### Otimização automática após o scan

Ao concluir o scan, as estatísticas do banco são atualizadas automaticamente (ANALYZE).
Isso otimiza o plano de execução das queries, acelerando buscas subsequentes.
Nenhuma ação especial é necessária.

---

## 3. Melhoria da velocidade de navegação

### Cache do Service Worker

O Service Worker do navegador faz cache automático dos seguintes conteúdos:

| Tipo | Limite de cache | Efeito |
|------|-------------|------|
| Miniaturas | 5.000 itens | Exibição instantânea da grade a partir da segunda vez |
| Preview (1200px) | 200 itens | Aceleração da exibição em modal |
| Imagens originais | 50 itens | Re-exibição instantânea de imagens vistas recentemente |

O Service Worker é gerenciado pelo navegador, sem necessidade de configuração.
Para limpar o cache, use as ferramentas de desenvolvedor > Application > Storage.

### Ativação do scroll virtual

Ao exibir milhares de resultados de busca, ativar o scroll virtual melhora significativamente o desempenho de renderização.

**Como ativar**: Settings > Appearance > "Virtual Scroll" ON

O scroll virtual renderiza no DOM apenas os cards visíveis, reduzindo bastante o uso de memória e a carga de renderização.
Em bibliotecas na escala de dezenas de milhares, é fortemente recomendado ativar.

### Miniaturas WebP

As miniaturas são geradas em formato WebP (30-40% menores que JPEG).
Isso reduz o tráfego, com efeito especialmente notável em acessos via LAN.
Aplicado automaticamente, sem necessidade de configuração.

---

## 4. Desempenho de busca

### Efeito dos índices

O banco cria automaticamente índices otimizados para os padrões de busca principais.
Ordenação por data, filtros por tag, busca por path etc. rodam de forma rápida.

**Estimativas**:
- Busca sem filtros: resposta em até 50ms mesmo na escala de 280k
- Busca com filtro de tag: até 100ms
- Busca por path (FTS5): até 50ms

### Busca full-text FTS5 vs busca com LIKE

A busca por path usa automaticamente índice FTS5 (Full-Text Search).
É de 20 a 100 vezes mais rápido que a busca LIKE tradicional (`%keyword%`).

Quando FTS5 não está disponível (ex.: upgrade a partir de um DB antigo), o sistema cai automaticamente para busca LIKE.
Basta executar o scan uma vez para que o índice FTS5 seja construído.

**Nota sobre busca em japonês**: buscas contendo kanji, hiragana ou katakana podem, internamente, usar o fallback para LIKE.
Isso acontece por limitações do tokenizador FTS5 do SQLite e é comportamento normal.

---

## 5. Otimização da reprodução de vídeo

### Cache de faststart

Para acelerar a reprodução de arquivos MP4/MOV, o processamento faststart é aplicado automaticamente.
Vídeos com faststart iniciam streaming instantaneamente.

| Item | Valor |
|------|-----|
| Local do cache | `cache/faststart/` |
| Limite total | 4 GB (gerenciado automaticamente por LRU) |
| Limite por arquivo | 500 MB |
| Alvos | MP4, MOV (WebM é pulado por não ser necessário) |

**Ganho perceptivo aproximado**:

| Tamanho do arquivo | Sem faststart | Com faststart |
|--------------|---------------|---------------|
| 5-50 MB | 2-10 s de espera | Inicia em cerca de 200ms |
| 50-200 MB | 10-60 s de espera | Inicia em cerca de 500ms |
| 200-500 MB | Vários minutos de espera | Inicia em cerca de 1 segundo |

### Verificação do FFmpeg

O processamento faststart requer FFmpeg. Sem ele, os vídeos só são reproduzidos após download completo.

```bash
ffmpeg -version
```

Se o FFmpeg não for encontrado no PATH, instale-o pelo [site oficial](https://ffmpeg.org/download.html).

---

## 6. Gestão de uso de memória

### mmap do SQLite

Em bancos grandes (mais de 100k arquivos), o mmap do SQLite (I/O mapeada em memória) é configurado automaticamente em 1 GB.
Isso faz com que queries de leitura aproveitem o page cache do SO e fiquem mais rápidas.

**Ambientes com RAM de 4 GB ou menos**: o mmap pode pressionar a memória.
Nesse caso, monitore a memória livre do sistema e feche outros aplicativos se houver muito swap.

### Gestão das abas do navegador

O YU AI Manager se comunica em tempo real com cada aba via SSE (Server-Sent Events).

- Até 10 conexões SSE simultâneas por IP
- Fechar abas desnecessárias libera recursos de conexão
- Muitas abas abertas também aumentam o uso de memória do navegador

**Recomendado**: mantenha entre 3 e 4 abas abertas ao mesmo tempo.

---

## 7. Troubleshooting — checklist quando parecer "lento"

### Verificações básicas

- [ ] **Está usando SSD?**: com `data/tags.db` em HDD, todas as operações ficam lentas
- [ ] **FFmpeg instalado?**: essencial para acelerar a reprodução de vídeo
- [ ] **Número de abas do navegador**: confirme se não tem mais de 5 abertas

### Navegação lenta

- [ ] **Ativar scroll virtual**: Settings > Appearance > Virtual Scroll
- [ ] **Não limpar o cache do navegador**: o cache do Service Worker está atuando
- [ ] **Está durante um scan?**: durante o scan o uso é normal, mas a primeira geração de miniaturas leva tempo

### Busca lenta

- [ ] **Concluir o scan**: ao concluir o scan, o ANALYZE roda e otimiza a busca
- [ ] **Resultados maiores que 100k**: adicione filtros (tag, data, path etc.) para reduzir

### Reprodução de vídeo lenta

- [ ] **Conferir existência de FFmpeg**: verifique com `ffmpeg -version`
- [ ] **Capacidade do cache faststart**: veja se `cache/faststart/` não ultrapassa 4 GB (autogerenciado, mas pode ser checado)
- [ ] **Tamanho do arquivo**: vídeos acima de 500 MB ficam fora do cache faststart. São reproduzidos por Range, mas o primeiro início é um pouco mais lento

### Servidor todo pesado

- [ ] **Número de acessos simultâneos**: confira se não há mais de 10 conexões SSE por IP
- [ ] **Durante upload?**: confira se não está enviando um arquivo próximo ao limite de 100 MB de upload
- [ ] **Aba Settings > Logs**: verifique erros e avisos nos logs do servidor

---

## 8. Referência de indicadores de desempenho

Estimativas de tempo de resposta em um ambiente adequadamente otimizado.

| Operação | Escala de 280k | Escala de 100k |
|------|-----------------|-----------------|
| Exibição de grade (inicial) | 200-500ms | 100-300ms |
| Exibição de grade (com cache) | Até 50ms | Até 50ms |
| Busca por tag | Até 100ms | Até 50ms |
| Busca por path (FTS5) | Até 50ms | Até 30ms |
| Miniatura (cache hit) | Até 5ms | Até 5ms |
| Início da reprodução de vídeo (com faststart) | 200ms | 200ms |

Se estiver muito acima desses valores, revise o checklist acima.

---

## Modo rápido (servidor Rust)

Em ambientes compatíveis, a inicialização passa automaticamente para o servidor Rust (`yu-server`).

Em Configurações -> "Servidor" -> "Modo rápido" escolhe-se **como obtê-lo**:

- **Baixar o binário publicado** (padrão) -- nunca compila
- **Compilar nesta máquina** -- nunca baixa
- **Baixar e, se falhar, compilar**

Compilar precisa de 8 GB livres em disco e usa muita CPU e memória. **Em máquinas com pouca memória (um Raspberry Pi, por exemplo) pode esgotar a swap e derrubar todo o sistema.** Todos os recursos continuam utilizáveis durante a compilação. Compilar no Windows exige ainda as ferramentas de compilação do Visual Studio (o linker).

O progresso aparece na mesma tela: tempo decorrido, a última linha do cargo, sucesso ou falha, e se a compilação parou no meio. O log bruto fica em `bin/fast-mode-build.log`.

Quando o modo rápido é recusado por causa do estado desta cópia (um pacote web desatualizado, uma extensão fora da lista incluída), obter um binário não muda a resposta: não há download nem compilação. Esse motivo também é mostrado ali.
