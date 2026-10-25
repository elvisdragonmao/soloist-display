# soloist-display

社辦樹莓派（`har`，Raspberry Pi 5，接 4K 電視）上的 Spotify Soloist 設定，以及一個「正在播放」全螢幕畫面：
模糊流動的封面背景、專輯封面、進度條、歌名／歌手／專輯，還有逐字亮起的同步歌詞，效果仿照 [Spicy Lyrics](https://github.com/spikerko/spicy-lyrics)。

## 部署

```sh
./deploy.sh            # 同步 repo 到 har:~/apps/soloist-display 並執行 install.sh
./deploy.sh soloist    # 只裝 Soloist 服務與自動更新
./deploy.sh display    # 只裝正在播放畫面
```

`install.sh` 也可以直接在 Pi 上執行。Soloist API key 放在 Pi 的 `~/.config/soloist/soloist.env`，不進版控（格式見 `soloist/soloist.env.example`）。

## Soloist 自動更新

Soloist 官方執行檔發布 90 天後失效，失效後 systemd 重啟也救不回來，必須換新版。

- `soloist-update.timer`（root）每天 05:30 與開機 3 分鐘後執行 `/usr/local/sbin/soloist-update`。
- 腳本下載 `soloist_release_arm64.tar.gz`，跟 `/usr/local/bin/soloist` 比對，不同才安裝：停掉 `spotify-soloist` 使用者服務 → 安裝（舊版留在 `soloist.prev`）→ 重新啟動。
- 正在播音樂時會延後，不打斷播放；要立刻更新：`sudo soloist-update --force`。
- 紀錄：`journalctl -u soloist-update`。

## 正在播放畫面

```
Soloist ──WebSocket──▶ Chromium（全螢幕 app 視窗）
                          ▲
server.py ──HTTP──────────┘  網頁、Soloist 的 WS 位址、歌詞（LRCLIB，快取在 ~/.cache/soloist-display）
```

- Soloist 以 `--ws 127.0.0.1:0` 開啟本機 WebSocket API，每次啟動埠號都不同；`server.py` 從 `~/.local/share/soloist/ws.port` 讀出來給網頁，斷線時網頁會重新查詢並重連。
- 歌詞來源是 [LRCLIB](https://lrclib.net)（免金鑰）。只有逐行時間軸，所以每個字的亮起時間依字數估算；LRC 若帶 `<mm:ss.xx>` 逐字標記則照實際時間。沒有歌詞或純音樂時，封面移到畫面中央。
- 背景是 [Kawarp](https://github.com/better-lyrics/kawarp)（MIT，放在 `display/web/vendor/`），與 Spicy Lyrics 相同。
- 沒在播放、別的裝置接手、或暫停超過 15 分鐘時顯示時鐘與裝置名稱。

### 操作

| 動作 | 方式 |
| --- | --- |
| 開機自動開啟 | `~/.config/autostart/soloist-display.desktop` |
| 切到其他 App | Alt+Tab，或按 Super 開選單 |
| 跳回正在播放 | **Ctrl+Alt+P**，或從應用程式選單點「正在播放」 |
| 離開全螢幕 | F11 |

### 參數

網址參數（改 `soloist-display-open` 裡的 `URL`，或設定 `SOLOIST_DISPLAY_URL`）：

- `?offset=300`：歌詞提早 300 ms（負數延後）。
- `?demo=曲名|歌手|秒數|封面網址|起始秒數`：播放假資料，不連 Soloist，用來調整畫面。

### 本機開發

```sh
ssh -N -L 45999:127.0.0.1:$(ssh har cat .local/share/soloist/ws.port) har &
mkdir -p /tmp/sol && echo 127.0.0.1 > /tmp/sol/ws.addr && echo 45999 > /tmp/sol/ws.port
SOLOIST_DATA_DIR=/tmp/sol python3 display/server.py --port 8788
# 開 http://localhost:8788/ 或 http://localhost:8788/?demo=Shape%20of%20You|Ed%20Sheeran|234
```

## 目錄

| 路徑 | 內容 |
| --- | --- |
| `soloist/` | `spotify-soloist.service`、自動更新腳本與 timer |
| `display/server.py` | 本機 HTTP server（只用 Python 標準函式庫） |
| `display/web/` | 正在播放畫面 |
| `display/soloist-display-open` | 開啟或切回畫面的啟動腳本 |
| `pi/` | Pi 上其他既有設定的快照（kanshi、labwc、M-AIR Edit 自動啟動） |
