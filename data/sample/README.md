# Bộ dữ liệu mẫu — 50 sản phẩm

Cắt ra từ catalog đầy đủ 2.225 sản phẩm để chạy thử nhanh mà không phải tải 12 MB.
Cùng schema, cùng giá trị thật — không phải dữ liệu giả.

| File | Kích thước | Dùng khi nào |
|---|---|---|
| `products-sample.jsonl` | 224 KB | Viết code. Đầy đủ 13 trường và toàn bộ `attributes` |
| `products-sample.csv` | 76 KB | Mở xem bằng Excel/Sheets. Chỉ có các trường hay dùng, đã làm phẳng |

## Mẫu này phủ những gì

50 sản phẩm trên 9 điểm đến, đủ cả **7 biến thể**:

| Biến thể | Số lượng |
|---|---|
| `hotel/property` | 8 |
| `hotel/room` | 15 |
| `attraction` | 5 |
| `flight/route` | 4 |
| `flight/flight` | 9 |
| `combo` | 5 |
| `golf` | 4 |

Và các trường hợp đặc biệt mà code của bạn cần xử lý đúng:

- **Liên kết cha–con toàn vẹn**: mọi hạng phòng đều có khách sạn cha trong mẫu, mọi chuyến bay đều có tuyến
  cha. Không có bản ghi mồ côi, nên thử `parentProductId` được ngay.
- **1 sản phẩm không có giá** — điểm công cộng không bán vé (`attributes.ticketed = false`).
  `unitPrice = null` ở đây nghĩa là không bán vé, không phải miễn phí.
- **2 vé có `memberPrices`** — giá theo hạng thành viên VinClub.
- **11 sản phẩm có `attributes.policies`** — điều khoản vé, tách riêng khỏi `description`.
- **1 sản phẩm có `attributes.descriptionOriginal`** — nguồn chỉ có mô tả tiếng Anh nên mô tả tiếng Việt
  được dựng từ thuộc tính.
- Toàn bộ 50 sản phẩm đều có toạ độ và mô tả tiếng Việt, giống catalog đầy đủ.

## Chạy thử

```python
import json
from collections import Counter

products = [json.loads(l) for l in open("products-sample.jsonl", encoding="utf-8")]
print(len(products), Counter(p["taxonomy"] for p in products))

# kiểm tra liên kết cha-con
ids = {p["productId"] for p in products}
orphans = [p["name"] for p in products
           if p["attributes"].get("parentProductId") not in (None, *ids)]
assert not orphans, orphans
```

Sinh lại mẫu (ví dụ muốn nhiều sản phẩm hơn mỗi loại):

```
python make_sample.py --per-variant 8
```

## Đọc thêm

- `../SCHEMA.md` — mô tả chi tiết 13 trường và toàn bộ `attributes`
- `../template.json` — bản máy đọc được, kèm độ phủ từng khoá và ví dụ cho mỗi biến thể
- `../BANGIAO.md` — tổng quan gói bàn giao và ghi chú riêng cho từng đội
