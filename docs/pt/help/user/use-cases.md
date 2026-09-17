# Coleção de Casos de Uso

Resumimos os usos representativos do YU AI Manager no formato "quando for assim, faça assim".

---

## 1. Quero organizar um monte de imagens geradas por IA

Quando se acumulam milhares de imagens geradas no NovelAI ou no Stable Diffusion em pastas e rever tudo fica difícil.

### Procedimento

1. Registre as pastas de scan na aba **Settings > Scan** (várias possíveis)
2. Após adicionar a pasta, o scan começa automaticamente. É possível escanear também dentro de ZIP/7z
3. Após concluir o scan, na página principal filtre as imagens com busca por tag (ex.: `1girl, blue_eyes`) e sort
4. Selecione as imagens preferidas e, com o botão direito > **Adicionar à coleção**, agrupe-as
5. A qualquer momento, navegue pelos grupos pela barra lateral de coleções

### Dicas

- A busca e a navegação funcionam mesmo durante o scan (a conexão somente leitura não entra em conflito)
- Ative a extension Auto Scan Watcher para detectar automaticamente novos arquivos nas pastas
- Mesmo com 1 milhão de itens, a paginação é rápida com Keyset Pagination

---

## 2. Quero encontrar imagens geradas com um prompt específico

Quando você não consegue lembrar "qual era o prompt daquela composição".

### Procedimento

1. Na barra de busca, alterne o alvo para **in_prompt**
2. Digite palavras-chave que você lembra (ex.: `cherry blossom`)
3. Use expressão regular para um filtro mais flexível (ex.: `masterpiece.*cherry`)

### Dicas

- Quando o FTS (busca full-text) está ativo, a busca é rápida mesmo com muitos prompts
- Combinar com filtros de intervalo de datas e formato de arquivo é eficaz
- Definir o sort como `random` ajuda a redescobrir imagens esquecidas

---

## 3. Quero achar imagens com composição parecida

Quando pensa "deve ter outras imagens com atmosfera parecida com esta".

### Procedimento A: busca de similaridade por pHash (composição e cores)

1. Abra a modal de detalhes da imagem
2. Clique em **Buscar imagens similares**
3. Imagens com composição próxima via pHash (hash perceptual) aparecem no painel lateral

### Procedimento B: busca semântica por CLIP (significado e conceito)

1. Clique no botão **Busca semântica** à direita da barra de busca
2. Digite uma descrição em linguagem natural (ex.: "garota em pé à beira-mar", "paisagem urbana no pôr do sol")
3. O CLIP entende o significado da imagem e exibe por ordem de similaridade

### Dicas

- A busca semântica exige configuração prévia de modelo CLIP (ONNX ou Hailo-10H)
- Em bibliotecas grandes (mais de 100k), instalar `faiss-cpu` melhora drasticamente a velocidade
- pHash acerta composição, CLIP acerta similaridade semântica. Testar os dois amplia as descobertas

---

## 4. Quero gerenciar imagens favoritas

Quando quer voltar rapidamente às obras-primas em meio a um monte de imagens.

### Procedimento

1. Marque como favorito pelo **botão coração** no card ou na modal de detalhes
2. Na modal de detalhes, defina o **rating por estrelas** (1 a 5) para avaliar a qualidade
3. Escreva notas livres em **anotações** (ex.: "candidato a retake", "já postado na SNS")
4. Filtre por "somente favoritos", "rating 4+" etc.

### Dicas

- O sort por rating (`rating_desc`) permite ver as imagens bem avaliadas de uma vez
- É possível operar favoritos e rating também pelo menu de contexto (botão direito)

---

## 5. Quero enviar o prompt de uma imagem a outra ferramenta

Quando quer reutilizar o prompt de uma imagem antiga para regerar ou criar variações em outra ferramenta.

### Procedimento

1. Abra a modal de detalhes da imagem e confira as informações de prompt
2. Clique em **Enviar para SD WebUI** / **Enviar para ComfyUI** / **Enviar para NAI**
3. A página do Bridge abre com o prompt preenchido automaticamente
4. Edite o prompt se necessário e execute na ferramenta geradora

### Dicas

- Entre SD ↔ NAI, a sintaxe de pesos `()` e `{}` é convertida automaticamente
- O botão **QP** na toolbar do Bridge insere um preset de qualidade em um clique
- A partir do Prompt Converter ou do Prompt Simulator, também é possível enviar para cada Bridge

---

## 6. Quero ver imagens dentro de arquivos ZIP/7z

Quando um conjunto de imagens baixado está empacotado em ZIP e você quer ver o conteúdo sem extrair.

### Procedimento

1. Em Settings > Scan, registre a pasta que contém os ZIP/7z
2. Ative **Scan dentro de ZIP/7z** nas opções de scan
3. Após o scan, as imagens dentro dos arquivos também aparecem na página principal como imagens normais
4. Na modal de detalhes, o nome do arquivo e o path dentro do arquivo são exibidos

### Dicas

- Vídeos dentro dos arquivos são extraídos para o cache temporário (LRU 2GB), permitindo reprodução fluida repetida
- ZIPs aninhados (ZIP-in-ZIP) também são suportados
- A função de download em lote permite reempacotar imagens dentro dos arquivos em um novo ZIP

---

## 7. Quero compartilhar imagens com a equipe ou a família

Quando quer permitir que outros dispositivos (smartphone, tablet etc.) na mesma Wi-Fi vejam as imagens.

### Procedimento

1. Na aba **Settings > Server**, ative "LAN Access"
2. Defina um **código PIN** (obrigatório ao publicar na LAN)
3. Reinicie o servidor
4. Nos outros dispositivos da LAN, acesse `http://<IP do servidor>:5000`
5. Faça login digitando o PIN

### Dicas

