# Chọn lọc tiện ích từ source sth

Không import/chạy source cũ, không copy cấu hình, session, cookie, key, downloads hoặc cache.
Chỉ tham khảo ý tưởng và giao diện lệnh; triển khai lại trên kiến trúc hiện tại.

## Nhóm đầu đã chuyển

| Source cũ | Bản hiện tại | Thay đổi chính |
| --- | --- | --- |
| `.ip` | Đã bỏ | Không đăng ký command/menu hoặc gọi dịch vụ tra IP. |
| `.speed`, `.speedtest` | `.speedtest`, `.speetest`, `.sp`, `.speed` và alias `/` | Subprocess hủy được, timeout 120s, giữ kiểm tra TLS; chỉ whitelist kết quả, không share và luôn ẩn IP. |
| `.whois` | `.whois`, `/whois` | RDAP thay cho scrape HTML; IDNA, giới hạn dữ liệu, không hiện contact cá nhân. |
| `.l`, download/upload | `.l`, `/l` | Streaming có giới hạn; temp riêng cho từng tác vụ, tên file an toàn, dọn cả khi lỗi/hủy. |
| progress | `TransferProgress` | Trạng thái riêng từng tác vụ, throttle, không dùng đối số mặc định mutable hoặc tạo task cho từng chunk. |
| `.cancel` | `.cancel`, `/cancel` | Hủy được cả tải và upload; ràng buộc owner/chat/transport, dừng hoàn toàn khi shutdown. |

HTTP công khai dùng chung một bộ lọc URL/DNS/redirect, giữ xác thực TLS, không dùng proxy
từ environment. Không resolve một lần để kiểm tra rồi để connector resolve lại. Chặn cả
IP viết kiểu số nguyên/rút gọn có thể bỏ qua resolver của aiohttp. Không trả URL ký số,
body lỗi của dịch vụ hoặc exception chứa thông tin bí mật vào chat.

## Không mang nguyên sang

- `.ping` và AFK: bản hiện tại đã có và đã sửa; source cũ đăng ký ping hai lần và phụ thuộc
  `ping3`/raw socket. Không thêm handler trùng hoặc lùi mặc định tự xóa AFK về 5 giây.
- `.music`: source cũ dùng tìm/tải YouTube và polling API không có giới hạn; tên lệnh hiện
  dành cho Last.fm. Nếu bổ sung sau sẽ dùng tên riêng, timeout và tác vụ hủy thực sự.
- YouTube: chưa mang job thread không hủy được hoặc tùy chọn tắt kiểm tra chứng chỉ sang.
- Speedtest: không giữ `results.share()`/ảnh chia sẻ từ source cũ; dùng `speedtest-cli` đã kê
  trong requirements, subprocess qua runner có giới hạn và kill/reap khi hủy.
- Pixeldrain: không đem key/cookie/link bypass cũ sang, không đăng ký `.up`/`/up` theo yêu cầu.
- Quote và plugin ảnh/API ngoài: cần kiểm tra lại dịch vụ, dữ liệu gửi cho bên thứ ba và
  kích thước phản hồi trước khi tích hợp. Quote cũ còn đưa bytes avatar thẳng vào JSON.
- `drgen.py`: phụ thuộc module `bot.*` của dự án khác, nhiều host/API cũ; không kéo toàn bộ
  dependency hay logic bypass vào bot chỉ để dùng một hai host.
- Cấp quyền `.a`/đặt key `.api`/gửi lặp `.send`: không mở rộng quyền admin, lộ key trên chat
  hoặc thêm gửi lặp hàng loạt chỉ vì có trong source cũ.

Kiểm thử nhóm này dùng HTTP/Telegram giả lập: input, TLS/redirect, DNS, giới hạn file,
timeout, cancel, cleanup, progress, quyền admin và panel Home; không đăng nhập tài khoản
hoặc gửi file thật để chạy test.
