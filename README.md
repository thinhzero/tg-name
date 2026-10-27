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

### Chạy nhanh — chỉ cần `python name.py`

```bash
git clone https://github.com/thinhzero/tg-name.git
cd tg-name
python name.py
```

Nếu máy chỉ có lệnh `python3`, dùng `python3 name.py`. Script kiểm tra thư viện **trước khi
import Telegram**, tự cài đầy đủ từ `requirements.txt` nếu thiếu. Khi đang ở Python hệ thống,
script tạo/tái sử dụng `.venv` rồi chuyển sang Python trong đó, không ép sửa Python hệ thống.
Nếu đang trong virtualenv thì cài vào chính môi trường đó. Cần mạng và quyền ghi thư mục;
nếu thiếu công cụ tạo venv trên Ubuntu/Debian, cài `python3-venv` rồi chạy lại.

Lần đầu chưa có cấu hình, script chỉ hỏi **BOT_TOKEN (ẩn)** và **ADMIN_ID**. Nếu đã có hai
giá trị trong `.env` thì không hỏi lại. Sau đó mở bot, nhấn **Start** để nhập API và đăng nhập
Telethon trong chat. Không cần nhập SĐT/OTP/2FA ở VPS. Chạy bằng PM2/không có terminal tương
tác thì cần điền sẵn hai giá trị trong `.env`.

Nếu dùng cách chạy nhanh này, **bỏ qua các bước cài thủ công bên dưới** và chuyển tới phần
lệnh Telegram. Những bước dưới là lựa chọn cho người muốn tự cấu hình/môi trường Python.

### Android / Termux

Trong Termux, cài các công cụ cần thiết:

```bash
pkg install python python-pip python-ensurepip-wheels git bash
```

Cài mới theo phần chạy nhanh ở trên, trong thư mục **`$HOME` của Termux**. Với repo đã có,
chỉ vào đúng thư mục đó và chạy `python name.py`; không cần clone lại hay nhập lại token.
Tránh đặt repo/`.venv` trong `/sdcard` hoặc `/storage/emulated/0`: bộ nhớ dùng chung có thể
chặn thực thi, symlink và khiến Git báo `dubious ownership`.

`/shell` tìm `bash`/`sh` trong `$PATH`, nên dùng được đường dẫn `$PREFIX/bin` của Termux.
Các lệnh như `fastfetch` cần cài bằng `pkg` nếu chưa có. Bot vẫn chỉ nhận lệnh của admin
trong chat riêng; giới hạn thời gian và output giống Linux.

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
| Cài đặt trực quan | — | `/settings` |
| Reset, chỉ giữ BOT_TOKEN + ADMIN_ID | — | `/reset` (cần xác nhận) |
| Trạng thái | `.status` | `/status` hoặc `/start` |
| Xem trước tên và bio | `.preview` | `/preview` |
| Cập nhật tên/bio ngay | `.update` | `/update` |
| Tạm dừng / tiếp tục | `.pause` / `.resume` | `/pause` / `/resume` |
| Vắng mặt / trở lại | `.afk [lý do]` / `.on` | `/afk [lý do]` / `/on` |
| Ping và uptime | `.ping [host]` | `/ping [host]` |
| Về Home nhanh | — | `/home` hoặc nút **🏠 Home** |
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
| Kiểm tra code, hỏi trước khi cập nhật | `.updatecheck` | `/updatecheck` |
| Chạy lệnh Linux | — | `/shell uptime` hoặc `/shell lệnh` (chỉ admin) |

Trên Helper Bot, `/cancel` hủy thao tác nhập đang dang dở. Đăng nhập qua terminal được
khuyến nghị; nếu dùng wizard đăng nhập qua chat, không chuyển tiếp OTP/2FA và xóa tin nhắn
nhạy cảm sau khi hoàn tất. Không gửi token/API key trong nhóm hoặc ảnh chụp màn hình.

### AFK, online và ping

```text
.afk đi ngủ
.on
.ping
.ping example.com
```

`.afk` bật vắng mặt: khi có người mention hoặc reply tin của bạn, Userbot trả lý do và thời
gian AFK. Mỗi người trong mỗi chat được trả lời tối đa một lần mỗi 60 giây; tin trả lời
gửi im lặng và cố tự xóa sau 5 giây. Tin thường không mention/reply, tin từ bot và tin của chính
bạn không kích hoạt. `.on` tắt AFK và xóa chính tin lệnh; không đổi trạng thái online Telegram.
AFK chỉ lưu trong lần chạy hiện tại, không tự thay tên/bio hay tạm dừng Profile Updater.

`.ping` sửa chính tin lệnh để hiện độ trễ gửi/sửa tin qua Telegram và uptime của tiến trình.
Thêm hostname/IP để chạy một gói ping hệ thống (timeout 5 giây), không dùng raw socket hay
thư viện `ping3`. Trên Termux, nếu chưa có lệnh ping: `pkg install iputils`.
Helper Bot nhận `/afk`, `/on`, `/ping` từ admin; bật AFK cần Userbot đang chạy.

