# 搜尋

## 基本搜尋

在搜尋列中以逗號分隔輸入標籤。

```
1girl, blue_eyes, school_uniform
```

## 搜尋篩選器

| 篩選器 | 說明 |
|---------|------|
| 日期範圍 | 以起始日～結束日進行篩選 |
| 檔案格式 | PNG / WebP / JPG / GIF |
| 評分 | 以 1～5 星進行篩選 |
| 收藏 | 僅顯示已加入收藏的項目 |
| 合集 | 僅顯示特定合集內的項目 |

## 提示詞內搜尋

使用「in_prompt」欄位可對圖片的提示詞文字進行全文搜尋。
若 FTS (Full-Text Search) 已啟用，可進行高速搜尋。

## 排序方式

| 排序 | 說明 |
|--------|------|
| date | 註冊日（最新優先） |
| date_old | 註冊日（最舊優先） |
| folder | 資料夾順序 |
| path | 路徑順序 |
| random | 隨機 |
| rating_desc | 評分（由高到低） |
| rating_asc | 評分（由低到高） |

## 語意搜尋

若已設定 Hailo-10H 或 ONNX CLIP 模型，可使用自然語言搜尋圖片。
請使用搜尋列右側的語意搜尋按鈕。

### 使用 FAISS 加速（建議）

語意搜尋預設使用 NumPy 進行暴力搜尋，
**安裝 FAISS 後可大幅提升速度**。

| 圖庫規模 | NumPy（預設） | FAISS（建議） |
|-------------|-------------------|-------------|
| 1 萬件以下 | 數十 ms | 數 ms |
| 10 萬件 | 1～3 秒 | 數十 ms |
| 100 萬件以上 | 10 秒以上 | 100 ms 以下 |

FAISS 會根據搜尋對象的規模自動選擇最佳索引：
- **5 萬件以下**：IndexFlatIP（精確全量搜尋，速度已足夠快）
- **5 萬件以上**：IndexIVFFlat（近似最近鄰搜尋，大規模也能高速處理）

#### 安裝方式

```bash
# 先啟用 venv 再安裝
source venv/bin/activate

# x86_64 (Intel/AMD) — 可直接用 pip 安裝
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — pip 無法安裝時
# 方法 1：透過 conda
conda install -c conda-forge faiss-cpu

# 方法 2：從原始碼建置
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

安裝後只需重新啟動伺服器即可自動偵測。
若啟動日誌中顯示以下訊息，表示 FAISS 已啟用：

```
FAISS x.x.x detected — using accelerated vector search
```

即使未安裝 FAISS，仍可使用 NumPy 正常運作。
