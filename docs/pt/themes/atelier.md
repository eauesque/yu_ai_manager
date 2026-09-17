# Sistema Atelier (γ)

**Atelier System** é a identidade visual introduzida ao yu_ai_manager — uma linguagem de design híbrida Editorial × Refined × Brutalist.

## Hierarquia de marca

**eauesque** (marca do produto) > **yu_ai_manager** (app) > **Atelier System** (nome do sistema de design)

Atelier System está no mesmo nível que Material / Fluent, organizado sob a marca de produto eauesque.

## Modelo de adoção: tema aditivo opt-in

Os temas existentes (light / dark / theme-retro / theme-glow) permanecem inalterados. Atelier é aplicado **adicionando** `body.theme-atelier-light` ou `body.theme-atelier-dark` — nenhuma substituição destrutiva.

- **Novos usuários**: padrão para Atelier light / dark (segue `prefers-color-scheme` do sistema)
- **Usuários retornando**: configurações preservadas; você pode voltar para legacy a qualquer momento

Alternar via Configurações → Diversos → "Atelier Theme".

## Híbrido de três fontes

| Função | Fonte | Notas |
|---|---|---|
| Display + body | **Fraunces** Variable | eixos opsz/wght impulsionam h1=96 / h2=48 / h3=24 / body=14 / eyebrow=11 com correspondência de tamanho óptico |
| UI sans | **Inter** Variable | Navegação, botões, rótulos, eyebrow |
| Data mono | **JetBrains Mono** Variable | Sintaxe de prompt (pesos, LoRA, embeds), valores de metadados |

Todos auto-hospedados (subconjunto Latin Extended). Fraunces 176K / Inter 148K / JetBrains Mono 52K. Licença SIL Open Font v1.1.

Regenerar via `scripts/build_atelier_fonts.py`.

## Acentos de dois níveis

| Token | Propósito | Light / Dark |
|---|---|---|
| `--accent-warm` | Decorativo, atmosfera, favoritos | `#c9a063` / `#d4a96e` |
| `--accent-tool` | Ação, contorno de foco, estado ativo | `#2f5c8a` / `#5a8fc5` |

Separar decoração de ação torna as affordances da UI inequívocas à primeira vista.

## --canvas (cinza neutro da área de imagem)

Regiões de imagem de IA (área de imagem modal, grade de miniaturas) vivem em uma **tela cinza neutra**, separada do chrome de UI quente para que a percepção de cor da imagem não seja enviesada:

- `--canvas`: `#d4d4d2` (light) / `#1a1a1a` (dark)
- `--canvas-raised`: `#c8c8c6` (light) / `#222222` (dark)

Chrome (`--bg`, `--surface`, `--surface-raised`) mantém a família quente-bege.

## Verificação de contraste WCAG

8 pares × light/dark = 16 casos, afirmados por `tests/test_atelier_wcag.py`. Texto de corpo 4.5:1, incidental (contorno de foco / eyebrow) 3:1.

```
uv run pytest tests/test_atelier_wcag.py
```

## Modal

- Área de imagem: `--canvas`
- Painel de informações: `--surface-raised` + Fraunces roman (sem itálico)
- Corpo de prompt: Fraunces roman; `(...:1.2)` e `<lora:...>` mudam para JetBrains Mono inline
- Barra de ferramentas (v4.126.2 pílulas circulares): glass + accent-tool ativo
- Fechar / seta de navegação / botão fav: glass + contorno de foco accent-tool
- Favorito ativo: acento quente (decorativo, mantido separado do azul da ferramenta)

## Logo do cabeçalho

Construção de duas linhas:
- Linha 1: `yu` (Fraunces 22pt)
- Linha 2: `eauesque` (assinatura JetBrains Mono 9pt)

Uma assinatura editorial que visualiza a hierarquia de marca. O nav-brand legacy permanece no lugar para temas não-atelier.

## Arquivos

```
ui/default/static/css/atelier/
  atelier-tokens.css       # @font-face + body.theme-atelier-* + tokens
  atelier-components.css   # h1-h3, p, eyebrow, glass btn, prompt-syntax
  atelier-index.css        # logo + sidebar + grid + pill search
  atelier-modal.css        # full modal (canvas + glass + accent-tool)

ui/default/static/fonts/atelier/
  Fraunces-VariableFont.subset.woff2     # 176K
  Inter-VariableFont.subset.woff2        # 148K
  JetBrainsMono-VariableFont.subset.woff2 # 52K
  LICENSE.md                              # OFL v1.1
```

## Acessibilidade

- `prefers-reduced-motion: reduce` cancela transform/animation (transições de opacidade mantidas)
- `:focus-visible` em todos os lugares usa `--accent-tool` contorno 2px + deslocamento 2px (WCAG 2.5.5 + 1.4.11)
- WCAG AA (4.5:1 corpo, 3:1 incidental) verificado em 16 pares

## Caminho de reversão

Se algo der errado, Configurações → "Atelier Theme" → "Off" restaura instantaneamente light/dark legacy. Temas personalizados (preset-*) não são afetados.
