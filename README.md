# data-collection — catalog du lịch cho V-OTA RecSys

Thu thập sản phẩm du lịch thật từ **Vinpearl** (khách sạn, hạng phòng, vé VinWonders, tour, combo, golf)
và **booking.com** (toàn bộ chỗ ở tại Việt Nam cùng hạng phòng, và vé tham quan). Đầu ra đúng schema
`Product` ở §6 của handbook.

Chỉ lấy dữ liệu sản phẩm. Không lấy review, tên người đánh giá hay bất cứ thông tin nào về từng khách;
chỉ giữ điểm đánh giá trung bình và số lượt đánh giá.

## Cài đặt

Cần Python 3.10 trở lên (đã chạy thử trên 3.14) và khoảng 2–3 GB ổ đĩa nếu crawl toàn bộ.

```bash
cd data-collection
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium        # Linux thiếu thư viện hệ thống: playwright install --with-deps chromium
```

## Chạy

```bash
python crawl.py vinpearl               # ~20–25 phút: 15 khách sạn, ~120 hạng phòng, ~380 vé/tour/combo/golf
python crawl.py booking-hotels         # ~34.000 chỗ ở; dừng/chạy lại thoải mái
python crawl.py booking-attractions    # ~13.500 vé tham quan (nguồn phụ)
python normalise.py                    # → data/products.jsonl, products.csv, stats.md, dedup_report.csv
```

Chạy thử trước khi chạy lớn:

```bash
python crawl.py vinpearl --tour-limit 10
python crawl.py booking-hotels --limit 20
python crawl.py booking-attractions --limit 10
python normalise.py && head -60 data/stats.md
```

Tiến độ và dừng/chạy tiếp:

```bash
python crawl.py status                          # đã xong / còn lại / lỗi theo từng nguồn
python crawl.py retry-failed booking-hotels     # đưa URL lỗi về hàng đợi
python crawl.py reparse booking-hotels          # sửa parser xong thì parse lại từ cache, không tải lại
```

Ctrl+C lúc nào cũng được. Mỗi trang xong là ghi ngay vào `data/state/crawl_state.sqlite`, nên chạy lại
đúng lệnh cũ sẽ tiếp tục từ chỗ dừng.

### Vì sao mặc định mở cửa sổ trình duyệt

Cả hai website đều có lớp chống bot. Script dùng Chromium thật qua Playwright và **không** dùng bất kỳ
kỹ thuật che giấu nào: không stealth plugin, không giả fingerprint, không proxy, không giải CAPTCHA.
Kết quả chạy thử (15/09/2026):

| | Có cửa sổ (mặc định) | `--headless` |
|---|---|---|
| API khách sạn Vinpearl | chạy (HTTP thường, không cần trình duyệt) | chạy |
| API tour/vé Vinpearl | chạy | **bị Cloudflare chặn** |
| booking.com: tên, mô tả, toạ độ, tiện nghi, hạng phòng | chạy | chạy |
| booking.com: **giá** theo hạng phòng | chạy | **không có giá**: booking.com trả bản trang không kèm ngày |
| booking.com attractions | chạy | chạy |

Máy không có màn hình (server) thì dùng `--headless` và chấp nhận thiếu giá booking.com cũng như tour Vinpearl.
Nếu cửa sổ hiện ô "Xác minh bạn là con người", **bạn tự bấm** trong cửa sổ đó; script chờ tối đa
`--manual-wait` giây (mặc định 300). Cookie được lưu trong `data/browser-profile/`, nên thường chỉ phải làm một lần.

Có thể dùng Google Chrome đã cài sẵn thay cho Chromium: `--browser-channel chrome`.

### Tốc độ và mức lịch sự

- Tối thiểu `--delay` giây giữa hai request tới cùng một host: Vinpearl 2 giây, booking.com 3 giây, cộng ngẫu nhiên thêm tới 35%.
- Tôn trọng `robots.txt` (có hỗ trợ wildcard và `Crawl-delay`).
- Bị chặn liên tiếp thì nghỉ tăng dần (1 → 2 → 4… phút). Sau `--max-blocks` lần liên tiếp (mặc định 8) thì
  **tự dừng**, tiến độ được giữ lại. Nghỉ vài giờ rồi chạy lại, có thể tăng `--delay`.
