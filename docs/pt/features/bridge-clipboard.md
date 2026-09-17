# Atalho de Clipboard para Bridge

Nas páginas NAI Bridge / ComfyUI Bridge / SD WebUI Bridge, uma tecla de atalho permite
enviar instantaneamente o texto do clipboard para o campo de prompt. Quando você copiar um prompt
de outra janela, pode aplicá-lo sem primeiro clicar na textarea.

## Atalho

| SO | Teclas |
|---|---|
| Windows / Linux | `Ctrl` + `Alt` + `V` |
| macOS | `⌘` + `⌥` + `V` |

Isso é adicionado junto com a colagem nativa do navegador (`Ctrl`+`V`) e não
interfere com o comportamento de colagem existente.

## Comportamento

1. Abra uma das páginas de Bridge
2. Copie texto de uma fonte externa (`Ctrl`+`C`)
3. Pressione `Ctrl`+`Alt`+`V` enquanto a página de Bridge tem foco
4. Seleção de destino:
   - Se uma textarea está em foco → inserida na posição do cursor nessa textarea
   - Se nada está em foco → inserida no campo de prompt positivo (NAI: `#nabPrompt` / ComfyUI: `#cfbPrompt` / SD: `#sdwbPrompt`)
5. No sucesso, um toast "Clipboard text inserted" é mostrado

## Campos de Destino

| Bridge | Prioridade de destino |
|---|---|
| NAI Bridge | `nabPrompt` → `nabNegative` |
| ComfyUI Bridge | `cfbPrompt` → `cfbNegative` → `cfbWorkflowJson` |
| SD WebUI Bridge | `sdwbPrompt` → `sdwbNegative` |

## Permissões do Navegador

Isso usa a **Clipboard API** do navegador (`navigator.clipboard.readText()`),
então o navegador pode solicitá-lo para permissão de leitura da área de transferência ao primeiro uso.
Se você negar, o recurso não funcionará.

Em navegadores mais antigos onde a Clipboard API não está disponível, um toast "Clipboard
API not available" é mostrado e nada acontece. A colagem regular `Ctrl`+`V` continua
funcionando como antes.

## Limitações

- Alguns navegadores exigem HTTPS ou `localhost` para que `navigator.clipboard` esteja
  disponível (Chrome permite `localhost`)
- Apenas texto simples é suportado — não imagens ou texto rico
- Elementos que não são `<textarea>` (por exemplo, regiões `contenteditable`) não são direcionados
  mesmo quando em foco
