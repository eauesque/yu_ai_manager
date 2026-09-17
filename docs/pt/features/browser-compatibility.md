# Relatório de Compatibilidade de Navegador

**Data da pesquisa:** 2026-02-23

## Navegadores Suportados (Recomendados)

| Navegador  | Versão Mínima | Versão com Recursos Completos |
|----------|----------------|---------------------|
| Chrome   | 80+            | 94+                 |
| Firefox  | 74+            | 101+                |
| Safari   | 13.1+          | 16+                 |
| Edge     | 80+            | 94+                 |

IE11 e versões mais antigas não são suportadas.

---

## Compatibilidade de API

| Recurso | Chrome | Firefox | Safari | Edge | Notas |
|---------|--------|---------|--------|------|-------|
| Fetch API / async/await | 55+ | 52+ | 11+ | 15+ | Todos os navegadores suportados |
| AbortController | 66+ | 57+ | 11.1+ | 16+ | Todos os navegadores suportados |
| IntersectionObserver | 51+ | 55+ | 12.1+ | 16+ | Usado para rolagem infinita |
| Optional chaining `?.` | 80+ | 74+ | 13.1+ | 80+ | Usado extensivamente em todo o código |
| scroll-snap | 69+ | 68+ | 13+ | 79+ | Usado para cartões de dock |
| `scrollbar-gutter` | 94+ | 101+ | **16+** | 94+ | Não suportado no Safari 15 e anteriores |
| `inset` CSS shorthand | 102+ | 106+ | **16+** | 102+ | Não suportado no Safari 15 e anteriores |
| `backdrop-filter` | 76+ | **Não suportado** | 9+ | 79+ | Não suportado no Firefox |
| `-webkit-backdrop-filter` | ✓ | **Não suportado** | 9+ | ✓ | Sem alternativa para Firefox |

---

## Problemas Conhecidos

### 🔴 Firefox — `backdrop-filter` Não Suportado

- **Arquivos afetados:** `dock-shell-panel.css`, `search-results-modal-nav.css`
- **Sintoma:** O efeito de desfoque do painel (glassmorphism) não é renderizado, deixando o fundo transparente
- **Gravidade:** Degradação de qualidade visual (funcionalidade não é afetada)
- **Plano:** Não abordado (um fallback de fundo opaco para Firefox pode ser adicionado no futuro)

### 🟡 Safari 15 e Anteriores — `scrollbar-gutter`, `inset` Não Suportados

- **Arquivos afetados:** `dock-cards.css`, `uxpatch-i18n-paths.css`
- **Sintoma:** Tremulação de região de scrollbar e pequenos deslocamentos de cálculo de posição
- **Gravidade:** Menor (layout permanece funcional)

---

## Medidas Existentes de Compatibilidade (Boas Práticas)

- Ambos `-webkit-backdrop-filter` e o `backdrop-filter` padrão são declarados
- Scrollbars do Firefox usam `scrollbar-width` / `scrollbar-color`
- Scrollbars do WebKit usam `-webkit-scrollbar`
- APIs destrutivas (`crypto.randomUUID`, `structuredClone`, `.at()`, etc.) não são usadas

---

## Candidatos Futuros

| Item | Prioridade | Descrição |
|------|----------|-------------|
| Firefox backdrop-filter fallback | P3 | Mudar para um fundo semi-transparente sem desfoque |
| `@supports` conditional query | P3 | Detecção de recursos CSS |
