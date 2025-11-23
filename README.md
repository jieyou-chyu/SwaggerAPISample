# SwaggerAPISample

這個專案示範如何批次抓取 TWSE／TPEX／TAIFEX 的 Swagger（OpenAPI）定義，並對所有 GET 端點發送請求，將結果存成 JSON，後續可用 GitHub Pages 的靜態頁面讀取並轉成 HTML 表格。

功能概述：
- 以 `swagger_API.py` 下載三個來源的 Swagger 定義檔，解析 GET 端點並發送請求
- 將每個端點的 JSON 回應存到 `swagger/<source>/` 目錄（twse、tpex、taifex）
- 產生清單檔 `swagger/<source>/manifest.json` 與總覽 `swagger/summary.json`
- GitHub Pages（docs/index.html）可讀取上述 JSON，渲染成表格，並支援下載 CSV

本地執行：
1. 安裝套件（若尚未安裝）：
   - pip install requests pandas urllib3
2. 執行：
   - python swagger_API.py
3. 產出結果：
   - swagger/twse/*.json
   - swagger/tpex/*.json
   - swagger/taifex/*.json
   - swagger/summary.json
   - swagger/<source>/manifest.json

GitHub Pages 設定：
- 已提供 `docs/index.html`，可直接在 repo 啟用 GitHub Pages（Source 選擇 `main` 分支、根目錄設定為 `/docs`）。
- 啟用後頁面可用來：
  - 載入 `swagger/<source>/manifest.json` 清單，選擇檔案
  - 或直接輸入 `swagger/<source>/<檔名>.json` 的路徑
  - 將 JSON 內容轉成 HTML 表格、支援下載 CSV

使用方式（GitHub Pages 頁面）：
- 預設來源有 TWSE/TPEX/TAIFEX 三種，亦可選擇自訂 URL
- 若 JSON 結構中不存在明確的陣列，頁面會退化為顯示物件鍵值
- 可以直接輸入任何符合 CORS 規則的 JSON URL

注意事項：
- 公開資料端點可能偶有 SSL 驗證問題，程式已內建 `verify=False` 的後備機制（僅限公開資料）。
- 若要對需要授權的 API 測試，請先在 `swagger_API.py` 加入 Authorization Header 或白名單端點。
- 若 JSON 結構複雜，頁面會盡力尋找常見鍵（data、records、items…），無法自動判定時會改為鍵值視圖。
