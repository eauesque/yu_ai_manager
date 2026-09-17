# Comece em 5 Minutos com YU AI Manager

## O que é YU AI Manager

YU AI Manager é um aplicativo de interface web para gerenciar centralmente metadados de imagens geradas por IA (Stable Diffusion / NovelAI / ComfyUI, etc.). Ele extrai automaticamente prompts e informações de modelo incorporadas nas imagens, tornando a busca por tags, visualização e organização eficientes.

---

## Ambiente Operacional

| Item | Requisito |
|------|-----------|
| Python | 3.11 ou superior |
| Node.js | 18 ou superior (para build de frontend) |
| SO | Windows 10/11, macOS, Linux |
| Navegador | Chrome / Firefox / Edge (versão mais recente recomendada) |

---

## Passos de Instalação

### 1. Clone o Repositório

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. Crie um Ambiente Virtual Python

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash):**

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3. Instale as Dependências Python

```bash
uv pip install -r requirements.txt
```

> Se `uv` não estiver instalado, instale-o primeiro com `pip install uv`.

### 4. Build do Frontend

```bash
pnpm install
pnpm run build
```

> Se `pnpm` não estiver instalado, instale-o primeiro com `npm install -g pnpm`.

Pronto! A instalação está completa.

---

## Inicialização Inicial

### 1. Inicie o Servidor

```bash
# Se venv não estiver ativado, ative-o primeiro
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. Acesse no Navegador

Após iniciar, abra a seguinte URL no seu navegador:

```
http://localhost:5000
```

*(Captura de tela da tela principal)*

---

## Primeira Coisa a Fazer

### Passo 1: Registre Pasta de Imagem para Verificação

Registre a pasta onde suas imagens geradas por IA estão salvas para ler metadados.

1. Clique no menu hambúrguer no canto superior direito da tela para abrir **Settings**
2. Selecione a aba **Scan**
3. Adicione o caminho da pasta a ser verificada
4. A verificação inicia automaticamente após adicionar a pasta

*(Captura de tela da tela de registro de pasta de verificação)*

Durante a verificação, uma barra de progresso aparece no topo da tela. Se houver muitas imagens, pode levar alguns minutos, mas você pode pesquisar e visualizar durante a verificação.

### Passo 2: Veja Imagens na Grade de Miniaturas

Após a verificação ser concluída, a grade de miniaturas aparece na página principal.

*(Captura de tela da exibição da grade de miniaturas)*

- **Rolagem**: Rolagem virtual permite exibir muitas imagens sem problemas
- **Ordenação**: Use o menu de ordenação no topo para alternar entre ordem de data, classificação, etc.
- **Clique com botão direito**: Acesse menu de contexto para registrar favoritos ou adicionar a coleção

### Passo 3: Refine Imagens com Busca de Tags

Digite tags separadas por vírgula na barra de busca para exibir apenas imagens correspondentes.

```
1girl, blue_eyes, school_uniform
```

*(Captura de tela da tela de busca de tags)*

- **Autocompletar**: Sugestões de tags aparecem enquanto você digita
- **Filtros**: Refine por intervalo de data, formato de arquivo, classificação em estrelas, etc.
- **Busca em Prompt**: Você também pode fazer busca de texto completo em prompts

### Passo 4: Confirme Informações da Imagem no Modal de Detalhe

Clique em uma miniatura para abrir o modal de detalhe.

*(Captura de tela do modal de detalhe)*

- **Aba Info**: Veja prompt, prompt negativo, nome do modelo, parâmetros de geração, etc.
- **Aba AI Analysis**: Exiba resultados de tag automático por WD-Tagger (se configurado)
- **Classificação em Estrelas**: Atribua classificação de 1-5 estrelas à imagem
- **Favorito**: Registre como favorito com ícone de coração
- **Editar Tags**: Adicione/remova tags de usuário
- **Operação de Teclado**: Mude para imagem anterior/próxima com setas

---

## Resumo de Operações Comuns

| Quero Fazer | Operação |
|-------------|----------|
| Encontrar imagem | Digite tags na barra de busca |
| Ver detalhes da imagem | Clique em miniatura |
| Adicionar a favoritos | Ícone de coração no modal de detalhe, ou menu de clique direito |
| Atribuir classificação | Ícone de estrela no modal de detalhe |
| Adicionar imagem a coleção | Menu de clique direito > Adicionar a coleção |
| Selecionar múltiplas imagens | Ctrl+clique (ou Shift+clique) para seleção de intervalo |
| Verificar nova pasta | Settings > Aba Scan |

---

## Próximos Passos

Quando se familiarizar com operações básicas, experimente os seguintes recursos também.

### Configurações

Na página Settings, você pode personalizar aparência, configurar fuso horário, configurar acesso LAN, etc.
Consulte [Guia de Configurações](settings.md) para detalhes.

### Bridge (Integração com Ferramenta de Geração)

Integre-se com SD WebUI / ComfyUI / NovelAI API para enviar/receber prompts.
Consulte [Guia de Bridge](bridges.md) para detalhes.

### Extensões

Muitos recursos de extensão estão disponíveis, como WD-Tagger (tag automático), biblioteca de prompts, visualizador de log de chat, etc. Você pode gerenciá-los na aba Extensions em Settings.

### Busca Semântica

Quando CLIP é configurado, você pode fazer busca de imagem em linguagem natural, como "uma menina olhando para o pôr do sol à beira-mar".
Consulte [Guia de Busca](search.md) para detalhes.

### Servidor MCP

Você pode operar YU AI Manager a partir de agentes de IA como Claude Desktop. Conecte via transporte stdio.

---

## Solução de Problemas

Se encontrar problemas, consulte [Guia de Solução de Problemas](troubleshooting.md).

Problemas comuns:

- **Comando `uv` não encontrado**: Instale com `pip install uv`
- **Comando `pnpm` não encontrado**: Instale com `npm install -g pnpm`
- **Porta 5000 em uso**: Especifique porta diferente com `python web_ui.py --port 5100`
- **Imagens não exibidas**: Verifique se o caminho da pasta de verificação está correto e se os arquivos de imagem existem

