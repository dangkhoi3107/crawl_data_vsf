# Báo cáo kiểm tra dữ liệu crawl — đối chiếu scope handbook

**Mốc dữ liệu:** 17:15 ngày 15/09/2026, giờ Việt Nam (UTC+7).  
**Hạn chốt:** 07:00 ngày 16/09/2026.  
**Nguồn chính:** `/home/dangkhoi/code/vsf/data-collection/data`.

## 1. Kết luận

**Đã có bộ dữ liệu Vinpearl dùng làm nền, nhưng chưa đạt scope crawl của handbook.** Có 508 Product sau chuẩn hóa, trên 11 nhãn điểm đến; thiếu ít nhất 1.492 sản phẩm để đạt mốc 2.000 và chưa có vé máy bay. Chất lượng cấu trúc tốt, nhưng cần xử lý giá bằng 0, nội dung không khớp sản phẩm, mô tả trùng và cách chuẩn hóa điểm đến.

**Mốc 2.000 sản phẩm có khả năng đạt về thời gian nếu bắt đầu crawl bổ sung và chạy ổn định. Chưa thể cam kết hoàn thành đầy đủ handbook trước 07:00.** Kiểm tra tiến trình trên máy lúc 17:15 không thấy `crawl.py` hoặc `run_forever.sh` đang chạy. Pipeline hiện kiểm tra chưa có nguồn/nhánh chuẩn hóa flight; tăng số khách sạn sẽ không giải quyết phần thiếu này.

## 2. Tiêu chí nghiệm thu theo handbook

Handbook §3 đặt mục tiêu khoảng **2.000–5.000 sản phẩm**, **10–15 điểm đến Việt Nam**, gồm lưu trú, vé máy bay, điểm tham quan và combo. Vinpearl là nguồn ưu tiên; tên và mô tả tiếng Việt, khử trùng lặp, nguồn gốc dữ liệu và cache raw là các yêu cầu trọng tâm. Không cần lấy hết sitemap Booking để hoàn thành mốc này.

| Tiêu chí | Kết quả hiện tại | Đánh giá |
|---|---|---|
| 2.000–5.000 Product | 508; bằng 25,4% mốc 2.000 | Chưa đạt |
| 10–15 điểm đến | 11 nhãn sau chuẩn hóa | Đạt số nhãn, cần kiểm tra cách gán địa lý |
| Lưu trú, flight, attraction, combo | Có hotel, attraction, combo và golf; flight = 0 | Chưa đủ danh mục |
| Nội dung tiếng Việt có ích | 484/508 được nhận diện tiếng Việt | Tốt ban đầu; còn nội dung ngắn, lặp và sai ngữ cảnh |
| Giá và khả năng đặt | 483 giá dương; 25 giá 0 vẫn `available=true` | Cần sửa/xử lý trước demo đặt hàng |
| Schema và liên kết phòng | Đủ 13 trường; UUID duy nhất; không có phòng mất liên kết cha | Đạt kiểm tra cấu trúc cơ bản |
| Khử trùng nguồn | Chưa có Booking trong dữ liệu chính | Chưa kiểm chứng đối soát đa nguồn |
| Đầu ra bàn giao | Trước audit chỉ có interim; đã tạo snapshot Product riêng cho báo cáo | Chưa chứng minh đã nạp CDP |

Phạm vi báo cáo là **crawl/catalog**, không đánh giá các hạng mục CDP, Insider hay embedding của toàn bộ Tuần 1. Nguồn đối chiếu: [handbook §3](/home/dangkhoi/code/vsf/recsys-internship-handbook-v3.vi.md:85) và [schema Product](/home/dangkhoi/code/vsf/recsys-internship-handbook-v3.vi.md:270).

## 3. Sản lượng và độ phủ

Lượt Vinpearl chạy từ 16:30:10 đến 16:50:05 ngày 15/09, khoảng 19 phút 55 giây. Có **392 bản ghi interim hợp lệ**: 15 khách sạn chứa 116 hạng phòng, cộng 377 tour/vé. Chuẩn hóa thành **508 Product**; không được nhầm 392 bản ghi, 508 sản phẩm và số URL tải về.

| Nhóm sản phẩm | Số lượng |
|---|---:|
| Khách sạn cấp cơ sở lưu trú | 15 |
| Hạng phòng | 116 |
| Điểm tham quan/vé/tour (`attraction`) | 251 |
| Combo | 121 |
| Golf | 5 |
| Vé máy bay | 0 |
| **Tổng** | **508** |

