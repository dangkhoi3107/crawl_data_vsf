# Thống kê catalog

Tạo lúc 2026-09-16 · **2225 sản phẩm**

## Đối chiếu handbook §3

| Mục tiêu | Thực tế | |
|---|---|---|
| 2.000–5.000 sản phẩm | 2225 | ✅ |
| 10–15 điểm đến (≥ 20 sản phẩm mỗi nơi) | 15 | ✅ |
| Đủ hotel, flight, attraction, combo | attraction, combo, flight, golf, hotel | ✅ |
| Mô tả được nhận diện là tiếng Việt | 2225 (100.0%) | ✅ |
| Có giá | 2079 (93.4%) | ✅ |
| Được đánh dấu available trong dữ liệu | 2078 (93.4%) | |
| Có toạ độ | 2225 (100.0%) | |
| Sản phẩm trùng giữa các nguồn đã gộp | 53 | |

Nhãn ngôn ngữ được ước lượng từ tỷ lệ ký tự có dấu trong mô tả; không xác nhận tên hoặc toàn bộ nội dung đã là tiếng Việt. Cần đọc tay các mẫu bên dưới.
Cờ available được suy ra từ dữ liệu nguồn và giá tại thời điểm crawl; chưa xác minh đặt chỗ hiện tại. Các trường còn thiếu được liệt kê trong `quality_review.csv`.
Trong 146 sản phẩm không có giá, 146 là điểm công cộng không bán vé (không có giá là đúng); phần còn lại mới là thiếu giá cần đối chiếu nguồn.

## Điểm đến × loại sản phẩm

| Điểm đến | hotel | flight | attraction | combo | golf | tổng |
|---|---|---|---|---|---|---|
| Nha Trang | 144 | 23 | 64 | 19 | 1 | 251 |
| Phú Quốc | 112 | 37 | 68 | 26 | 1 | 244 |
| Hà Nội | 87 | 33 | 68 | 13 | 0 | 201 |
| Hải Phòng | 126 | 16 | 25 | 8 | 1 | 176 |
| TP. Hồ Chí Minh | 99 | 42 | 21 | 1 | 1 | 164 |
| Đà Nẵng | 93 | 34 | 10 | 0 | 0 | 137 |
| Nghệ An | 77 | 17 | 28 | 11 | 0 | 133 |
| Hội An | 101 | 0 | 23 | 8 | 1 | 133 |
| Đà Lạt | 96 | 16 | 18 | 0 | 0 | 130 |
| Huế | 97 | 14 | 18 | 0 | 0 | 129 |
| Quy Nhơn | 90 | 12 | 18 | 0 | 0 | 120 |
| Phan Thiết | 98 | 0 | 17 | 0 | 1 | 116 |
| Sa Pa | 89 | 0 | 18 | 0 | 0 | 107 |
| Hà Tĩnh | 83 | 0 | 3 | 7 | 0 | 93 |
| Hạ Long | 51 | 0 | 17 | 0 | 0 | 68 |
| Bắc Ninh *(ngoài kế hoạch)* | 7 | 0 | 0 | 0 | 0 | 7 |
| Thanh Hóa *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Quảng Bình *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Ninh Bình *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Tây Ninh *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |

## Theo nguồn

- booking: 1092
- trip: 461
- vinpearl: 429
- agoda: 243

## Theo loại / cấp

- attraction/-: 416
- combo/-: 93
- flight/flight: 184
- flight/route: 60
- golf/-: 6
- hotel/property: 559
- hotel/room: 907

Độ dài mô tả trung vị: 739 ký tự

## Bị loại

- biến thể giá thành viên Vinpearl (đã gộp, giá từng hạng giữ trong memberPrices): 54
- khách sạn trùng giữa các nguồn (đã gộp): 49
- không có giá và nguồn không cung cấp được (không đặt được): 48
- điểm tham quan trip.com trùng vé Vinpearl (đã gộp): 4
- room của sản phẩm bị loại: 2
- tuyến bay ngoài kế hoạch: 1
- booking: vượt 30/điểm đến: 1
- flight của sản phẩm bị loại: 1

## Vị trí (toạ độ)

| Loại / cấp | Sản phẩm | Có toạ độ | |
|---|---|---|---|
| attraction/- | 416 | 416 | 100.0% |
| combo/- | 93 | 93 | 100.0% |
| flight/flight | 184 | 184 | 100.0% |
| flight/route | 60 | 60 | 100.0% |
| golf/- | 6 | 6 | 100.0% |
| hotel/property | 559 | 559 | 100.0% |
| hotel/room | 907 | 907 | 100.0% |

Nguồn toạ độ: booking.com 1137, trip.com 413, ourairports 244, agoda.com 240, vinpearl 86, manual 53, osm 52

Độ chính xác: exact 1683, venue 298, airport 244 (exact = vị trí riêng của sản phẩm; venue = khu vui chơi/sân golf dùng vé; poi = điểm tham quan trip.com; airport = sân bay đến)

