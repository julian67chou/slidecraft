# SlideCraft Templates

簡報範本庫。每個 `.json` 就是一種簡報的「配方」——定義了主題色、頁面結構、layout 分佈、build step 設定。

## 使用方式

1. 選一個範本（或自己寫）
2. 寫進 Grok prompt：「照這個範本，內容換成 OOO」
3. Grok 生 DeckSpec → 小彌驗收 → deploy

## 範本清單

| 檔案 | 說明 | 頁數 | 配圖 |
|------|------|------|------|
| `cross-culture.json` | 跨文化溝通 | 10頁 | 4張（Grok Draw） |
| `_skeleton.json` | 通用骨架（從零開始） | 自訂 | 自訂 |

## 規範

所有範本遵循 SlideCraft Layout Rules：
- 每頁內容 ≤ 640px（1280×720 扣 padding）
- build step 全揭露後仍 ≤ 640px
- card padding ≤ 16px，grid gap ≤ 12px
- 手機 compact mode 下 grid 排成 1 欄
- 背景圖需有 dark overlay