Hai cấp khách sạn và hạng phòng được đếm riêng theo thiết kế hiện tại; **131 Product hotel không có nghĩa là 131 khách sạn**.

| Điểm đến theo output hiện tại | Product |
|---|---:|
| Phú Quốc | 133 |
| Nha Trang | 131 |
| Hà Nội | 74 |
| Nghệ An | 48 |
| Hội An | 32 |
| Hải Phòng | 31 |
| Hà Tĩnh | 23 |
| Đà Nẵng | 11 |
| Hạ Long | 9 |
| TP. Hồ Chí Minh | 9 |
| Bắc Ninh | 7 |

Nha Trang và Phú Quốc chiếm **52,0%** danh mục. Độ phủ ở một số điểm đến còn mỏng; mở rộng nên ưu tiên phân bổ điểm đến thay vì tiếp tục tăng độ sâu tại hai nơi này.

### Dữ liệu chạy thử Booking được tìm thấy riêng

Thư mục `/tmp/claude-1000/-home-dangkhoi-code-vsf/724c49e5-4579-4675-a82c-b6cda0439200/scratchpad/testdata` có 54 khách sạn Booking, chứa 308 hạng phòng, và 3 attractions trong interim. State ghi nhận 54/33.719 hotel URLs và 3/13.529 attraction URLs hoàn tất. Lần crawl Booking cuối nhìn thấy trong log là 16:36; sau đó có reparse cache.

File `products.jsonl` tại thư mục chạy thử có 600 dòng nhưng được xuất lúc 16:20, trước khi interim Booking tăng lên 54 khách sạn. **Không cộng 600 vào 508**: dữ liệu chạy thử có cả Vinpearl trùng với nguồn chính và đầu ra đã cũ. Muốn tận dụng cần chuẩn hóa lại, kiểm tra rồi khử trùng. Báo cáo này giữ nguyên các nguồn và không cộng số chưa đối soát.

## 4. Đánh giá chất lượng

| Chỉ số trên 508 Product | Kết quả |
|---|---:|
| JSON hợp lệ; ID/sourceRef duy nhất | 508/508 |
| Có tên, mô tả, nhãn điểm đến và URL ảnh | 508/508 |
| Mô tả được nhận diện tiếng Việt | 484/508 — 95,3% |
| Mô tả từ 80 ký tự | 498/508 — 98,0% |
| Độ dài mô tả trung vị | 1.476 ký tự |
| Giá lớn hơn 0 | 483/508 — 95,1% |
| Có tọa độ | 131/508 — toàn bộ hotel/property và room |
| Không lấy được chi tiết, dùng danh sách dự phòng | 25/377 tour/vé — 6,6% |
| Biến thể thành viên (`memberTier`) | 59 |
| Nhóm mô tả giống hệt nhau | 60 nhóm, chứa 337 Product |

Ngôn ngữ được nhận diện bằng tỷ lệ ký tự tiếng Việt trong code, không phải đánh giá thủ công toàn bộ. Có URL ảnh không chứng minh ảnh còn truy cập được. Mô tả lặp có thể thuộc các biến thể vé hợp lệ; không nên tự xóa mọi dòng có mô tả giống nhau.

### Các vấn đề cần xử lý trước bàn giao