- vé có toạ độ địa điểm: 377
- điểm đến sửa theo bằng chứng (destination_overrides.csv): 14
- khách sạn: toạ độ xa tâm điểm đến: 10
- khách sạn: trùng toạ độ khách sạn khác: 4
- toạ độ sửa tay (location_overrides.csv): 3
- vé đổi điểm đến theo địa điểm: 3

Cảnh báo toạ độ (12 sản phẩm, không tính hạng phòng):

- Meliá Vinpearl Phu Ly · Ninh Bình · cách tâm Ninh Bình 32 km
- Serena Xuân Thành Hotel · Hà Tĩnh · cách tâm Hà Tĩnh 35 km
- Songlam Waterfront Hotel - 藍江酒店 · Hà Tĩnh · cách tâm Hà Tĩnh 40 km
- Khách Sạn Xanh Hà Tĩnh · Hà Tĩnh · cách tâm Hà Tĩnh 42 km
- Hoa Tien Paradise Villa · Hà Tĩnh · cách tâm Hà Tĩnh 34 km
- Khách sạn Mường Thanh Grand Hà Tĩnh (Muong Thanh Grand Ha Tinh Hotel) · Hà Tĩnh · cách tâm Hà Tĩnh 56 km
- Khách sạn Mường Thanh Luxury Xuân Thành (Muong Thanh Luxury Xuan Thanh Hotel) · Hà Tĩnh · cách tâm Hà Tĩnh 34 km
- Khách sạn Polaris (Polaris Hotel) · Hà Tĩnh · cách tâm Hà Tĩnh 59 km
- Hải Vân Quan · Huế · cách tâm Huế 66 km
- Đèo Hải Vân · Huế · cách tâm Huế 65 km
- Khu Lưu niệm Đại thi hào Nguyễn Du · Hà Tĩnh · cách tâm Hà Tĩnh 39 km
- Đền Chợ Củi - Thờ Quan Hoàng Mười · Hà Tĩnh · cách tâm Hà Tĩnh 37 km

Bản đồ: 804 ghim trong `map/` (mymaps-khach-san.csv, mymaps-vui-choi.csv, mymaps-san-bay.csv, places.geojson). Cần kiểm tra tay: 30 dòng trong `map/can-kiem-tra.csv`.

## Mẫu để đọc tay (kiểm tra chất lượng tên + mô tả)

- **Hòn Tằm Resort** · hotel · Nha Trang · 2219215 VND  
  Với vẻ đẹp của thiên nhiên kết hợp cùng kiến trúc bungalow và villa sang trọng, Hòn Tằm Resort Nha Trang mang đến cho du khách một kỳ nghỉ đẳng cấp, riêng tư và ấn tượng khó quên. Khu nghỉ dưỡng được bao phủ bởi cảnh quan xanh mát, yên ả của rừng và biển giúp thư giãn cả cơ thể l
- **Vé Hạng Văn Lang | Trải nghiệm Gondola, Aquafield & Set Ẩm thực** · attraction · Hà Nội · 1245000 VND  
  Vé Hạng Văn Lang | Trải nghiệm Gondola, Aquafield & Set Ẩm thực  ► Vui lòng tham khảo sơ đồ chỗ ngồi trước khi đặt vé.  Phù hợp: Nhóm bạn, Gia đình, Cặp đôi. Địa điểm: Hà Nội. Giá từ 1.245.000₫
- **[VinWonders Nam Hội An] [Sunset Premium] Vé vào cửa & Xe Buggy & Gói VIP Safari & Set trà chiều** · combo · Hội An · 750000 VND  
  [VinWonders Nam Hội An] [Sunset Premium] Vé vào cửa & Xe Buggy & Gói VIP Safari & Set trà chiều  Vé vào cửa trực tiếp khu vui chơi VinWonders Nam Hội An sử dụng trong ngày dành cho 01 người  Bao gồm Vé vào cửa trực tiếp khu vui chơi VinWonders Nam Hội An sử dụng trong ngày dành c
- **[02 ngày không giới hạn] - VinWonders + Vinpearl Safari Phú Quốc + Bảo Tàng Gấu Teddy** · attraction · Phú Quốc · 2040000 VND  
  [02 ngày không giới hạn] - VinWonders + Vinpearl Safari Phú Quốc + Bảo Tàng Gấu Teddy  - Combo vé tiêu chuẩn vào cửa trực tiếp VinWonders và Vinpearl Safari Phú Quốc trong 02 ngày (ra vào không giới hạn) - Tặng 01 Vé Bảo Tàng Gấu cho mỗi vé  Bao gồm - Combo vé tiêu chuẩn vào cửa 
- **[Vinpearl Horse Academy] - Tour tham quan "Mái nhà của ngựa"** · attraction · Hải Phòng · 150000 VND  
  [Vinpearl Horse Academy] - Tour tham quan "Mái nhà của ngựa"  Phù hợp: Nhóm bạn, Gia đình, Cặp đôi, Doanh nhân. Địa điểm: Hải Phòng. Giá từ 150.000₫