- Không tải ảnh, font, video (chỉ lưu URL ảnh), nên nhẹ cho cả hai phía.

Tốc độ đo được khi chạy thử booking-hotels (chế độ có cửa sổ, `--delay 3`):

| Cấu hình | Trang/phút | Toàn bộ ~33.700 chỗ ở |
|---|---|---|
| mặc định, 1 tab | 6 | ~4 ngày |
| mặc định, 3 tab | 8,6 | ~2,7 ngày |
| `--fast`, 3 tab | 16,4 | **~1,5 ngày** |

`--fast` không chờ trang tải xong và chặn CSS cùng tracker quảng cáo. Dữ liệu cần lấy đã có sẵn trong HTML
server trả về, nên kết quả parse giống hệt chế độ thường (đã đối chiếu). booking-attractions (~13.500 URL)
chạy khoảng 10 trang/phút với 1 tab ở chế độ thường.

`--concurrency` mở thêm tab nhưng vẫn chung giới hạn `--delay`. Nếu log bắt đầu báo bị chặn, hãy giảm lại.
Có thể ưu tiên điểm đến bằng `--match`, ví dụ `--match 'nha-trang|phu-quoc|ha-long|hoi-an|da-nang'`;
khách sạn có chữ Vinpearl trong URL luôn được crawl trước.

## Chạy số lượng lớn

### Thứ tự ưu tiên Vinpearl

```bash
# 1. Vinpearl: bảng giá phòng mỗi 7 ngày trong 6 tháng tới (15 khách sạn × 26 ngày ≈ 15 phút), cộng toàn bộ vé/tour/combo/golf
python crawl.py vinpearl --price-dates "$(seq -s, 7 7 182)"

# 2. Khách sạn mang thương hiệu Vinpearl trên booking.com, gồm cả những khách sạn không có trong API Vinpearl
#    (dòng Meliá Vinpearl, Landmark 81, Tây Ninh, Thanh Hoá…), kèm giá OTA để so sánh
python crawl.py booking-hotels --fast --match 'vinpearl|vinholidays|vinwonders'

# 3. Điểm đến có Vinpearl trước (đủ dùng cho demo tuần 2)
python crawl.py booking-hotels --fast --concurrency 3 --match 'nha-trang|cam-ranh|phu-quoc|hoi-an|ha-long|cua-lo|ha-tinh|hai-phong|bac-ninh'

# 4. Phần còn lại, để chạy nền nhiều ngày
./run_forever.sh booking-hotels --fast --concurrency 3
./run_forever.sh booking-attractions --fast --concurrency 2

python normalise.py        # chạy được bất cứ lúc nào, kể cả khi crawl còn đang chạy
```

Mỗi bước dùng chung hàng đợi, nên URL đã xong ở bước trước sẽ không bị crawl lại ở bước sau.

### Chạy nhiều ngày không cần canh

- Chạy trong `tmux` hoặc `screen` để tắt terminal hay mất SSH không làm dừng crawl:
  `tmux new -s crawl`, chạy lệnh, rồi `Ctrl+B D` để thoát ra; `tmux attach -t crawl` để vào lại.
- `run_forever.sh` tự chạy tiếp sau khi bị chặn (nghỉ `COOLDOWN_HOURS`, mặc định 3 giờ) hoặc sau lỗi mạng,
  và dừng khi xong.
- Máy chủ không có màn hình mà vẫn cần giá: `sudo apt install xvfb`, rồi
  `xvfb-run -a ./run_forever.sh booking-hotels --fast --concurrency 3`.
- Theo dõi tiến độ: `python crawl.py status` và `tail -f data/logs/crawl-$(date +%Y%m%d).log`.
- Mỗi nguồn chỉ chạy **một tiến trình**; chạy trùng sẽ bị khoá chặn lại. Có thể chạy song song các nguồn khác
  nhau, nhưng `booking-hotels` và `booking-attractions` cùng gọi www.booking.com nên tổng tốc độ cộng dồn:
  mỗi nguồn nên để `--concurrency 2`.

### Giới hạn nên giữ

- `--concurrency` tối đa 3–4 và giữ `--delay` ≥ 3. Tăng nữa thì bị chặn nhiều hơn chứ không nhanh hơn.
- Không dùng proxy xoay IP hay nhiều máy để vượt giới hạn tốc độ: vừa trái điều khoản vừa dễ bị chặn cả dải IP.
  Cần nhanh hơn nữa thì dùng nguồn chính thức (Booking.com Affiliate/Demand API, Amadeus) hoặc xin dữ liệu từ đội Vinpearl.