1. **25 sản phẩm giá 0 vẫn được ghi còn bán.** Log có 50 cảnh báo HTTP 500 trên 25 đường dẫn chi tiết, thử hai channel. Crawler giữ thông tin từ danh sách; normalizer vẫn suy ra `available=true` từ cờ bật và ngày kết thúc. Không dùng các dòng này làm vé miễn phí hoặc bằng chứng có thể đặt; cần gắn trạng thái chưa xác minh giá hoặc loại khỏi tập demo đặt hàng.
2. **Có mô tả không khớp tên hoặc đã cũ.** Ví dụ `VW02335` mang tên Safari Phú Quốc + Fastpass + Xe điện, nhưng mô tả nói VinWonders và có thời gian ưu đãi năm 2023. `VW02885` mang tên Wave Park trong khi mô tả dự phòng nói Water Park + Buffet. Cần kiểm tra nguồn/cache của từng sản phẩm; chưa đủ bằng chứng quy lỗi cho parser hay website.
3. **Điểm đến chưa nhất quán.** Vinpearl Resort & Golf Nam Hội An cùng 8 hạng phòng được gán Đà Nẵng từ địa chỉ hành chính; các vé/golf Nam Hội An được gán Hội An. Cần thống nhất “điểm đến du lịch” để tìm kiếm, ghép trùng và gợi ý không bị chia tách.
4. **Mô tả có mặt nhưng chưa chắc có giá trị embedding.** Hai phòng Hạ Long chỉ có mô tả kiểu tên phòng, trong đó một dòng là `Deluxe Twin Terrace`. Nhiều vé chủ yếu chứa điều kiện sử dụng, hoàn hủy; nên tách chính sách khỏi nội dung mô tả trải nghiệm.
5. **Biến thể thành viên và văn bản trùng làm giảm độ đa dạng.** 59 biến thể thành viên cần quản lý như offer/thuộc tính hoặc cân nhắc loại khỏi tập embedding chung, sau khi kiểm tra quan hệ với vé gốc.

Áp dụng bộ lọc sơ bộ: giá dương, `available=true`, mô tả nhận diện `vi`, dài ≥80 ký tự, không có `memberTier`, còn **404 Product trên 11 nhãn điểm đến**. Đây là **ứng viên để tiếp tục QA**, chưa phải 404 sản phẩm đã xác nhận đúng nội dung. Ngưỡng 80 ký tự và cách lọc thành viên là lựa chọn audit, không phải con số bắt buộc trong handbook. Các nhóm lỗi có giao nhau, không cộng trực tiếp để tính số dòng loại.

Giá phòng trong bộ dữ liệu được hỏi cho 1 đêm, 2 người lớn, tại các ngày 29/09, 15/10 và 14/11/2026. Đây không phải bảng giá đầy đủ cho cả sáu tháng hoặc giá đặt chỗ tại thời điểm đọc báo cáo.

## 5. Khả năng hoàn thành trước 07:00

Từ mốc 17:15 đến 07:00 có khoảng 13 giờ 45 phút. Nên dành **06:00–07:00** cho chuẩn hóa, khử trùng, đọc mẫu và xuất báo cáo, tức khoảng 12 giờ 45 phút để crawl.

Benchmark chạy thử cho Booking hotels: 3 worker thường đạt 15 URL trong 104,52 giây (**8,61 URL/phút**); 3 worker fast đạt 15 URL trong 55,01 giây (**16,36 URL/phút**). Các batch 1 worker dao động khoảng 3,32–6,87 URL/phút. Đây là mẫu ngắn, chưa chứng minh tốc độ ổn định qua đêm.

**Dự toán thận trọng hơn, lấy 404 ứng viên hiện tại làm nền**, giả định mỗi URL mới mang lại 1 Product đạt bộ lọc và không trùng:

| Mục tiêu | Cần bổ sung | 3,32 URL/phút | 6 URL/phút | 8,61 URL/phút |
|---|---:|---:|---:|---:|
| 2.000 Product | 1.596 | 8,01 giờ | 4,43 giờ | 3,09 giờ |
| 5.000 Product | 4.596 | 23,07 giờ | 12,77 giờ | 8,90 giờ |

Các con số chưa gồm discovery, CAPTCHA, nghỉ do bị chặn, lỗi, nội dung bị loại và phần flight. Một URL có thể tạo nhiều hạng phòng, nhưng mẫu Booking nhỏ ưu tiên khách sạn thương hiệu; không nên ngoại suy tỷ lệ phòng này cho toàn bộ Việt Nam. Ngược lại, URL lỗi hoặc dữ liệu không đạt có thể tạo **0** Product dùng được.

- **2.000: khả thi về khối lượng**, có điều kiện crawler thực sự chạy, dữ liệu mới đạt chất lượng và được phân bổ đúng điểm đến.
- **5.000: chưa nên cam kết**, phụ thuộc tốc độ dài hạn và tỷ lệ sản phẩm dùng được.
- **Đầy đủ handbook: hiện chưa thể cam kết**, vì còn flight, vấn đề nội dung/địa lý và chưa có tiến trình crawl hoạt động tại mốc kiểm tra.
- Crawl hết phần Booking còn lại không phải mục tiêu đêm nay: riêng 33.665 hotel URLs còn lại đã cần khoảng 34,3 giờ ngay ở benchmark nhanh nhất.