- **Vé máy bay Đà Lạt - Hải Phòng** · flight · Hải Phòng · 1116000 VND  
  Vé máy bay một chiều từ Đà Lạt (DLI) đến Hải Phòng (HPH). Hãng khai thác: VietJet Air. Thời gian bay khoảng 1 giờ 45 phút. Giá một chiều từ 1.116.000₫, khứ hồi từ 2.018.000₫. Tháng có giá trung bình rẻ nhất: 2026-12.
- **Nâu Homestay 2** · hotel · Hải Phòng · 625000 VND  
  Nằm ở Thành phố Hải Phòng, gần Nhà hát lớn Hải Phòng, Trung tâm thương mại Vincom Ngô Quyền và Hai Phong Railway Station, Nâu Homestay 2 có Wi-Fi miễn phí, nơi khách có thể trải nghiệm phòng chờ chung.  Tất cả các căn có phòng tắm riêng, vòi xịt/chậu rửa vệ sinh, điều hòa, TV màn
- **Kingdom Hotel Cua Lo** · hotel · Nghệ An · 845688 VND  
  Nằm ở Cửa Lò, Nghệ An, Kingdom Hotel Cua Lo tọa lạc cách Bãi biển Cửa Lò 7 phút đi bộ. Ngoài nhà hàng, khách sạn 3 sao này còn có các phòng với điều hòa được trang bị Wi-Fi miễn phí, trong đó mỗi phòng đều có phòng tắm riêng. Chỗ nghỉ này cung cấp dịch vụ phòng và quầy lễ tân 24 
- **Royal Resort Bai Xep Quy Nhon** · hotel · Quy Nhơn · 594000 VND  
  Nằm ở Quy Nhơn, cách Bãi Xếp chưa đến 1 km, Royal Resort Bai Xep Quy Nhon cung cấp chỗ nghỉ có khu vườn, chỗ đậu xe riêng miễn phí, phòng chờ chung và sân hiên. Chỗ nghỉ này có các tiện nghi như nhà hàng, quầy bar và tiện nghi thể thao dưới nước. Chỗ nghỉ cung cấp lễ tân 24/24, d
- **Khách sạn Sophia Central Nha Trang by HT (Sophia Central Nha Trang Hotel by HT)** · hotel · Nha Trang · 248116 VND  
  Khách sạn Sophia Central Nha Trang by HT tại Nha Trang: Tất cả những gì bạn cần biếtKhách sạn Sophia Central Nha Trang by HT là lựa chọn lưu trú riêng tư và thuận tiện dành cho du khách công tác lẫn những ai muốn tận hưởng nhịp sống duyên hải Nha Trang theo cách yên tĩnh, chủ độn
- **Eldora Hotel** · hotel · Huế · 1388889 VND  
  Eldora Hotel tại Huế: Tất cả những gì bạn cần biếtEldora Hotel là điểm dừng chân lý tưởng để khám phá nét duyên dáng của Huế, đồng thời mang đến không gian thuận tiện cho những chuyến công tác ngắn ngày. Được xây dựng vào năm 2014, khách sạn sở hữu 81 phòng, tạo cảm giác vừa đủ r
- **Khách sạn Mường Thanh Sông Lam (Muong Thanh Song Lam Hotel)** · hotel · Nghệ An · 661601 VND  
  Khách sạn Mường Thanh Sông Lam tại Vinh: Tất cả những gì bạn cần biếtKhách sạn Mường Thanh Sông Lam là điểm dừng chân nổi bật ngay trung tâm Vinh, mang đến lựa chọn thuận tiện cho cả chuyến công tác bận rộn lẫn kỳ nghỉ khám phá thành phố. Với vị trí chỉ cách trung tâm 0,1 km, quý
- **Khách sạn 1991 Phan Thiết (1991 Hotel Phan Thiết)** · hotel · Phan Thiết · 212348 VND  
  Khách sạn 1991 Phan Thiết tại Phan Thiết: Tất cả những gì bạn cần biếtKhách sạn 1991 Phan Thiết là lựa chọn lưu trú đầy thuận tiện tại Phan Thiết, phù hợp cho cả chuyến công tác cần kết nối nhanh với trung tâm lẫn kỳ nghỉ thư giãn muốn khám phá nhịp sống địa phương. Tọa lạc cách 
- **Nông Trại Cún Puppy Farm** · attraction · Đà Lạt · None VND  
  Nông trại này có diện tích rộng lớn, khuôn viên sạch sẽ và trang thiết bị đầy đủ. Nơi đây nuôi dưỡng rất nhiều loài động vật như chó, lạc đà, ngựa, dê... Ngoài ra, trong trang trại còn có vườn dâu tây, vườn bí ngô, xương rồng... Không gian ấm cúng, rất thích hợp để gia đình, bạn 
- **Công viên Võ Văn Kiệt** · attraction · Phan Thiết · None VND  
  Công viên Võ Văn Kiệt. Địa chỉ: Võ Văn Kiệt, Phú Thủy, Lâm Đồng, Việt Nam. Giờ mở cửa: Mở cửa cả ngày
