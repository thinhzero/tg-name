# tg-name — Tự đổi tên và bio Telegram

Chạy bằng **tài khoản Telegram của bạn** để cập nhật tên/bio khoảng mỗi phút. Ví dụ:

```text
HzzMonet | 11:35 - 25/10 | GMT +7 | eat29
```

`eat29` được chọn ngẫu nhiên từ các dòng trong `name.txt`. Có thể thêm thời tiết, nhạc Last.fm
và một Helper Bot riêng để điều khiển bằng nút bấm. **Helper Bot là tùy chọn.**

> Không chia sẻ `.env`, `SESSION_STRING`, file `*.session`, OTP hoặc mật khẩu 2FA.
> Session cho phép truy cập tài khoản của bạn. Repo không cung cấp API key dùng chung.

## 1. Cài đặt lần đầu

**Cần có:** Python 3.10 trở lên, Git, kết nối mạng và tài khoản Telegram.
Các lệnh trong khối `bash` bên dưới chạy ở **terminal trên máy/VPS**, không gửi vào Telegram.

### Bước 1 — Tải code và cài thư viện

```bash
git clone https://github.com/thinhzero/tg-name.git
cd tg-name
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Nếu Ubuntu/Debian báo thiếu `venv`, cài gói `python3-venv` rồi thử lại.
Các ví dụ terminal còn lại giả sử bạn đang ở thư mục `tg-name` và đã kích hoạt `.venv`.

### Bước 2 — Chọn cách cấu hình và đăng nhập

**Cách A — Cài trực tiếp ở terminal** (không bắt buộc có Helper Bot):

```bash
python setup.py
```

Chọn **1 — Cài đặt từng bước**, sau đó:

1. Mở https://my.telegram.org/apps, tạo ứng dụng và lấy **API_ID**, **API_HASH của riêng bạn**.
   Nhập hai giá trị vào wizard. Không có giá trị mặc định cho hai mục này.
2. Chọn đăng nhập Telegram. Nhập số điện thoại kèm mã quốc gia, mã xác nhận và 2FA nếu có.
   Wizard tự lưu `SESSION_STRING` vào `.env`; không cần tự sao chép chuỗi session.
3. Ở mục Helper Bot: **để trống BOT_TOKEN nếu chưa cần bot riêng**. Nếu muốn dùng,
   lấy token từ https://t.me/BotFather và nhập `ADMIN_ID` là ID số của chính bạn.
   Wizard tự có ID này nếu bước đăng nhập đã thành công.
4. Thời tiết: nhập thành phố. Có thể để trống `WEATHER_API` để dùng `wttr.in`.
5. Nhạc: nếu không dùng, bỏ qua. Nếu dùng, cần cả Last.fm username và API key riêng.
6. Nhập tên cố định, ví dụ `HzzMonet`. Với múi giờ Việt Nam chọn `Asia/Ho_Chi_Minh`.
   Nhấn Enter ở mẫu tên để dùng mẫu tên + giờ + GMT + random như ví dụ đầu trang.
7. Ở câu hỏi khởi chạy cuối wizard, chọn **1** để chạy ngay.

Khi nhập API hash/token/key, terminal không hiện ký tự — đây là chủ ý, không phải bị treo.
Nếu đã thoát wizard, khởi chạy bằng:

```bash
python name.py
```

**Chỉ chạy một bản bot cho cùng tài khoản/session.** Không mở thêm `name.py` nếu wizard
hoặc PM2 đã chạy bot. Nhấn `Ctrl+C` để dừng bản đang chạy ở terminal.

**Cách B — Chỉ điền BOT_TOKEN + ADMIN_ID, rồi cài toàn bộ qua chat bot:**

Không cần điền API_ID/API_HASH hoặc đăng nhập tài khoản ở terminal trước. Sau khi cài
thư viện ở bước 1, chọn **10** trong `python setup.py`: nhập BOT_TOKEN và ADMIN_ID,
wizard sẽ lưu `.env` và chạy bot ngay. Hoặc tự chuẩn bị `.env` rồi chạy:

```bash
cp -n .env.example .env
nano .env
python name.py
```

Trong `.env`, **chỉ điền hai dòng `BOT_TOKEN=` và `ADMIN_ID=` bằng giá trị thật của bạn**.
Để `API_ID=`, `API_HASH=`, `SESSION_STRING=` trống. `cp -n` không ghi đè `.env` đã có;
nếu đang dùng bản cũ đã có API/session thì không cần xóa chúng để dùng `/setup`.

Sau khi tiến trình đã chạy:

1. Dùng đúng tài khoản có ID đã điền ở `ADMIN_ID`, mở chat riêng với bot và nhấn **Start**.
   Bot đọc ID từ `.env`, **không nhận người nhắn đầu tiên làm admin**. Nếu chưa nhấn Start,
   Telegram chưa cho bot tự nhắn bạn, nên terminal sẽ nhắc mở bot.
2. Bấm **Nhập API_ID / API_HASH**. Bot lần lượt hỏi API_ID và API_HASH riêng từ
   https://my.telegram.org/apps, kiểm tra rồi lưu `.env`. Không gửi BOT_TOKEN vào chat.
3. Bot tự chuyển sang màn hình đầy đủ, **không cần chạy lại ở terminal**. Bấm
   **Đăng nhập Telegram**, nhập số điện thoại, mã xác nhận và mật khẩu 2FA nếu có.
4. Session tự lưu, bot tự chạy cập nhật profile sau khi đăng nhập. Chọn các nút
   **Tên hiển thị**, **Múi giờ**, **Mẫu tên / Bio** để tùy chỉnh tiếp.
5. Dùng `/setup` hoặc nút **Cài đặt từng bước** để mở lại hướng dẫn, `/cancel` để hủy
   thao tác nhập. `ADMIN_ID` không bị đổi sang ID tài khoản bạn đăng nhập.

Ở bước thiếu API, bot dùng **Telegram Bot API** chỉ bằng token; sau khi có API riêng mới
khởi chạy Helper Bot/Userbot bằng Telethon. Không cần key công khai ghi cứng.
Bot cố xóa tin nhắn chứa API hash, OTP và 2FA sau khi xử lý; việc xóa có thể thất bại do
quyền/mạng và không thay thế bảo mật tài khoản. Chỉ dùng bot do chính bạn vận hành.
Nếu bot đã gắn webhook ở dịch vụ khác, hãy dừng dịch vụ/gỡ webhook đó trước; không chạy
nhiều tiến trình cùng token.

### Bước 3 — Kiểm tra trên Telegram

Mở **Saved Messages / Tin nhắn đã lưu** của tài khoản vừa đăng nhập và tự gửi:

```text
.status
.preview
```

Các lệnh bắt đầu bằng dấu **`.`** do chính tài khoản Userbot gửi. Bạn bè gửi lệnh không
điều khiển được Userbot. Các lệnh bắt đầu bằng **`/`** chỉ dùng khi nhắn riêng Helper Bot.

## 2. Dùng đúng mẫu tên có random

Gửi **từng lệnh riêng** trong Saved Messages:

```text
.name HzzMonet
.nameformat {base_name} | HH:mm - DD/MM | {gmt} | {random}
.updaterandom sleep
.updaterandom đang ăn
.lsrandom
.update
```

- Thay `HzzMonet` bằng tên của bạn.
- Giữ nguyên `{base_name}`, `{gmt}`, `{random}` trong lệnh mẫu: bot sẽ tự điền chúng.
- `{gmt}` dùng múi giờ đã chọn; `Asia/Ho_Chi_Minh` cho kết quả `GMT +7`.
- `.update` đổi **tên/bio ngay**, không phải cập nhật mã nguồn.

### Thêm / xem / xóa random

| Việc cần làm | Lệnh trên Userbot |
| --- | --- |
| Thêm một mục | `.updaterandom nội dung mới` |
| Xem toàn bộ mục và UID | `.lsrandom` |
| Xóa một mục | `.rmrandom UID` |

Ví dụ kết quả `.lsrandom`:

```text
UID — Nội dung
a1b2c3d4e5f6 — sleep
```

Để xóa mục đó, gửi `.rmrandom a1b2c3d4e5f6`. **Dùng UID thực bot trả về**, không dùng UID
mẫu trên. UID là mã của mục random, không phải ID tài khoản Telegram.

Có thể thêm nhiều mục trong **một tin nhắn nhiều dòng**:

```text
.updaterandom uống trà
đọc sách
đang ngủ
```

Mỗi dòng là một mục; dòng trống và nội dung trùng bị bỏ qua. Lần đầu dùng, bot tự tạo
`name.txt` từ `name.example.txt` với mục mẫu `eat29`, nên thêm lại `eat29` sẽ báo đã có.
Bạn cũng có thể sửa `name.txt` trực tiếp. Bot đọc lại ở mỗi lần cập nhật và có thể chọn
lặp lại mục trước. UID không đổi khi sắp xếp/thêm/xóa mục khác; sửa nội dung sẽ đổi UID.
Nếu xóa hết mục, `{random}` trở thành chuỗi rỗng, không tự khôi phục mục mẫu.

## 3. Các lệnh thường dùng

Helper Bot chỉ nhận lệnh trong **chat riêng**, từ `ADMIN_ID` đã cấu hình.

| Mục đích | Userbot | Helper Bot |
| --- | --- | --- |
| Hướng dẫn | `.help` | `/help` |
| Wizard cài đặt qua nút bấm | — | `/setup` |
| Trạng thái | `.status` | `/status` hoặc `/start` |
| Xem trước tên và bio | `.preview` | `/preview` |
| Cập nhật tên/bio ngay | `.update` | `/update` |
| Tạm dừng / tiếp tục | `.pause` / `.resume` | `/pause` / `/resume` |
| Đổi tên cố định | `.name tên mới` | `/setname tên mới` |
| Đổi mẫu tên | `.nameformat mẫu` | `/nameformat mẫu` |
| Đổi mẫu bio | `.bioformat mẫu` | `/bioformat mẫu` |
| Xem bio và độ dài | `.previewbio` | `/previewbio` |
| Thêm random | `.updaterandom nội dung` | `/updaterandom nội dung` |
| Danh sách random | `.lsrandom` | `/lsrandom` |
| Xóa random | `.rmrandom UID` | `/rmrandom UID` |
| Đổi thành phố | `.city Hanoi` | `/setcity Hanoi` |
| Xem thời tiết | `.weather` | `/weather` |
| Đặt Last.fm username | `.lastfm username` | `/lastfm username` |
| Xem nhạc | `.music` | `/music` |
| Đổi ngôn ngữ | `.lang vi` / `.lang en` | `/lang vi` / `/lang en` |
| Cập nhật code và restart | `.updatecheck` | `/updatecheck` |

Trên Helper Bot, `/cancel` hủy thao tác nhập đang dang dở. Đăng nhập qua terminal được
khuyến nghị; nếu dùng wizard đăng nhập qua chat, không chuyển tiếp OTP/2FA và xóa tin nhắn
nhạy cảm sau khi hoàn tất. Không gửi token/API key trong nhóm hoặc ảnh chụp màn hình.

### Các từ khóa để viết mẫu tên / bio

| Từ khóa | Ý nghĩa |
| --- | --- |
| `{base_name}` | Tên cố định đã đặt bằng `.name` |
| `{random}` | Một dòng ngẫu nhiên trong `name.txt` |
| `{gmt}` | GMT của múi giờ hiện tại, ví dụ `GMT +7` |
| `HH:mm`, `HH:mm:ss` | Giờ:phút, hoặc giờ:phút:giây |
| `DD/MM`, `DD/MM/YYYY` | Ngày/tháng, hoặc ngày/tháng/năm |
| `hh`, `ampm` | Giờ 12 tiếng, AM/PM |
| `{thu}`, `{thu_ngan}` | Thứ đầy đủ / viết gọn theo ngôn ngữ |
| `{day}`, `{day_short}` | Thứ tiếng Anh đầy đủ / viết gọn |
| `{city}` | Thành phố |
| `{weather}`, `{weather_short}`, `{weather_medium}`, `{weather_full}` | Thời tiết các mức độ dài |
| `{temp}`, `{feels_like}`, `{humidity}`, `{wind}` | Nhiệt độ, cảm giác thực, độ ẩm, gió |
| `{weather_desc}`, `{weather_icon}`, `{sunrise}`, `{sunset}` | Mô tả, icon, bình minh, hoàng hôn |
| `{music}`, `{track}`, `{artist}`, `{album}`, `{scrobbles}` | Dữ liệu Last.fm |
| `{music_or_weather}` | Nhạc khi đang phát; thời tiết khi không phát |

Ví dụ đổi bio: `.bioformat {music_or_weather} ⏰ HH:mm`.
Bot cắt tên ở **64 ký tự**, bio ở **70 ký tự**. Có `ss` trong mẫu không làm bot đổi mỗi giây;
chu kỳ tự động vẫn khoảng một phút, có thể lâu hơn nếu Telegram yêu cầu chờ.

## 4. File `.env`: mục nào cần điền?

`.env.example` cố ý **để trống tất cả giá trị**. Wizard tạo `.env` thật trên máy bạn.
Nếu muốn tự chỉnh, sao chép `.env.example` thành `.env` rồi điền bằng trình soạn thảo.
Không ghi key/token vào lệnh shell hoặc gửi chúng lên GitHub.

| Biến | Bắt buộc? / mặc định khi trống |
| --- | --- |
| `API_ID`, `API_HASH` | Bắt buộc cho Userbot; có thể nhập qua chat sau khi bot khởi chạy bằng token + admin |
| `SESSION_STRING` | Wizard tự lưu sau khi đăng nhập; cũng hỗ trợ file session cục bộ |
| `SESSION_NAME` | `bot` — dùng khi đăng nhập bằng file session |
| `BOT_TOKEN` | Tùy chọn; để trống thì chỉ chạy Userbot |
| `ADMIN_ID` | Bắt buộc khi dùng Helper Bot; bot chỉ nhận cấu hình từ ID số này, không tự đổi sau đăng nhập |
| `BASE_NAME` | Tên của bạn; mặc định là chữ `tên` nếu chưa đặt |
| `TIMEZONE`, `LANGUAGE` | `Asia/Ho_Chi_Minh`, `vi` |
| `NAME_FORMAT` | `{base_name} \| HH:mm - DD/MM \| {gmt} \| {random}` |
| `BIO_FORMAT` | `{weather} ⏰ HH:mm` |
| `CITY` | `Bac Ninh`; đổi sang thành phố của bạn nếu dùng thời tiết |
| `WEATHER_API` | Tùy chọn: key riêng OpenWeatherMap; không có thì dùng wttr.in |
| `LASTFM_USERNAME`, `LASTFM_API_KEY` | Tùy chọn, nhưng muốn lấy nhạc phải có cả hai |

Key Last.fm: https://www.last.fm/api/account/create. Liên kết trình nghe nhạc với Last.fm
hoặc cài scrobbler trước; bot không đăng nhập trực tiếp Spotify/Apple Music.
Key thời tiết: https://home.openweathermap.org/api_keys. Nếu cả nguồn thời tiết đều lỗi,
bot chỉ hiện tên thành phố. Sau khi sửa `.env` bằng tay, khởi động lại bot để nạp cấu hình.

## 5. Chạy nền và cập nhật

Nếu máy đã cài PM2, chạy từ thư mục repo (dừng bản terminal trước):

```bash
pm2 start name.py --name tg-name --interpreter "$PWD/.venv/bin/python" --cwd "$PWD"
pm2 save
```

- Xem log: `pm2 logs tg-name`.
- Khởi động lại sau khi sửa cấu hình: `pm2 restart tg-name`.
- Dừng: `pm2 stop tg-name`.

Gửi `.updatecheck` trên Userbot hoặc `/updatecheck` cho Helper Bot để cập nhật code.
Bot kiểm tra nhánh **main** của https://github.com/thinhzero/tg-name. Nếu có bản mới,
bot clone tạm, kiểm tra cú pháp Python, cài thư viện nếu `requirements.txt` thay đổi,
cập nhật fast-forward rồi tự restart. Không có bản mới thì không restart.

`.env`, `name.txt`, session và remote `origin` được giữ nguyên. Nếu code đã sửa cục bộ,
có commit riêng hoặc file mới trùng file của bạn, bot dừng cập nhật thay vì ghi đè.
Hãy lưu/giải quyết các sửa đổi đó thủ công; **không cần `git reset --hard`**.
Tải/cài lỗi sẽ không restart; pip có thể đã thay đổi một phần thư viện trước khi báo lỗi.
Máy cần Git, quyền ghi repo và quyền cài thư viện trong virtualenv.

Nếu bản cũ chưa có `.updatecheck`: dừng bot, chạy `git pull --ff-only` và
`python -m pip install -r requirements.txt`, rồi khởi động lại bằng cách bạn đang dùng.
Repo này công khai nên chức năng cập nhật **không cần GitHub token**.

## 6. Khi gặp lỗi

| Triệu chứng | Cách xử lý |
| --- | --- |
| Thiếu API_ID/API_HASH | Nếu đã có token + admin: mở bot và /start để nhập API. Nếu không dùng Helper Bot: cấu hình bằng setup.py |
| Chưa đăng nhập / session hết hạn | Chạy lại bước đăng nhập trong `setup.py` |
| Helper Bot báo thiếu ADMIN_ID | Điền ID số của bạn; bot không cấp admin cho người nhắn đầu tiên |
| `.status` không trả lời | Dùng chính tài khoản đã đăng nhập, kiểm tra tiến trình còn chạy |
| Thiếu module Python | Kích hoạt `.venv`, cài lại `requirements.txt`, dùng đúng interpreter của PM2 |
| Tên/bio bị cắt | Rút ngắn mẫu hoặc random; xem `.preview` / `.previewbio` |
| Báo FloodWait | Chờ đúng thời gian Telegram yêu cầu; không spam `.update` hoặc chạy nhiều bản |
| Nhạc không hiện | Kiểm tra username, API key riêng và scrobbler Last.fm |
| `.updatecheck` bị từ chối | Xem sửa đổi bằng `git status` / `git diff`; sao lưu rồi xử lý thủ công |

## 7. Bảo mật và kiểm thử

- `.gitignore` chặn `.env`/bản sao env, session, `name.txt`, virtualenv, log và cache.
  Trước khi commit vẫn nên kiểm tra `git status` và `git diff --cached`.
- API hash/key từng được ghi cứng trong các commit cũ. Bản hiện tại đã bỏ chúng;
  **xóa khỏi bản mới không xóa khỏi lịch sử Git**. Nếu là key của bạn, hãy đổi/thu hồi.
- Nếu session Telegram lộ: vào **Settings → Devices** để chấm dứt phiên tương ứng.
  Nếu bot token hoặc token GitHub lộ: thu hồi tại dịch vụ cấp token, không chỉ xóa file.
- Không đăng log có key/OTP/session. Helper Bot không hiển thị lại API hash/key đã lưu.

Kiểm thử không cần đăng nhập Telegram hay gọi GitHub thật:

```bash
python -m unittest discover -s tests -v
```

`name.py` là file chạy chính; `setup.py` là wizard. `generate_session.py` là lựa chọn phụ
để đăng nhập và lưu session vào `.env` mà không in session ra terminal. Các file `*_engine`,
`*_state`, `helper_bot.py`, `bot_updater.py`, `random_names.py`, `i18n.py` là module của bot,
không cần chạy từng file riêng.
