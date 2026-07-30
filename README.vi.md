# Duyệt Dịch (悦翻译 / YueTranslate)

[简体中文](README.md) | [English](README.en.md) | **Tiếng Việt**

> Mini Program WeChat phiên dịch song song Trung–Việt + dịch vụ backend dịch thời gian thực
>
> Công cụ dịch thuật công ích, tiện dân cho các tình huống xuyên biên giới Trung–Việt: phiên dịch song song thời gian thực vừa nói vừa dịch, hội thoại mặt đối mặt hai micro, dịch qua ảnh chụp, dịch văn bản, cùng danh bạ kết nối phiên dịch viên / cơ hội kinh doanh hoàn toàn miễn phí.

## 📲 Quét mã trải nghiệm

<img src="assets/qrcode-miniprogram.jpg" alt="Mã QR Mini Program Duyệt Dịch" width="200"/>

Mở WeChat, quét mã QR bên trên để trải nghiệm Mini Program Duyệt Dịch.

## ✨ Tổng quan tính năng

### Năng lực dịch thuật (trang "Phiên dịch" trong Mini Program, 4 chế độ chuyển đổi nội tuyến)

| Chế độ | Mô tả | Chi phí |
|--------|-------|---------|
| 🎙️ **Phiên dịch song song** | Dịch đồng thời theo thời gian thực: vừa nói vừa hiện bản dịch, dựa trên đường truyền streaming WebSocket | Miễn phí 30 phút mỗi ngày, vượt hạn mức có thể mua gói giọng nói |
| 🗣️ **Mặt đối mặt** | Hai micro, mỗi người một câu: hai người mỗi bên giữ micro của mình để nói (PTT), phía đối diện hiển thị bản dịch xoay ngược 180°, phù hợp giao tiếp trực tiếp | Như trên (dùng chung đường truyền phiên dịch) |
| 📷 **Dịch qua ảnh** | Chụp/chọn ảnh, nhận diện và dịch chữ trong ảnh (mô hình thị giác lớn) | Miễn phí (chỉ giới hạn tần suất chống lạm dụng) |
| ✍️ **Dịch văn bản** | Nhập văn bản, dịch tức thì hai chiều | Miễn phí (chỉ giới hạn tần suất chống lạm dụng) |

### Danh bạ tiện dân (công ích, miễn phí)

- 🔍 **Tìm phiên dịch**: phiên dịch viên / công ty dịch thuật đăng ký miễn phí; hỗ trợ 59 ngôn ngữ, hai loại dịch vụ phiên dịch / biên dịch, lọc đa lựa chọn theo 20 lĩnh vực chuyên môn
- 💼 **Tìm việc dịch**: đăng nhu cầu dịch thuật, tự động ghép nối và đẩy đến phiên dịch viên phù hợp theo Ngôn ngữ ∩ Dịch vụ ∩ Lĩnh vực
- 📚 **Câu thông dụng**: kho câu Trung–Việt thông dụng kèm phát âm, bao phủ các tình huống tần suất cao như đi lại, lưu trú, thương mại

### Nguyên tắc sản phẩm

- Không thu số điện thoại, không thu hộ phí dịch thuật; phiên dịch viên đăng ký miễn phí vĩnh viễn
- Chỉ tính phí khi phiên dịch song song vượt hạn mức miễn phí hàng ngày (gói giọng nói ¥9.9 / ¥19.9 / ¥49.9 tương ứng 60 / 200 / 600 phút, mua một lần dùng lâu dài)

## 🛠️ Công nghệ sử dụng

| Tầng | Công nghệ |
|------|-----------|
| Frontend Mini Program | WeChat Mini Program nguyên bản (WXML / WXSS / JS), bố cục 5 tab |
| Framework backend | Python 3.13 + FastAPI + Uvicorn |
| Phiên dịch thời gian thực | Proxy WebSocket → Alibaba Cloud DashScope `qwen3.5-livetranslate-flash-realtime` |
| Dịch qua ảnh | `qwen-vl-plus` (hiểu thị giác) |
| Dịch văn bản | `qwen-plus` |
| Cơ sở dữ liệu | PostgreSQL (production) / SQLite (phát triển cục bộ), SQLAlchemy 2.0 |
| Cache / giới hạn tần suất | Redis (production) / fakeredis (phát triển cục bộ) |
| Xác thực | Đăng nhập WeChat openid + JWT; trang quản trị có mã xác nhận hình ảnh |
| Thanh toán | Thanh toán ảo WeChat (gói giọng nói) |
| Triển khai | Docker Compose (app + postgres + redis) |

## 📁 Cấu trúc thư mục