### Helper Bot ít thông báo

Menu, wizard nhập cấu hình, xem trước và tiến trình cập nhật ưu tiên **sửa
cùng một tin nhắn của bot**. Tin đầu tiên, hoặc khi tin cũ đã bị xóa/không sửa được, được gửi
mới ở chế độ im lặng. Sau khi restart bot có thể tạo một panel mới; không sửa tin của bạn.
Danh sách random dài có nút chuyển trang thay vì đẩy nhiều tin nối tiếp.

Riêng **`/shell` trả một tin kết quả mới cho mỗi lần gọi**, không sửa panel hay kết quả lệnh
trước đó. Kết quả gửi im lặng, vẫn giữ lịch sử từng lệnh, kể cả khi bạn đã quay về Home.

Gõ **`/`** trong chat riêng với bot để xem danh sách lệnh và mô tả. Bot tự đăng ký gợi ý cho
đúng chat `ADMIN_ID` khi khởi động, gửi `/start` và khi đổi ngôn ngữ. Trước bước nhập API,
menu chỉ hiện các lệnh đã dùng được trong chế độ khởi tạo. Nếu Telegram chưa cập nhật danh
sách ngay, mở lại chat hoặc gửi `/start`; gợi ý không thay đổi quyền admin của các lệnh.

Mỗi màn hình có **🏠 Home**; bấm để hủy bước nhập đang chờ, đóng phiên đăng nhập tạm và về
bảng điều khiển. `/home` hoặc `/start` cũng mở lại giao diện. Tin chứa OTP/API hash/mật khẩu
vẫn được cố xóa riêng; kết quả tác vụ cũ không ghi đè màn hình Home vừa mở.

### Nút cập nhật và lệnh Linux / Termux

Bấm **🔎 Kiểm tra cập nhật** ở menu chính hoặc **Cài đặt**: hành vi giống `/updatecheck`.
Có bản mới thì báo **số commit mới hơn** và hỏi **✅ Có, cập nhật / ❌ Không**. Chưa bấm Có
thì không clone, cài thư viện, tạo snapshot hay thay code; đã mới nhất thì chỉ báo commit.
Nút này và `/updatecheck` cũng có ở màn hình khởi tạo khi chưa nhập API.

Trên Linux hoặc Termux, admin nhắn riêng với bot:

```text
/shell uptime
/shell {uptime}
/shell ls -la
/shell fastfetch
/shell df -h | head
```

Hai dòng đầu đều chạy `uptime`. Với `/shell lệnh`, bot chạy lệnh shell tại thư mục repo,
trả stdout + stderr và exit code. Hỗ trợ lệnh có tham số/pipeline; không có stdin tương tác.
Không giới hạn vào `uptime`: chạy lệnh có sẵn trên máy (`fastfetch` cần được cài trước).
Mỗi lúc chỉ chạy một lệnh, timeout 30 giây; dừng nhóm tiến trình khi timeout/hủy hoặc output
vượt 64 KiB. Kết quả gửi Telegram được rút gọn để không vượt giới hạn tin nhắn.

**Đây là quyền chạy lệnh thật với quyền của tiến trình bot, không phải sandbox.** Không chạy
bot bằng root; không đưa quyền admin/token cho người khác. Bot bỏ các biến môi trường nhạy
cảm khỏi tiến trình con và cố che key/token đã biết trong kết quả, nhưng không thể bảo đảm
che được dữ liệu bí mật đã mã hóa/biến đổi. Không dùng lệnh in `.env`, session hay private key
vào chat. `/shell` chỉ chấp nhận đúng `ADMIN_ID`, chat riêng, và chỉ trên Linux/Termux; cũng dùng được
ở màn hình khởi tạo trước khi nhập API. Không tự chạy lệnh của người khác hoặc output có sẵn.

### Cài đặt bằng nút bấm và `/reset`

Mở **Cài đặt** hoặc gửi `/settings`: có các nút đăng nhập, API Telegram, tên, thành phố,
múi giờ, mẫu tên/bio, ngôn ngữ, thời tiết, username/key Last.fm, quản lý random và **Đặt lại cấu hình**.
Trong mục Random, bấm **Thêm random**, chọn trang bằng mũi tên hoặc bấm nút thùng rác cạnh
một mục và xác nhận để xóa; không cần nhớ lệnh/UID.

Muốn làm lại từ đầu, admin gửi `/reset` hoặc bấm **Đặt lại cấu hình → Xác nhận reset**:

- Chỉ admin đã cấu hình, trong chat riêng, mới được reset. Không xóa gì nếu chưa xác nhận.
  Nút xác nhận dùng một lần, hết hạn sau 5 phút; bấm **Hủy** để giữ cấu hình.
