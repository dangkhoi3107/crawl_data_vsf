"""Sinh data/template.json từ catalog đã chuẩn hoá: schema 13 trường, các khoá attributes theo từng
loại sản phẩm kèm độ phủ thực tế, và một bản ghi thật làm ví dụ cho mỗi loại.

Chạy lại sau mỗi lần normalise.py:  python make_template.py
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics

_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument('--data-dir', default='data')
_args = _ap.parse_args()
PATH = f'{_args.data_dir}/products.jsonl'
rows = [json.loads(l) for l in open(PATH)]

NOTE = {
 'level': 'property = khách sạn, room = hạng phòng; flight: route = tuyến, flight = chuyến cụ thể',
 'parentProductId': 'productId của khách sạn cha (hạng phòng) hoặc tuyến bay cha',
 'url': 'trang nguồn của sản phẩm',
 'fieldSources': 'trường nào lấy từ nguồn nào, dùng để truy nguồn',
 'descriptionLang': 'vi / en — đoán theo tỷ lệ ký tự có dấu, không phải kiểm tra ngôn ngữ đầy đủ',
 'descriptionSource': 'có mặt nghĩa là mô tả được tự sinh, không phải văn bản gốc của nguồn',
 'latitude': 'vĩ độ WGS84',
 'longitude': 'kinh độ WGS84',
 'locationSource': 'booking.com / agoda.com / trip.com / vinpearl / osm / ourairports / manual',
 'locationPrecision': 'exact = vị trí riêng của sản phẩm; venue = khu vui chơi dùng vé; airport = sân bay đến; poi = điểm tham quan trip.com',
 'address': 'địa chỉ nguồn cung cấp',
 'province': 'tỉnh/thành theo địa chỉ, khác với destination (nhãn điểm đến du lịch)',
 'city': 'thành phố theo địa chỉ',
 'starRating': 'hạng sao 1–5',
 'starRatingType': 'official = hạng sao chính thức, estimated = do nguồn tự xếp',
 'propertyType': 'khách sạn / resort / căn hộ / homestay…',
 'amenities': 'tiện ích, đã gộp từ nhiều nguồn nên có thể trùng ý',
 'images': 'ảnh phụ; ảnh chính nằm ở trường imageUrl cấp trên',
 'reviewScore': 'điểm đánh giá trung bình — KHÔNG có nội dung hay tên người đánh giá',
 'reviewScoreScale': 'thang điểm của reviewScore (10 hoặc 5)',
 'reviewCount': 'số lượt đánh giá',
 'tripAdvisorRating': 'điểm TripAdvisor do vinpearl.com công bố',
 'tripAdvisorReviewCount': 'số lượt đánh giá TripAdvisor',
 'priceDate': 'ngày nhận phòng đã dùng để hỏi giá',
 'priceNights': 'số đêm của unitPrice (luôn là 1)',
 'priceAdults': 'số người lớn đã dùng để hỏi giá',
 'otaPrices': 'giá cùng sản phẩm ở các OTA khác, để so sánh',
 'vinpearlPrice': 'giá niêm yết trên vinpearl.com',
 'roomName': 'tên hạng phòng',
 'hotelName': 'tên khách sạn cha',
 'roomSizeM2': 'diện tích phòng (m2)',
 'maxOccupancy': 'số khách tối đa',
 'bed': 'loại giường',
 'oceanView': 'phòng hướng biển',
 'familyFriendly': 'phù hợp gia đình có trẻ nhỏ',
 'conditions': 'điều kiện đặt phòng / sử dụng vé',
 'brand': 'thương hiệu (Vinpearl, Meliá…)',
 'venue': 'địa điểm sử dụng vé, xem collectors/venues.csv',
 'ticketed': 'false = điểm công cộng không bán vé',
 'openingHours': 'giờ mở cửa, nguồn trip.com',
 'durationMinutes': 'thời lượng tham quan hoặc thời gian bay (phút)',
 'suggestedDuration': 'thời lượng gợi ý dạng chữ',
 'tourCode': 'mã tour/vé của Vinpearl',
 'vinpearlType': 'mã loại sản phẩm nội bộ Vinpearl',
 'salesChannels': 'kênh bán nội bộ Vinpearl',
 'soldQuantity': 'số lượng đã bán do nguồn công bố',
 'promo': 'nội dung khuyến mãi',
 'adultOriginalPrice': 'giá gốc người lớn trước khuyến mãi',
 'childPrice': 'giá trẻ em',
 'audience': 'đối tượng phù hợp do nguồn gắn nhãn',
 'supplier': 'đơn vị cung cấp dịch vụ',
 'airline': 'hãng bay',
 'flightNumber': 'số hiệu chuyến bay',
 'departureAirport': 'sân bay đi (mã IATA)',
 'arrivalAirport': 'sân bay đến (mã IATA)',
 'originalDestination': 'nhãn điểm đến trước khi sửa theo bằng chứng',
 'destinationSource': 'căn cứ gán điểm đến',
 'destinationEvidence': 'bằng chứng đã đối chiếu khi sửa điểm đến',
 'hasDetail': 'đã lấy được trang chi tiết hay chỉ có dữ liệu trang danh sách',
}

SCHEMA = {
 'productId':   ('string (UUIDv5 của sourceRef)', 'Khoá chính. Ổn định giữa các lần chạy lại, dùng làm khoá ngoại được.'),
 'name':        ('string', 'Tên hiển thị. Hạng phòng theo mẫu "<Khách sạn> - <Hạng phòng>", vé máy bay "Vé máy bay <A> - <B>".'),
 'taxonomy':    ('string enum', 'hotel | flight | attraction | combo | golf'),
 'destination': ('string', 'Nhãn điểm đến du lịch (Nha Trang, Phú Quốc…), không phải tỉnh hành chính.'),
 'description': ('string', 'Văn bản để embedding. Nếu attributes.descriptionSource có giá trị thì đây là mô tả tự sinh.'),
 'attributes':  ('object', 'Mọi trường ngoài 13 trường CDP. Khoá thay đổi theo taxonomy, xem attributes_by_taxonomy.'),
 'unitPrice':   ('number | null', 'Khách sạn: giá 1 đêm. null nghĩa là chưa lấy được giá, không phải miễn phí.'),
 'currency':    ('string', 'Luôn là "VND".'),
 'available':   ('boolean', 'true = có giá tại thời điểm crawl. KHÔNG phải xác nhận còn phòng/vé hiện tại.'),
 'availableFrom': ('string (YYYY-MM-DD) | null', 'Vé Vinpearl: ngày bắt đầu bán. Vé máy bay: ngày bay sớm nhất thấy được.'),
 'availableTo':   ('string (YYYY-MM-DD) | null', 'Vé Vinpearl: ngày hết hạn bán. Vé máy bay: ngày bay muộn nhất thấy được.'),
 'imageUrl':    ('string (URL) | null', 'Ảnh chính. Ảnh phụ nằm trong attributes.images.'),
 'sourceRef':   ('string', 'Định danh gốc: "<nguồn>:<loại>:<id>". Nguồn: vinpearl | booking | agoda | trip.'),
}

def variant(o):
    a = o.get('attributes') or {}
    lv = a.get('level')
    return o['taxonomy'] + ('/' + lv if lv else '')

groups = collections.defaultdict(list)
for o in rows:
    groups[variant(o)].append(o)

# do phu tung truong cap 1
n = len(rows)
schema_cov = {k: sum(1 for o in rows if o.get(k) not in (None, '', [], {})) for k in SCHEMA}

attributes_by_taxonomy = {}
for v, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
    cnt = collections.Counter()
    for o in items:
        for k, val in (o.get('attributes') or {}).items():
            if val not in (None, '', [], {}):
                cnt[k] += 1
    m = len(items)
    keys = {}
    for k, c in cnt.most_common():
        if c / m < 0.10:
            continue
        keys[k] = {'do_phu': f'{100*c/m:.0f}%', 'y_nghia': NOTE.get(k, '')}
    attributes_by_taxonomy[v] = {'so_san_pham': m, 'attributes': keys}

# vi du: ban ghi co do dai mo ta gan trung vi nhat, uu tien ban ghi day du truong
examples = {}
for v, items in groups.items():
    lens = sorted(len(o.get('description') or '') for o in items)
    med = statistics.median(lens)
    def score(o):
        a = o.get('attributes') or {}
        filled = sum(1 for x in a.values() if x not in (None, '', [], {}))
        return (abs(len(o.get('description') or '') - med) / 100.0) - filled / 10.0
    examples[v] = min(items, key=score)

out = {
 '_doc': 'Template schema catalog du lịch V-OTA. Mô tả 13 trường CDP, các khoá trong attributes theo từng '
         'loại sản phẩm, và một bản ghi thật làm ví dụ cho mỗi loại. Sinh tự động từ data/products.jsonl.',
 '_ban': __import__('datetime').date.today().isoformat(),
 '_tong_san_pham': n,
 '_doc_them': 'BANGIAO.md (cùng thư mục) và README.md của repo crawl_data_vsf',
 'schema': {
     k: {'kieu': SCHEMA[k][0],
         'do_phu': f'{100*schema_cov[k]/n:.1f}%',
         'y_nghia': SCHEMA[k][1]}
     for k in SCHEMA
 },
 'attributes_by_taxonomy': attributes_by_taxonomy,
 'vi_du': examples,
}

with open(f'{_args.data_dir}/template.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f'đã ghi {_args.data_dir}/template.json — {n} sản phẩm, {len(groups)} biến thể')

