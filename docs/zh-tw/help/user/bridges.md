# Bridge 連動

Bridge 功能可從 YU AI Manager 直接將提示詞傳送至各種 AI 圖片生成工具。

## 支援的 Bridge

### SD WebUI Bridge
與 Stable Diffusion WebUI (Automatic1111 / Forge) 連動。
- 提示詞的收發
- 生成參數的傳輸

### NAI Bridge
與 NovelAI 連動。
- 提示詞語法的自動轉換（SD <-> NAI）
- 品質標籤的自動插入

#### Vibe Transfer（NAI 藥水）與 encode-vibe 快取

NAI V4+ 模型需要先透過 `/ai/encode-vibe` API 對參考圖片進行編碼（**每次 2 Anlas**）才能用於生成。

為避免相同圖片重複生成時浪費 Anlas，編碼結果會快取至本機：

```
data/nai_vibe_cache/<sha256>__<model>__<info_extracted>.bin
```

- **鍵值**：原始圖片 SHA256 + 模型名稱 + 資訊提取度（0.01 步進）
- **上限**：預設 500 MB。可在 Settings > NAI Bridge > "Vibe encode cache (MB)" 調整（0 = 停用）
- **LRU 淘汰**：超出限制時，背景執行緒按最舊順序刪除

### ComfyUI Bridge
與 ComfyUI 連動。
- 將提示詞插入工作流程
- 輸出格式的自訂

## 批次生成

三種 Bridge 的主要生成路徑均支援批次生成（A1111 相容語意）。

### Batch count / Batch size

- **Batch count** — 連續生成的次數（時間方向）。客戶端每次呼叫一次 API
- **Batch size** — 單次 API 呼叫並列生成的張數（VRAM 方向）。NAI Bridge 不顯示此項
- 總張數 = Batch count × Batch size

固定 Seed 時，loop 內的 seed 會以 `base + i` 遞增（與 A1111 相同）。`-1`（隨機）時，每次都會產生新的隨機 seed。

### 停止按鈕

| Bridge | 單次 (count=1) | loop (count>1) |
|---|---|---|
| NAI | 無停止按鈕 | 僅「完成本張後停止」 |
| SD WebUI | 「停止」(伺服器 cancel API) | 「完成本張後停止」+「停止」 |
| ComfyUI | 「停止」(伺服器 cancel API) | 「完成本張後停止」+「停止」 |

- **停止（即時）** — 中斷進行中的 API 呼叫並停止 loop。SD WebUI / ComfyUI 同時呼叫伺服器 cancel API
- **完成本張後停止** — 讓目前正在生成的圖片完成後，不再送出下一次

NAI Bridge 的單次生成沒有停止按鈕，原因是 NAI API 在接受 fetch 的瞬間即扣除 Anlas（點數）。切斷 HTTP 連線無法停止伺服器端的生成或退費，因此顯示停止按鈕只會造成誤解，故意圖性地不顯示。

### VRAM 注意事項

提高 Batch size 會按張數等比增加伺服器 GPU 的 VRAM 使用量。SDXL 搭配 Batch size 4 以上可能導致 OOM，建議從 1 開始嘗試。

## 品質預設

各 Bridge 工具列上的「QP」按鈕可一鍵插入品質提升標籤。

內建預設：
- SD High Quality
- SD Realistic
- NAI Quality
- NAI Artistic
- Minimal

也可建立自訂預設。

## 解析度預設

SD WebUI Bridge 和 ComfyUI Bridge 的 Width/Height 輸入框上方有「Resolution Preset」下拉選單和 ⇄ 交換按鈕，可一鍵選擇常用解析度。

- **SD 1.5** — 適用於 SD1.5 系模型的 5 種常用解析度（512 基準）
- **SDXL Trained** — SDXL 官方訓練桶 9 種（品質優先）
- **SDXL Cheat Sheet** — 電影・攝影的長寬比以 8 的倍數近似的 12 種（構圖優先，來源 [Civitai](https://civitai.com/articles/2246/sdxl-image-size-cheat-sheet)）

選擇 `Custom` 會保留目前的 W/H 值。套用預設後手動編輯 W/H 會自動回到 `Custom`。⇄ 按鈕可交換寬高。

Cheat Sheet 解析度超出官方桶範圍，部分模型可能會產生輕微的構圖偏差。

> ComfyUI Bridge 僅於 Simple 模式套用，Raw JSON Workflow 模式的節點值不會被修改。

## Bridge 間傳輸

可在 Bridge 之間直接傳輸提示詞。SD <-> NAI 之間的語法會自動轉換。

## 傳送至 Bridge

從圖片詳細模態視窗的工具列，可將目前顯示的圖片的提示詞或圖片本身直接傳送至生成 Bridge。

- **傳送提示詞 ▾** — 將顯示圖片的提示詞傳送至 NAI Bridge / SD WebUI / ComfyUI 的其中一個。以 NAI 語法撰寫的提示詞，若目標為 SD/ComfyUI 則自動轉換為 SD 語法，反之亦然。NAI v4 的角色提示詞（positive/negative），若目標為 NAI Bridge 則保持結構化傳送，否則合併至主提示詞後傳送。
- **傳送圖片 (img2img) ▾** — 將顯示圖片的完整解析度直接設定至 NAI Bridge / SD WebUI / ComfyUI 的 img2img 槽位。ComfyUI 自 v4.121.0 起支援。
- **重混 ▾**（v4.121.3〜） — **同時**傳送提示詞與圖片。對相同圖片微調提示詞並重新生成時，1 鍵完成。可選目標：NAI / SD WebUI / ComfyUI。

按鈕顯示條件：
- 傳送提示詞：圖片包含提示詞中繼資料（positive/negative 或角色資訊）時
- 傳送圖片：目前顯示的媒體為圖片（靜態圖片 / 動態圖片 / 影片）時。影片時將擷取目前播放位置的畫格傳送（v4.121.20〜）
- 重混：以上兩個條件皆成立時

注意事項：
- PDF、音訊不會顯示「傳送圖片」
- 影片畫格傳送時，僅傳送目前播放位置的 1 幀 PNG，不會傳送原始影片
- 若提示詞轉換失敗，會以原始語法傳送，並在目標 Bridge 畫面顯示警告 toast
- 僅傳送提示詞/圖片。取樣器、步數、CFG、Seed 等參數不會在目標端還原（使用 Bridge 端的預設值或上次的設定值）
