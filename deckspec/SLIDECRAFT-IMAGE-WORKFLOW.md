# SlideCraft 配圖工作流程（Option A）

## 設計原則

**圖進 repo，CI 只驗證不生圖。**

```
生圖（本地）→ commit → push → CI 驗證 → deploy
```

- Grok Draw 只在**本地開發環境**使用（有認證 + GPU）
- CI 不做生圖 — 只負責 render、verify、deploy
- 圖檔進版控（Git LFS 或直接 commit，看檔案大小）

---

## 一、目錄結構

每份 deck 的配圖放在對應目錄：

```
deckspec/images/<deck-name>/
├── slide_01_bg.jpg      # 第 1 頁背景
├── slide_02_bg.jpg      # 第 2 頁背景
├── slide_03_bg.jpg      # 第 3 頁背景
└── ...
```

---

## 二、生圖（本地）

用 Grok CLI 或 Grok Draw 生背景圖：

```bash
# Grok CLI（推薦）
grok -p "Medical clinic interior, warm lighting, photorealistic, 1920x1080"
cp ~/.grok/sessions/*/images/1.jpg deckspec/images/his-proposal/slide_01_bg.jpg

# Grok Draw CDP（備援）
python3 ~/.hermes/profiles/deepseek-reasoner/scripts/draw.py \
  --engine grok --timeout 60 \
  "Medical clinic interior, warm lighting, photorealistic" \
  deckspec/images/his-proposal/slide_01_bg.jpg
```

**格式規則：**
- 解析度 ≥ 1280×720（背景圖會裁切）
- 單圖 ≤ 300KB
- 格式：.jpg 或 .webp
- 主題色系：接近 deck 的 theme colors

---

## 三、在 DeckSpec 中引用

```json
{
  "slides": [
    {
      "id": "s01",
      "layout": "cover",
      "title": "...",
      "background_image": "deckspec/images/his-proposal/slide_01_bg.jpg",
      "background_override": "linear-gradient(135deg, rgba(0,0,0,0.75) 0%, rgba(0,0,0,0.55) 100%)"
    }
  ]
}
```

**注意：**
- `background_image` 使用**相對 repo root 的路徑**
- engine.py 會自動複製到 `output/<deck>_images/` 並更新路徑
- renderer 產出的 HTML 使用相對路徑指向 images 目錄
- 務必加上 `background_override`（暗色 overlay），確保白字對比

---

## 四、Commit & Push

```bash
git add deckspec/images/<deck-name>/
git commit -m "images: add <deck-name> background images"
git push origin main
```

**路徑過濾器：** CI workflow 已包含 `deckspec/*.json` → 但修改 `deckspec/images/` 不會觸發。只要 spec 在範圍內就夠了 — push 時就算只改 images，也要順便確認 spec 是最新版。

---

## 五、CI 處理流程

Engine (`orchestrator/engine.py`) 在 render 階段：

1. 讀取 spec → 發現 `background_image: "deckspec/images/deck/slide_01_bg.jpg"`
2. 檢查 `os.path.exists("deckspec/images/deck/slide_01_bg.jpg")` → ✅ 存在
3. 複製到 `output/<deck>_images/slide_01_bg.jpg`
4. 更新 spec：`s["background_image"] = "output/<deck>_images/slide_01_bg.jpg"`
5. Renderer 產出 HTML：`<img src="<deck>_images/slide_01_bg.jpg">`
6. Verify-deck 檢查每張圖的 HTTP 200 + naturalWidth > 0 + size < 300KB
7. Deploy：`output/` → gh-pages `decks/`

**佈署後 URL 結構：**
```
https://julian67chou.github.io/slidecraft/decks/
├── deck_20260614_020149.html
└── deck_20260614_020149_images/
    ├── slide_01_bg.jpg
    ├── slide_02_bg.jpg
    └── ...
```

---

## 六、驗證方式

### CI 自動驗證

`scripts/verify-deck.py` 用 Playwright 實際載入 HTML，監聽：
- HTTP response：每張圖 status = 200
- DOM：`img.naturalWidth > 0`
- File size：每張圖 < 300KB

任一項失敗 → exit code 1 → CI 阻止 deploy。

### 本地驗證

```bash
# 全項驗證
python scripts/verify-deck.py --html output/<deck>.html

# 只看圖片
python scripts/verify-deck.py --html output/<deck>.html 2>&1 | grep "Image issue"

# 直接檢查圖片路徑
curl -sI https://julian67chou.github.io/slidecraft/decks/<deck>_images/slide_01_bg.jpg | grep "200"
```

---

## 七、無圖時的 Fallback

如果 CI 跑但圖還沒準備好：

1. 在 spec 中**移除** `background_image` 和 `background_prompt`
2. 使用深色 theme（如 `pitch-dark`），純色背景
3. 白字對比約 19:1，100% PASS
4. 之後本地生圖 → commit → push → CI 自動更新 deck

---

## 八、完整流程範例

```bash
# Step 1: 修改 spec
vim deckspec/his-proposal.json

# Step 2: 生圖（本地）
grok -p "Medical clinic waiting area, modern design, warm lighting" 
cp ~/.grok/sessions/latest/images/1.jpg deckspec/images/his-proposal/slide_01_bg.jpg
grok -p "Doctor using computer, medical office, professional" 
cp ~/.grok/sessions/latest/images/1.jpg deckspec/images/his-proposal/slide_02_bg.jpg

# Step 3: 確認 spec 引用路徑正確
grep background_image deckspec/his-proposal.json
# → "deckspec/images/his-proposal/slide_01_bg.jpg"

# Step 4: Commit & push
git add deckspec/ && git commit -m "feat: add background images to his-proposal deck"
git push origin main

# Step 5: 等 CI 跑完（～2-3分鐘）
gh run list --limit 1 --json status,conclusion

# Step 6: 驗證佈署結果
curl -s https://julian67chou.github.io/slidecraft/decks/deck_20260614_020149 | grep -o 'src="[^"]*\.jpg"' | head
```