```
vi-translate/
├── miniprogram/                  # Frontend Mini Program WeChat (mở thư mục này trong DevTools)
│   ├── app.{js,json,wxss}        # Cấu hình toàn cục (5 tab: Phiên dịch / Tìm phiên dịch / Tìm việc / Câu thông dụng / Tôi)
│   ├── pages/
│   │   ├── index/                # Trang chính (Phiên dịch / Mặt đối mặt / Ảnh / Văn bản — 4 chế độ nội tuyến)
│   │   ├── services/             # Tìm phiên dịch (danh bạ + bộ lọc)
│   │   ├── translator-detail/    #   └─ Chi tiết phiên dịch viên
│   │   ├── translator-edit/      #   └─ Đăng ký / chỉnh sửa hồ sơ phiên dịch viên
│   │   ├── business-publish/     # Tìm việc dịch (đăng nhu cầu dịch thuật)
│   │   ├── matched-needs/        #   └─ Nhu cầu được ghép với tôi
│   │   ├── my-needs/             #   └─ Nhu cầu tôi đã đăng
│   │   ├── ask/                  # Câu thông dụng (câu theo danh mục + giọng đọc)
│   │   ├── profile/              # Tôi (ID người dùng / hạn mức / cài đặt)
│   │   ├── pricing/ pay/         # Mua gói giọng nói
│   │   ├── history/              # Lịch sử dịch
│   │   └── face/                 # Trang Mặt đối mặt độc lập (dự phòng; lối vào chính đã gộp vào index)
│   ├── utils/
│   │   ├── live.js               # Client WebSocket phiên dịch (connect/finish/stop)
│   │   ├── recorder.js           # Ghi âm PCM
│   │   └── ...
│   └── components/               # Component dùng chung
│
├── live-translate/               # Dịch vụ backend (FastAPI)
│   ├── app/
│   │   ├── main.py               # Điểm khởi chạy ứng dụng
│   │   ├── config.py             # Cấu hình (hạn mức miễn phí / giới hạn tần suất, v.v.)
│   │   ├── models.py             # Mô hình SQLAlchemy
│   │   ├── translate/proxy.py    # Proxy WebSocket phiên dịch thời gian thực (lõi)
│   │   ├── photo/                # API dịch qua ảnh + dịch văn bản
│   │   ├── directory/            # Danh bạ tìm phiên dịch / tìm việc (danh mục chuẩn ngôn ngữ/lĩnh vực trong catalog.py)
│   │   ├── auth/                 # Đăng nhập WeChat / JWT / SMS
│   │   ├── billing/              # Hạn mức và gói giọng nói
│   │   ├── payments/             # Thanh toán ảo WeChat
│   │   ├── admin/                # API quản trị
│   │   └── sessions/ security/   # Phiên và bảo mật
│   ├── migrations/               # Script migration SQL
│   ├── static/                   # Trang quản trị / audio câu thông dụng và tài nguyên tĩnh khác
│   ├── tests/                    # Bộ test pytest
│   ├── deploy/                   # Script triển khai Docker Compose
│   ├── requirements.txt
│   ├── run.ps1                   # Khởi chạy nhanh cục bộ trên Windows
│   └── .env.example              # Mẫu biến môi trường
│
└── README.md
```

## 🚀 Cách chạy

### 1. Backend (phát triển cục bộ)

Chế độ cục bộ dùng SQLite + fakeredis, không cần Docker / PostgreSQL / Redis.

```bash
cd live-translate

# 1. Tạo môi trường ảo (Python 3.13)
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 2. Cài đặt phụ thuộc
pip install -r requirements.txt

# 3. Cấu hình biến môi trường
cp .env.example .env
# Sửa .env, tối thiểu điền DASHSCOPE_API_KEY (đăng ký tại https://dashscope.console.aliyun.com/apiKey)

# 4. Khởi chạy
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Trên Windows cũng có thể chạy: .\run.ps1
```

Sau khi khởi chạy, truy cập `http://127.0.0.1:8000/healthz` sẽ trả về ok.

### 2. Backend (triển khai production)

```bash
cd live-translate/deploy
cp ../.env.example .env   # Điền cấu hình production (setup.sh tự sinh mật khẩu/khóa ngẫu nhiên mạnh)
./setup.sh                # Triển khai lần đầu: khởi động app + postgres + redis
./update.sh               # Cập nhật sau này: build lại và khởi động lại
```

### 3. Frontend Mini Program

1. Mở **WeChat DevTools**, import dự án, chọn thư mục `miniprogram/`
2. Điền AppID Mini Program của bạn (hoặc chọn "tài khoản test" để trải nghiệm)
3. Sửa địa chỉ backend trong `miniprogram/utils/` thành tên miền bạn đã triển khai (production cần cấu hình tên miền hợp lệ request/socket trên WeChat Official Platform, bắt buộc HTTPS / WSS)
4. Biên dịch và chạy trong trình mô phỏng; xem trước trên máy thật cần quét mã QR

### Biến môi trường quan trọng

| Biến | Mô tả |
|------|-------|
| `DASHSCOPE_API_KEY` | API Key DashScope của Alibaba Cloud (bắt buộc; dùng chung cho phiên dịch/ảnh/văn bản) |
| `TRANSLATE_MODEL` | Mô hình phiên dịch, mặc định `qwen3.5-livetranslate-flash-realtime` |
| `DATABASE_URL` | Chuỗi kết nối PostgreSQL (cục bộ có thể bỏ trống, tự dùng SQLite) |
| `REDIS_URL` | Chuỗi kết nối Redis (cục bộ có thể bỏ trống, tự dùng fakeredis) |
| `JWT_SECRET` | Khóa ký JWT (production phải là chuỗi ngẫu nhiên mạnh) |
| `DIRECTORY_CONTACT_KEY` | Khóa Fernet mã hóa thông tin liên hệ phiên dịch viên |
| `FREE_DAILY_MINUTES` | Số phút phiên dịch miễn phí mỗi ngày, mặc định 30 |

Danh sách đầy đủ xem tại [`live-translate/.env.example`](live-translate/.env.example).

## 🧪 Kiểm thử

```bash
cd live-translate
pytest tests/
```

## 📄 Giấy phép

Bản quyền © Yuexun Translation (Duyệt Tấn). Mã nguồn công khai để học tập và tham khảo; sử dụng thương mại vui lòng liên hệ tác giả.

---

*Duyệt Dịch — để giao tiếp Trung–Việt không còn rào cản ngôn ngữ.*
