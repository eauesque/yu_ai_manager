# Solução de Problemas

Soluções para problemas comuns.

## Erro de Inicialização

**"Module not found"**
```bash
uv pip install -r requirements.txt
```

**"Port already in use"**
```bash
python web_ui.py --port 5100
```

## Problema de Verificação

**"No images found"**
- Verificar caminho da pasta
- Confirmar arquivos de imagem existem
- Usar .jpg / .png / .webp

**"Metadata not extracted"**
- Imagens geradas por IA devem ter metadados
- Usar PNG com metadados incorporados

## Problema de Busca

**"Search is slow"**
- Executar VACUUM: Settings > Debug > Vacuum Database
- Aumentar DB pool size em config.json
- Usar SSD em vez de HDD

**"Suggestions not appearing"**
- Reconstruir índices: Settings > Debug > Rebuild Indices
- Limpar cache: Settings > Debug > Clear Cache

## Problema de Bridge

**"Bridge not connecting"**
- Verificar URL do server (ex. http://127.0.0.1:7860)
- Confirmar firewall permite conexão
- Reiniciar bridge

**"Prompt not transferred"**
- Verificar sintaxe do prompt
- Testar com prompt simples primeiro

## Problema de Performance

**"High memory usage"**
- Reduzir max_workers em config.json
- Desabilitar auto-scan
- Limpar cache de thumbnail

**"CPU 100%"**
- Pausar verificação automática
- Reduzir threads em settings

## Crash/Log

Visualize logs em:
```
Settings > Logs > (selecione nível: DEBUG/INFO/WARNING/ERROR)
```

Procure por mensagens de erro ou exceções.

## Solicitação de Suporte

Se problema persistir:
1. Copie logs de erro
2. Descreva passos para reproduzir
3. Abra issue no GitHub

