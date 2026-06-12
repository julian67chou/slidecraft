# Grok 任務：生成 SlideCraft DeckSpec JSON

## 專案資訊
- 專案目錄：/workspace/gamma-ppt/
- 這是 SlideCraft 簡報生成器，input 是 DeckSpec JSON，output 是 HTML 簡報
- Source code 在 renderers/html/renderer.py — 可以看 layout 實作

## 你的任務
生成一份 10 頁的「多元文化職場溝通技巧」DeckSpec JSON，存到 /workspace/gamma-ppt/cross-culture-spec.json

## 風格要求
- 專業簡約（professional minimal）
- 文字大而清晰
- 不要 emoji
- 每頁都要有配圖、圖表或流程圖 — 用 inline SVG 直接嵌在 extra.inline_svg 欄位
- 主題用 academic-clean（白底 + 沉穩藍灰）

## 可用 Layouts
- cover — 封面
- content — 純內容（標題 + 條列）
- two-column — 雙欄對比
- card-list — 卡片列表（自動 3 欄）
- stat-card — 數字統計卡片（4 欄）
- timeline — 時間軸/流程
- comparison — 左右對比表
- quote — 引言頁
- transition — 章節過渡頁
- grid — 2×2 網格
- process-flow — 橫向流程步驟（圓圈+連線）
- image-text — 圖文並排
- team — 團隊介紹（但這裡不用）

## DeckSpec JSON 格式
```json
{
  "deck_id": "cross-culture-communication",
  "title": "多元文化職場溝通技巧",
  "num_slides": 10,
  "global_design": {
    "theme_id": "academic-clean",
    "accent_override": null
  },
  "slides": [
    {
      "id": "s01",
      "order": 1,
      "layout": "cover",
      "content": {
        "title": "多元文化職場溝通技巧",
        "subtitle": "打造包容、高效的國際化團隊",
        "bullets": [],
        "stats": [],
        "columns": [],
        "steps": [],
        "quote": null,
        "visual": {
          "type": "none",
          "prompt": null
        },
        "extra": {}
      }
    }
  ],
  "source_prompt": "Generate a 10-slide deck about cross-cultural workplace communication skills",
  "generated_at": "2026-06-12T10:00:00"
}
```

## 每頁詳細要求

### 第1頁 — 封面 (cover)
- 標題：多元文化職場溝通技巧
- 副標題：打造包容、高效的國際化團隊

### 第2頁 — 為什麼重要 (content)
- 說明全球化職場現狀、跨文化溝通為何是必備技能
- 加一個 inline SVG 長條圖顯示跨文化團隊比例

### 第3頁 — 文化差異維度 (card-list)
- 卡片列出 Hofstede 文化維度：權力距離、個人vs集體、不確定性規避、長期導向
- 每個卡片有標題+說明

### 第4頁 — 溝通風格比較 (comparison)
- 高情境 vs 低情境文化溝通風格
- 左右欄對比：間接vs直接、含蓄vs明確、關係vs任務

### 第5頁 — 常見誤解 (grid / 2×2)
- 4個格子：語言障礙、非語言誤讀、刻板印象、價值觀衝突
- 每個格子有標題+描述

### 第6頁 — 溝通技巧流程 (process-flow)
- 5步驟流程：觀察→傾聽→確認→調整→反饋
- 用 process-flow layout

### 第7頁 — 數字會說話 (stat-card)
- 關鍵統計數據：85%跨文化專案有溝通障礙、73%員工...
- 4個統計卡片，附 inline SVG 補充圖表

### 第8頁 — 實戰案例 (timeline)
- 時間軸呈現一個跨文化協作案例從衝突到成功的過程
- 每個節點：問題→理解→調整→成果

### 第9頁 — 黃金法則 (content 或 quote)
- 跨文化溝通的核心原則列表
- 加一個 inline SVG 圓餅圖或流程圖

### 第10頁 — 結尾 (transition)
- 結語：溝通無國界，理解有深度
- 簡單收尾，加一個代表性 inline SVG

## 重要提醒
1. **絕對不要用 emoji** — 連 bullet 都不要用特殊符號，用「•」或「-」
2. **每頁都加 inline SVG** — 放在 extra.inline_svg 欄位，SVG 要 self-contained
3. **文字要夠大夠清晰** — 這是投影簡報不是手機閱讀
4. **圖表要自製 inline SVG** — 不要用外部圖片或圖示，也不要寫「此處放圖表」
5. **路徑相關資料要用台灣職場情境** — 舉例用台商、外商、半導體等

## 產出格式
把你生成的完整 JSON 存到 /workspace/gamma-ppt/cross-culture-spec.json

完成後跟我說「完成」，不需要貼 JSON 內容。
