# Barra de ferramentas modal

A barra de ferramentas unificada na parte inferior da modal de detalhes fornece acesso a todos os controles principais durante a visualização de imagens/vídeos.

## Estrutura

### Barra primária (sempre visível)

**Modo de imagem fixa:**
- ☆ Favorito
- ⓘ Alternar painel de informações
- ‹ › Anterior / Próximo
- Zoom (− / 100% / +)
- Modo de ajuste (fit / fit-w / fit-h / fit-custom + altura / original)
- Spread 2P / direção ↔ (quando aplicável)
- ⛶ Imersivo / ⤢ Tela cheia
- 📁 Coleção
- Bridge Enviar (Enviar prompt ▾ / Enviar imagem ▾)

**Modo vídeo/áudio (layout de 2 níveis):**
- Superior: exibição de tempo + barra de pesquisa (largura máx 720px)
- Inferior: ☆ Fav / ⓘ Info / ‹ › / ▶ Reproduzir ⏪ ⏩ / ♪ Mudo + volume / ⛶ ⤢ / 📁

### Menu de estouro (botão …)

Consolida operações pouco frequentes em uma lista vertical:
- Reprodução automática + intervalo
- Repetir / velocidade / retomar (para vídeo)
- FPB / grade de caracteres (para imagens fixas)
- ZIP / visualização de contêiner
- Guia de teclado ?
- Recolher barra de ferramentas «

## Atalhos de teclado

| Tecla | Ação |
|---|---|
| `T` | Alternar visibilidade da barra de ferramentas |
| `V` | Modo imersivo |
| `F` | Tela cheia |
| `I` | Painel de informações |
| `H` | Guia de teclado |
| `P` | Reprodução automática |
| `Space` / `K` | Reproduzir / pausar (vídeo) |
| `J` / `0` | Retroceder (vídeo) |
| `L` | Avançar rápido (vídeo) |
| `M` | Mudo (vídeo) |
| `R` | Repetir (vídeo) |
| `←` / `→` | Imagem anterior / próxima |
| `ESC` | Fechar menu de estouro → modal em ordem |

## Recolher e restaurar

Métodos para recolher a barra de ferramentas:
- No menu de estouro (…), selecione "Recolher barra de ferramentas"
- Pressione a tecla `T`

Métodos para restaurar:
- Clique na alça de borda no centro inferior da tela
- Pressione a tecla `T` novamente

A posição da alça de borda se ajusta automaticamente com base na presença de tira de filme durante o estado recolhido.

## Acessibilidade

- Toda a barra de ferramentas tem `role="toolbar"`
- O botão de estouro usa `aria-haspopup="menu"` / `aria-expanded` atualizado dinamicamente
- Os itens do menu de estouro têm `role="menuitem"`
- A alça de borda é um `<button>` padrão operável com Enter / Espaço
- Para satisfazer WCAG 2.5.5 (Tamanho de destino), a alça visualmente 8px tem uma área de impacto invisível de 24px de altura estendida via `::before`
