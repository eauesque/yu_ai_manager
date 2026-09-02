# Começando

YU AI Manager é um aplicativo de interface web para gerenciar metadados de imagens geradas por IA.

## Instalação

### Ambiente Necessário

- Python 3.11 ou superior
- Node.js 18 ou superior (para build de frontend)

### Passos de Configuração

```bash
# Clone o repositório
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# Instale uv (apenas primeira vez)
pip install uv

# Crie ambiente virtual Python e instale dependências
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# Build do frontend
pnpm install
pnpm run build

# Opcional: Acelerar busca semântica (para grandes bibliotecas)
uv pip install faiss-cpu
```

## Como Iniciar

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

Acesse `http://localhost:5000` no seu navegador.

## Configuração Inicial

1. **Registrar Pasta de Verificação**: Settings > Aba Scan — Adicione a pasta onde suas imagens geradas por IA estão salvas
2. **Executar Verificação**: A verificação inicia automaticamente após adicionar a pasta
3. **Visualizar Imagens**: Você pode pesquisar e visualizar imagens na página principal

## Acesso LAN

Para acessar de outros dispositivos:

1. Em **Settings > Aba Server**, configure "LAN Access" como ON
2. Configure autenticação PIN (obrigatória para acesso LAN)
   Digite um número (4-8 dígitos) no campo "Código de Autenticação PIN" em **Settings > Aba Server**
3. Reinicie o servidor

Você pode acessar de outros dispositivos na LAN através de `http://<IP-do-servidor>:5000`.