- Ổ đĩa: khoảng 45 KB mỗi trang cache, tức ~1,5 GB cho toàn bộ khách sạn và ~0,5 GB cho attraction.
  `normalise.py` với toàn bộ dữ liệu cần vài GB RAM.

## Tuỳ chọn hay dùng

| Lệnh | Tuỳ chọn | Ý nghĩa |
|---|---|---|
| mọi lệnh crawl | `--headless` | không mở cửa sổ (xem bảng ở trên) |
| | `--delay 5` | chậm hơn, ít bị chặn hơn |
| | `--fast` | không chờ trang tải xong, chặn CSS/tracker; nhanh gấp đôi, dữ liệu như cũ |
| | `--data-dir /đường/dẫn` | nơi lưu dữ liệu (hoặc biến môi trường `VOTA_DATA_DIR`) |
| `vinpearl` | `--price-dates 30,14,60` | các ngày hỏi giá phòng (số ngày kể từ hôm nay hoặc `YYYY-MM-DD`); hạng phòng hết chỗ ngày này vẫn được lấy từ ngày khác |
| | `--skip-hotels` / `--skip-tours` | chạy riêng một phần, phần kia giữ từ lần trước |
| | `--site-pages` | thêm đoạn giới thiệu và "giá công bố" từ vinpearl.com (có Cloudflare, thường phải tự xác minh) |
| | `--refresh` | bỏ cache, tải lại |
| `booking-hotels` | `--checkin 2026-10-15 --nights 1 --adults 2` | ngày lấy giá (mặc định hôm nay + 30 ngày) |
| `booking-*` | `--limit N`, `--match REGEX` | giới hạn lượt chạy |
| | `--concurrency 3` | số tab song song |
| | `--rediscover` | đọc lại sitemap để thêm sản phẩm mới |
| | `--full-cache` | lưu nguyên HTML (~450 KB/trang) thay vì bản gọn (~45 KB) |
| `normalise.py` | `--vietnamese-only` | chỉ giữ sản phẩm có mô tả tiếng Việt |
| | `--min-description 80` | bỏ sản phẩm có mô tả quá ngắn |
| | `--usd-vnd 26300 --eur-vnd 30500` | tỷ giá khi booking.com không trả VND (thường gặp ở attraction) |
| | `--keep-duplicate-rooms` | giữ hạng phòng booking.com của khách sạn đã ghép với Vinpearl |
| | `--drop-member-variants` | bỏ các bản sao giá thành viên của vé Vinpearl (`[VIN33 - Gold]`, `[Khách hàng đặc biệt]`…); gần trùng sản phẩm gốc, dễ làm loãng gợi ý |

## Cấu trúc thư mục

```
data-collection/
├── crawl.py                    # CLI: vinpearl | booking-hotels | booking-attractions | all | status | reparse | retry-failed
├── normalise.py                # interim → products.jsonl theo schema Product
├── requirements.txt
├── run_forever.sh              # chạy nhiều ngày: tự chạy tiếp sau khi bị chặn / lỗi mạng
└── collectors/
    ├── common.py               # cache raw, trạng thái resume, robots.txt, giới hạn tốc độ, trình duyệt
    ├── vinpearl.py
    ├── booking_base.py         # sitemap → hàng đợi → crawl → reparse
    ├── booking_hotels.py
    ├── booking_attractions.py
    ├── geo.py                  # chuẩn hoá điểm đến (phường/tỉnh/địa danh → Nha Trang, Phú Quốc…)
    └── textutil.py

data/                           # tạo khi chạy (không commit)
├── raw/<nguồn>/                # MỌI response gốc, gzip: HTML, JSON API, sitemap
├── interim/<nguồn>.jsonl       # bản ghi thô đã parse, mỗi nguồn một file
├── state/crawl_state.sqlite    # hàng đợi URL và trạng thái
├── browser-profile/            # cookie trình duyệt (để không phải xác minh lại)
├── logs/
├── products.jsonl              # ← đầu ra chính
├── products.csv
├── dedup_report.csv
└── stats.md
```

## Schema đầu ra