- Bot dừng cập nhật profile, đóng kết nối rồi đặt lại `.env` chỉ còn đúng **hai khóa**:
  `BOT_TOKEN` và `ADMIN_ID`, với giá trị hiện tại. Xóa cả API/key cũ, session string, thiết
  lập tên/bio và các biến cũ trong `.env`; không tạo bản sao chứa key cũ.
- Dọn các file session cục bộ `bot.session`, `helper_bot_session.session`, session đang
  cấu hình và journal/wal/shm của chúng trong repo. Không xóa symlink/session ngoài repo,
  không xóa code hoặc `name.txt`. Nếu có file ngoài repo hay lỗi quyền dọn file, kiểm tra
  thủ công; không xem reset là cách thu hồi mọi bản sao session.
- Bot tự restart vào màn hình cài đặt: nhập lại API riêng và đăng nhập Telegram bằng nút.
  `/reset` cũng dùng được ở màn hình khởi tạo khi chưa có API.
- Reset chỉ xóa cấu hình/phiên **trên máy chạy bot**, không xóa lịch sử chat, không thu hồi
  API key/token tại dịch vụ cấp key hay chấm dứt mọi phiên Telegram từ xa.

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

Gửi `.updatecheck` trên Userbot hoặc `/updatecheck` cho Helper Bot để **kiểm tra trước**.
Bot so sánh với nhánh **main** của https://github.com/thinhzero/tg-name, fetch lịch sử Git
để đếm chính xác số commit nhưng **không clone/checkout, cài thư viện hay đổi code** ở bước này.

- Có bản mới: hiện số commit và commit đích, hỏi **✅ Có, cập nhật / ❌ Không** trong cùng panel.
- Chọn **Không**, về Home hoặc không xác nhận: không áp dụng cập nhật. Xác nhận hết hạn sau 5 phút,
  dùng một lần, gắn với admin và bản bot nhận yêu cầu; không khóa/chặn các bản bot khác đang test.
- Chỉ sau khi chọn **Có**: clone tạm, kiểm tra mã Python, tạo snapshot code hiện tại, cài thư viện
  nếu cần, cập nhật fast-forward **đúng commit đã xác nhận**, rồi tự restart bản đang xử lý.
- Trên Userbot (không gửi được nút inline), tin kết quả có lệnh `.updateconfirm TOKEN` và
  `.updatecancel TOKEN`; dùng đúng mã bot trả về, không phải token đăng nhập Telegram/GitHub.

Snapshot nằm tại **`snapshots/<thời-gian-UTC>-<commit-cũ>-<mã>/`** trong thư mục bot:

- `code/` chứa các file source/text được Git theo dõi và source mới chưa commit, không lấy file bị ignore.
- `snapshot.json` ghi commit trước/sau, danh sách file và file đã che/bỏ qua; không chứa giá trị key.
- Không sao chép `.git`, `.env` thật/bản sao, session, khóa riêng, database, archive/binary, virtualenv,
  cache, log, `name.txt` cá nhân hay các snapshot cũ. Các literal token/API/session trong source
  được nhận diện và key đã biết được che; snapshot không phải bản sao cấu hình/đăng nhập.
- Snapshot được tạo **trước khi cài thư viện/thay code**, vẫn còn sau cập nhật hoặc nếu bước sau lỗi.
  Không tạo được snapshot thì dừng. Thư mục này được Git ignore, không tự push hay tự xóa bản cũ.
- Khi phục hồi thủ công, chỉ lấy source cần thiết từ `code/`, giữ `.env`/session hiện tại; xem trường
  `redacted` trong `snapshot.json` nếu source cũ có literal khóa cần nhập lại.

`.env`, `name.txt`, session và remote `origin` được giữ nguyên. Nếu code đã sửa cục bộ,
có commit riêng hoặc file mới trùng file của bạn, bot dừng cập nhật thay vì ghi đè.
Hãy lưu/giải quyết các sửa đổi đó thủ công; **không cần `git reset --hard`**.
Tải/cài lỗi sẽ không restart; pip có thể đã thay đổi một phần thư viện trước khi báo lỗi.
Máy cần Git, quyền ghi repo và quyền cài thư viện trong virtualenv.
Bot kiểm tra chính thư mục chứa mã nguồn, không phụ thuộc thư mục terminal hay biến `GIT_DIR`
được kế thừa. Lỗi thiếu `.git`, chạy trong repo cha và quyền sở hữu Git có thông báo riêng;
không tự đổi `safe.directory`, xóa file hay bắt chuyển `.env`/session sang clone khác.

Nếu bản cũ chưa có `.updatecheck`: dừng bot, chạy `git pull --ff-only` và
`python -m pip install -r requirements.txt`, rồi khởi động lại bằng cách bạn đang dùng.
Repo này công khai nên chức năng cập nhật **không cần GitHub token**.