## 6. Kế hoạch đề xuất trong scope

| Mốc | Việc cần làm | Kết quả cần đo |
|---|---|---|
| Bắt đầu lượt bổ sung | Chốt nguồn flight; xử lý/quarantine các dòng nghi vấn; khởi chạy Booking theo điểm đến | Có tiến trình và log tăng thực tế |
| Các batch đầu | Khoảng 40–60 URL/điểm đến, chuẩn hóa sau từng vòng | Product mới sau khử trùng, chất lượng giá/mô tả và phân bổ địa lý |
| Trong đêm | Bổ sung nơi còn mỏng; tiếp tục tới mốc ≥2.000 đạt tiêu chí chất lượng | Sản lượng theo taxonomy/điểm đến, không chỉ tổng URL |
| 06:00–07:00 | Chốt snapshot, chuẩn hóa, dedup, kiểm tra mẫu mọi nhóm/điểm đến, xuất báo cáo | Bộ Product cùng số liệu có thể tái kiểm tra |

CLI hiện có `--match` để lọc **chuỗi URL**, không bảo đảm lọc đúng địa lý; `--limit` là số URL trong lượt, không phải quota Product hay quota từng điểm đến. Cần kiểm tra `destination` sau parse. Cấu hình điểm đến trong `collectors/plan.py` mới là phần khung ở snapshot kiểm tra, chưa được nối đầy đủ qua CLI/Booking discovery; không dựa vào đó để khẳng định phân bổ tự động.

Nếu chưa bổ sung được flight, báo cáo sáng mai phải ghi **“hoàn thành một phần scope: lưu trú, điểm tham quan, combo và golf; còn thiếu flight”**, kể cả khi đủ 2.000 dòng.

Đây là kế hoạch đề xuất; lượt audit này không khởi chạy crawl qua đêm hoặc thay đổi pipeline.

## 7. Đoạn tóm tắt có thể dùng để báo cáo

> Tại 17:15 ngày 15/09/2026, nhóm đã hoàn thành lượt thu thập Vinpearl và chuẩn hóa được 508 sản phẩm trên 11 nhãn điểm đến, gồm 15 cơ sở lưu trú, 116 hạng phòng, 251 vé/điểm tham quan, 121 combo và 5 sản phẩm golf. Tỷ lệ mô tả được nhận diện tiếng Việt đạt 95,3%, tỷ lệ có giá dương đạt 95,1%. Bộ dữ liệu chưa đạt mục tiêu 2.000–5.000 sản phẩm của handbook và chưa có vé máy bay. Hiện cần xử lý 25 sản phẩm thiếu chi tiết/giá, rà soát nội dung và chuẩn hóa điểm đến. Mốc 2.000 có khả năng đạt về khối lượng trước 07:00 ngày 16/09 nếu chạy bổ sung ổn định; hoàn thành đầy đủ scope còn phụ thuộc nguồn flight và kết quả kiểm tra chất lượng.

## 8. Tệp bàn giao và cách kiểm chứng

- [Catalog chuẩn hóa JSONL](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/snapshot/products.jsonl) và [CSV](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/snapshot/products.csv).
- [Thống kê và 12 mẫu đọc tay](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/snapshot/stats.md).
- [Danh sách cờ chất lượng theo sản phẩm](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/quality-issues.csv); một sản phẩm có thể có nhiều cờ.
- [Chỉ số chất lượng](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/quality-metrics.json), [audit chi tiết và mẫu](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/quality-audit-detail.json), [benchmark/queue Booking](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/eta-evidence.json).
- [Log crawl nguồn](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/source-crawl-20260915.log), [mốc snapshot và SHA-256](/home/dangkhoi/code/vsf/data-collection/reports/crawl-audit-2026-09-15/evidence.json).

Đã chạy normalizer hiện có trên **bản sao** interim trong thư mục báo cáo và kiểm tra toàn bộ 508 dòng; dữ liệu crawl gốc không bị ghi đè. Kiểm tra process chỉ là ảnh chụp tại một thời điểm trên máy hiện tại, không xác nhận trạng thái máy từ xa. Báo cáo dựa trên file, log, state và code local; không tải lại website để xác nhận giá/ảnh/khả năng đặt hiện hành.