Mỗi dòng trong `products.jsonl` có đúng các trường của schema Product (§6):

```json
{
  "productId": "9d5cd325-a23d-5907-90aa-7286e06d6654",
  "name": "Vinpearl Beachfront Nha Trang - Studio Hướng Biển Giường Đôi",
  "taxonomy": "hotel",
  "destination": "Nha Trang",
  "description": "Với diện tích 42 m², Studio Ocean View 1 Giường Đôi mang phong cách hiện đại…",
  "attributes": { "level": "room", "starRating": 5, "oceanView": true, "familyFriendly": true,
                  "maxOccupancy": 4, "roomSizeM2": 42, "bedType": "01 giường đôi", "parentProductId": "8b60…" },
  "unitPrice": 2540000,
  "currency": "VND",
  "available": true,
  "availableFrom": null,
  "availableTo": null,
  "imageUrl": "https://booking-static.vinpearl.com/room_types/…jpg",
  "sourceRef": "vinpearl:hotel:24386cea-…:room:2c4503be-…"
}
```

- `productId` = UUIDv5 của `sourceRef`: **ổn định giữa các lần chạy**, nên event đã sinh không bị trỏ vào sản phẩm biến mất.
- `taxonomy`: `hotel` (cả cấp khách sạn và cấp hạng phòng), `attraction`, `combo`, `golf`. Hai nguồn này
  **không có `flight`**; cần vé máy bay cho gợi ý chéo ở tuần 3 thì bổ sung từ trip.com hoặc Amadeus (§3).
- Khách sạn được xuất ở hai cấp: `attributes.level = "property"` (khách sạn) và `"room"` (hạng phòng, có
  `parentProductId`). Tên hạng phòng theo mẫu handbook: `"<Khách sạn> - <Hạng phòng>"`.
- Mọi trường không nằm trong schema được đặt trong `attributes`, để không tự thêm field mà CDP thật không có.

### Nguồn của từng trường

| Trường | Vinpearl khách sạn / hạng phòng | Vinpearl vé, tour, combo, golf | booking.com chỗ ở / hạng phòng | booking.com attraction |
|---|---|---|---|---|
| `name` | API `availability/rooms` → `hotel.name`; phòng: `"{khách sạn} - {roomtype.name}"` | `tour.tourName` | JSON-LD `Hotel.name`; phòng: `"{khách sạn} - {tên phòng}"` | `<h1>` |
| `description` | `hotel.description`, `roomtype.description` (HTML → text) | `tourDetail.description` + `highlight` + `extraInfos` | `[data-testid=property-description]`; phòng: **ghép** giường, sức chứa, tiện nghi phòng + mô tả khách sạn (`attributes.descriptionSource`) | nội dung chính, đã bỏ phần huỷ vé, thời lượng và FAQ |
| `taxonomy` | `hotel` | `golf` nếu tên có "golf"; `combo` nếu có "combo", mã `GN`, hoặc là gói nghỉ; còn lại `attraction` | `hotel` | `attraction` (`combo`/`golf` theo tên) |
| `destination` | `geo.py` từ địa chỉ, rồi tên | `geo.py` từ tên, rồi tỉnh | `geo.py` từ breadcrumb thành phố → địa chỉ → tỉnh | `geo.py` từ tên → phụ đề → thành phố trong tiêu đề trang |
| `unitPrice` | giá thấp nhất còn bán, 1 đêm, 2 người lớn, đã gồm thuế, tại ngày đầu trong `--price-dates` | `adultSalePrice` | giá thấp nhất trong bảng phòng, 1 đêm, 2 người lớn, VND | "Giá thấp nhất", quy đổi VND nếu cần (`attributes.priceConverted`) |
| `available` | có ít nhất một gói giá chưa hết phòng | `isEnabled` và chưa quá `saleEndDate` | có giá cho ngày đã hỏi | có giá |
| `availableFrom/To` | — | `saleStartDate` / `saleEndDate` | — | — |
| `imageUrl` | ảnh đầu tiên của `hotel.media` / `roomtype.media` | `thumbImageView` | ảnh gallery (nâng lên 1024px) | gallery / `og:image` |
| `attributes.starRating` | `hotel.star` | — | `[data-testid=rating-stars]` (`starRatingType` phân biệt sao chính thức và ước tính của booking) | — |
| `attributes.latitude/longitude` | `hotel.latitude/longtitude` | — | `data-atlas-latlng` | — |
| `attributes.oceanView / familyFriendly` | suy ra từ tên, mô tả, tiện nghi (regex trong `normalise.py`), sức chứa trẻ em | `tourTypes` có "Gia đình" | suy ra từ tên, mô tả, tiện nghi, sức chứa | suy ra từ mô tả |

