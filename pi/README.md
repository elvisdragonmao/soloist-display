# 樹莓派現有設定快照

從 `har`（Raspberry Pi 5，Debian 13 trixie，labwc）抓下來的設定，做為參考與還原用。
由 `install.sh` 管理的檔案不放這裡（見 `soloist/`、`display/`）。

| 檔案 | 在 Pi 上的位置 |
| --- | --- |
| `kanshi/config` | `~/.config/kanshi/config`（4K 電視、scale 2） |
| `labwc/environment` | `~/.config/labwc/environment` |
| `autostart/m-air-edit.desktop` | `~/.config/autostart/m-air-edit.desktop`（Midas MR18 混音器控制） |

`~/.config/soloist/soloist.env` 內含 Soloist API key 與裝置名稱（`🪗 活中社辦樹莓派`），不進版控；格式見 `soloist/soloist.env.example`。

`~/apps/spotify-soloist/` 是最早手動下載 Soloist 的目錄，現在由 `soloist-update` 直接更新 `/usr/local/bin/soloist`，那個目錄已不再使用。