- Emitindo um **token de LAN Share** (path `/s/`), é possível compartilhar um link de acesso para convidado sem PIN
- Na tela do servidor aparece um QR Code; basta ler com a câmera do smartphone para acessar
- Há suporte também à autenticação Trusted Proxy via proxy reverso

---

## 8. Quero taguear automaticamente

Quando taguear à mão for cansativo e você quiser deixar a IA analisar e atribuir tags automaticamente.

### Procedimento A: WD-Tagger (rápido, especializado em tags)

1. Em **Settings**, baixe o modelo ONNX do WD-Tagger
2. Clique em **Executar WD-Tagger** na página Tools ou na modal de detalhes
3. Tags no estilo Danbooru são atribuídas automaticamente

### Procedimento B: AI Analysis (linguagem natural, alta precisão)

1. Em **Settings > AI Analysis**, adicione Ollama ou um servidor compatível com OpenAI
2. Execute a análise pela **aba AI Analysis** na modal de detalhes
3. É gerada uma descrição da imagem em linguagem natural

### Dicas

- O WD-Tagger também suporta modo combinado com engine VLM (compatível com OpenAI API)
- Pós-processamentos como filtro NSFW e normalização de tags são aplicados automaticamente
- Há suporte à escrita de tags em metadados XMP, facilitando integração com outras ferramentas

---

## 9. Quero ver estatísticas e relatórios

Quando quer entender as tendências e o crescimento da sua biblioteca de imagens.

### Procedimento

1. Abra a página **Stats** no menu de navegação e confira as estatísticas gerais
2. Na página **Monthly Report**, veja relatórios detalhados por mês
   - Número de arquivos do mês vs. mês anterior, TOP 20 tags, novas tags, distribuição por source, contagem por dia
3. Na seção **Trophies**, confira os troféus de conquistas

### Dicas

- Os troféus se desbloqueiam de forma escalonada em 6 categorias (milestone / streak / diversity / source / hidden) e 4 tiers (bronze a platinum)
- Configurar corretamente o fuso horário (Settings > Appearance) deixa as estatísticas diárias precisas

---

## 10. Quero integrar com agentes de IA via MCP

Quando quer operar a biblioteca de imagens a partir do Claude Desktop ou de outras ferramentas de IA compatíveis com MCP.

### Procedimento

1. Nas configurações do cliente MCP (Claude Desktop etc.), registre o servidor MCP do YU AI Manager
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. Instrua a IA em linguagem natural: "busque imagens", "adicione aos favoritos" etc.
3. Mais de 60 ferramentas disponíveis, como `search_images`, `add_favorite`, `trigger_scan`

### Dicas

- Pela extension do cliente MCP, é possível conectar também a servidores MCP externos (stdio / SSE / Streamable HTTP)
- Configurando autenticação por API Key, é possível chamar as REST APIs diretamente de ferramentas externas, sem cabeçalho CSRF
- Usando a extension Hailo GenAI, também é possível integrar via endpoint compatível com OpenAI SDK

---

## 11. Quero usar o Hailo-10H como servidor compatível com OpenAI

Quando você tem o NPU Hailo-10H e quer usá-lo como servidor de IA local compatível com o OpenAI SDK. Ferramentas externas como Open WebUI, Continue.dev ou scripts próprios podem usar LLM / VLM / reconhecimento de voz / embeddings CLIP do Hailo como se fossem OpenAI.

### Endpoints suportados

| Endpoint | Funcionalidade | API OpenAI correspondente |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | Lista de modelos já baixados | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | Geração de texto e compreensão de imagem (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | Transcrição de áudio | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | Conversão de texto em vetor (CLIP) | Embeddings |

### Procedimento

1. Em **Extensions > GenAI**, confirme que a extension Hailo GenAI está ativada
2. Baixe o modelo desejado (LLM: `qwen2.5-1.5b-chat` etc., VLM: `llava-v1.6-vicuna-7b` etc.)
3. Nas configurações de conexão da ferramenta externa, defina a **Base URL** como:
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   (ajuste a porta conforme a configuração do YU AI Manager)
4. API Key não é necessária (por ser acesso local). Se a ferramenta exigir, informe um valor dummy (ex.: `dummy`)

### Exemplos de conexão com ferramentas externas

#### Open WebUI

Adicione em Settings > Connections > OpenAI API:
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev (assistente de IA do VS Code)

Adicione em `~/.continue/config.json`:
```json
{
  "models": [{
    "title": "Hailo Qwen2.5",
    "provider": "openai",
    "model": "qwen2.5-1.5b-chat",
    "apiBase": "http://localhost:5000/ext/hailo-genai/v1",
    "apiKey": "dummy"
  }]
}
```

#### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# Text generation
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# Image understanding (VLM) — attach image as base64
import base64
with open("image.png", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

res = client.chat.completions.create(
    model="llava-v1.6-vicuna-7b",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image."},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ],
    }],
)

# Audio transcription
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# Text embedding (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### Parâmetros suportados

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input` (string ou array de strings)
- **Aliases de modelo**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### Observações

- **Exclusividade do dispositivo**: o Hailo-10H consegue carregar apenas 1 modelo GenAI por vez (LLM ou VLM ou S2T). A troca de modo é feita na página GenAI
- **Restrição de URL de imagem**: por segurança, URLs `http://` para imagens são bloqueadas. Use o formato `data:image/...;base64,...` ou o formato `file_id:` do YU AI Manager
- **Embedding CLIP**: apenas conversão texto → vetor. Imagem → vetor está disponível via endpoint `/api/semantic/`
- **Formatos de áudio**: formatos diferentes de WAV (MP3, M4A, OGG etc.) exigem ffmpeg
- **Campo `usage`**: a contagem de tokens sempre retorna 0 (restrição do NPU Hailo)