### Gộp trùng Vinpearl ↔ booking.com

Cùng một khách sạn Vinpearl xuất hiện ở cả hai nguồn. `normalise.py` ghép chúng bằng tên (rapidfuzz
`token_sort_ratio ≥ 88`, sau khi bỏ dấu), với điều kiện trùng điểm đến và mỗi bên chỉ ghép một lần.
Kết quả ghép nằm trong `dedup_report.csv`.

| Trường | Bên thắng |
|---|---|
| tên, mô tả, ảnh, hạng phòng | Vinpearl (nội dung của chính công ty) |
| giá bán | Vinpearl (kênh bán trực tiếp); thiếu thì dùng booking.com |
| giá booking.com | lưu ở `attributes.otaPrice` để so sánh giá đối thủ |
| toạ độ, hạng sao | Vinpearl; thiếu thì booking.com |
| điểm đánh giá booking.com | `attributes.bookingReviewScore`, `bookingReviewCount` |

Khách sạn booking.com đã ghép sẽ không xuất riêng. Hạng phòng booking.com của nó cũng bị bỏ, trừ khi dùng
`--keep-duplicate-rooms`. `attributes.fieldSources` ghi lại bên thắng cho từng trường, `attributes.sameAs`
ghi các `sourceRef` đã gộp.

> Handbook gợi ý mặc định "OTA thắng về giá". Ở đây giá Vinpearl được ưu tiên vì API Vinpearl trả giá bán
> trực tiếp theo ngày, còn giá booking.com vẫn giữ lại để so sánh. Muốn đổi thì sửa `merge_property()`
> trong `normalise.py`.

## Kiểm tra trước khi coi là xong tuần 1

1. Mở `data/stats.md`: xem số sản phẩm theo taxonomy và điểm đến, tỷ lệ có mô tả tiếng Việt, và **đọc tay
   12 mẫu** ở cuối file.
2. Mở `data/dedup_report.csv` và kiểm tra các cặp ghép.
3. `grep -c '"descriptionLang": "vi"' data/products.jsonl`: mô tả tiếng Việt là tài sản giá trị nhất của bộ dữ liệu.
4. Attraction booking.com phần lớn có mô tả tiếng Anh. Nếu nó làm lệch phép so sánh model tuần 2, chạy
   `normalise.py --vietnamese-only`.

## Khi có sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `Chưa cài trình duyệt cho Playwright` | `playwright install chromium` |
| `Không có màn hình để mở trình duyệt` | thêm `--headless`, hoặc chạy trên máy có màn hình |
| Log báo "Bị chặn … dừng lượt chạy" | nghỉ vài giờ, chạy lại cùng lệnh, cân nhắc `--delay 6 --concurrency 1` |
| Cửa sổ đứng ở trang "Chờ một chút…" | bấm xác minh trong cửa sổ đó (script đang chờ) |
| booking.com không có giá | đang chạy `--headless`, hoặc khách sạn hết phòng ngày đó → thử `--checkin` khác, rồi `retry-failed` / chạy lại |
| Sửa parser xong muốn áp dụng cho dữ liệu cũ | `python crawl.py reparse <nguồn>` rồi `python normalise.py` |
| Muốn thêm sản phẩm mới xuất hiện trên booking.com | `python crawl.py booking-hotels --rediscover` |

## Lưu ý pháp lý

- Vinpearl là dữ liệu của chính công ty. Nếu dùng lâu dài, nên xin đội kỹ thuật Vinpearl quyền truy cập API
  hoặc bản xuất dữ liệu thay vì crawl.
- Điều khoản sử dụng của booking.com không cho phép thu thập tự động. Dữ liệu này chỉ dùng nội bộ cho bản
  demo thực tập, không phân phối lại. Nếu team cần một nguồn "sạch" về pháp lý, fallback là Amadeus
  Self-Service API (§3).
- Không ghi gì vào CDP hay Insider production.
# crawl_data_vsf
# crawl_data_vsf
