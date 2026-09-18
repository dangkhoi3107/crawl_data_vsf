# Thống kê catalog

Tạo lúc 2026-09-16 · **2216 sản phẩm**

## Đối chiếu handbook §3

| Mục tiêu | Thực tế | |
|---|---|---|
| 2.000–5.000 sản phẩm | 2216 | ✅ |
| 10–15 điểm đến (≥ 20 sản phẩm mỗi nơi) | 15 | ✅ |
| Đủ hotel, flight, attraction, combo | attraction, combo, flight, golf, hotel | ✅ |
| Mô tả được nhận diện là tiếng Việt | 2216 (100.0%) | ✅ |
| Có giá | 2076 (93.7%) | ✅ |
| Được đánh dấu available trong dữ liệu | 2075 (93.6%) | |
| Có toạ độ | 2216 (100.0%) | |
| Sản phẩm trùng giữa các nguồn đã gộp | 53 | |

Nhãn ngôn ngữ được ước lượng từ tỷ lệ ký tự có dấu trong mô tả; không xác nhận tên hoặc toàn bộ nội dung đã là tiếng Việt. Cần đọc tay các mẫu bên dưới.
Cờ available được suy ra từ dữ liệu nguồn và giá tại thời điểm crawl; chưa xác minh đặt chỗ hiện tại. Các trường còn thiếu được liệt kê trong `quality_review.csv`.
Trong 140 sản phẩm không có giá, 140 là điểm công cộng không bán vé (không có giá là đúng); phần còn lại mới là thiếu giá cần đối chiếu nguồn.

## Điểm đến × loại sản phẩm

| Điểm đến | hotel | flight | attraction | combo | golf | tổng |
|---|---|---|---|---|---|---|
| Nha Trang | 144 | 23 | 63 | 19 | 1 | 250 |
| Phú Quốc | 112 | 37 | 67 | 26 | 1 | 243 |
| Hà Nội | 87 | 33 | 68 | 13 | 0 | 201 |
| Hải Phòng | 126 | 16 | 25 | 8 | 1 | 176 |
| TP. Hồ Chí Minh | 99 | 42 | 21 | 1 | 1 | 164 |
| Đà Nẵng | 93 | 34 | 10 | 0 | 0 | 137 |
| Hội An | 101 | 0 | 23 | 8 | 1 | 133 |
| Nghệ An | 77 | 17 | 27 | 11 | 0 | 132 |
| Đà Lạt | 96 | 16 | 18 | 0 | 0 | 130 |
| Huế | 97 | 14 | 17 | 0 | 0 | 128 |
| Quy Nhơn | 90 | 12 | 16 | 0 | 0 | 118 |
| Phan Thiết | 98 | 0 | 16 | 0 | 1 | 115 |
| Sa Pa | 89 | 0 | 17 | 0 | 0 | 106 |
| Hà Tĩnh | 83 | 0 | 3 | 7 | 0 | 93 |
| Hạ Long | 51 | 0 | 16 | 0 | 0 | 67 |
| Bắc Ninh *(ngoài kế hoạch)* | 7 | 0 | 0 | 0 | 0 | 7 |
| Thanh Hóa *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Quảng Bình *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Ninh Bình *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Tây Ninh *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |

## Theo nguồn

- booking: 1092
- trip: 453
- vinpearl: 428
- agoda: 243

## Theo loại / cấp

- attraction/-: 407
- combo/-: 93
- flight/flight: 184
- flight/route: 60
- golf/-: 6
- hotel/property: 559
- hotel/room: 907

Độ dài mô tả trung vị: 741 ký tự

## Bị loại

- biến thể giá thành viên Vinpearl (đã gộp, giá từng hạng giữ trong memberPrices): 53
- khách sạn trùng giữa các nguồn (đã gộp): 49
- không có giá và nguồn không cung cấp được (không đặt được): 48
- đã soát tay và loại (collectors/excluded_products.csv): 10
- điểm tham quan trip.com trùng vé Vinpearl (đã gộp): 4
- room của sản phẩm bị loại: 2
- tuyến bay ngoài kế hoạch: 1
- booking: vượt 30/điểm đến: 1
- flight của sản phẩm bị loại: 1

## Vị trí (toạ độ)

| Loại / cấp | Sản phẩm | Có toạ độ | |
|---|---|---|---|
| attraction/- | 407 | 407 | 100.0% |
| combo/- | 93 | 93 | 100.0% |
| flight/flight | 184 | 184 | 100.0% |
| flight/route | 60 | 60 | 100.0% |
| golf/- | 6 | 6 | 100.0% |
| hotel/property | 559 | 559 | 100.0% |
| hotel/room | 907 | 907 | 100.0% |

Nguồn toạ độ: booking.com 1137, trip.com 404, ourairports 244, agoda.com 240, vinpearl 86, manual 53, osm 52

Độ chính xác: exact 1675, venue 297, airport 244 (exact = vị trí riêng của sản phẩm; venue = khu vui chơi/sân golf dùng vé; poi = điểm tham quan trip.com; airport = sân bay đến)

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

Bản đồ: 796 ghim trong `map/` (mymaps-khach-san.csv, mymaps-vui-choi.csv, mymaps-san-bay.csv, places.geojson). Cần kiểm tra tay: 30 dòng trong `map/can-kiem-tra.csv`.

## Mẫu để đọc tay (kiểm tra chất lượng tên + mô tả)

- **Hòn Tằm Resort** · hotel · Nha Trang · 2219215 VND  
  Với vẻ đẹp của thiên nhiên kết hợp cùng kiến trúc bungalow và villa sang trọng, Hòn Tằm Resort Nha Trang mang đến cho du khách một kỳ nghỉ đẳng cấp, riêng tư và ấn tượng khó quên. Khu nghỉ dưỡng được bao phủ bởi cảnh quan xanh mát, yên ả của rừng và biển giúp thư giãn cả cơ thể l
- **Vé Hạng Lạc Hồng | Trải nghiệm Gondola, Aquafield & Set Ẩm thực** · attraction · Hà Nội · 1530000 VND  
  Vé Hạng Lạc Hồng | Trải nghiệm Gondola, Aquafield & Set Ẩm thực  ► Vui lòng tham khảo sơ đồ chỗ ngồi trước khi đặt vé.  Phù hợp: Nhóm bạn, Gia đình, Cặp đôi. Địa điểm: Hà Nội. Giá từ 1.530.000₫
- **[Nam Hội An Signature] Vé vào cửa & Gói VIP Tour Safari | TẶNG quà Safari** · combo · Hội An · 785000 VND  
  [Nam Hội An Signature] Vé vào cửa & Gói VIP Tour Safari | TẶNG quà Safari  Vé vào cửa trực tiếp khu vui chơi VinWonders Nam Hội An sử dụng trong ngày dành cho 01 người  Bao gồm Vé vào cửa trực tiếp khu vui chơi VinWonders Nam Hội An sử dụng trong ngày dành cho 01 người
- **[02 ngày không giới hạn] - VinWonders + Vinpearl Safari Phú Quốc + Bảo Tàng Gấu Teddy** · attraction · Phú Quốc · 2040000 VND  
  [02 ngày không giới hạn] - VinWonders + Vinpearl Safari Phú Quốc + Bảo Tàng Gấu Teddy  - Combo vé tiêu chuẩn vào cửa trực tiếp VinWonders và Vinpearl Safari Phú Quốc trong 02 ngày (ra vào không giới hạn) - Tặng 01 Vé Bảo Tàng Gấu cho mỗi vé  Bao gồm - Combo vé tiêu chuẩn vào cửa 
- **[Vinpearl Horse Academy] - Tour tham quan "Mái nhà của ngựa"** · attraction · Hải Phòng · 150000 VND  
  [Vinpearl Horse Academy] - Tour tham quan "Mái nhà của ngựa"  Phù hợp: Nhóm bạn, Gia đình, Cặp đôi, Doanh nhân. Địa điểm: Hải Phòng. Giá từ 150.000₫
- **Vé máy bay Đà Lạt - Phú Quốc** · flight · Phú Quốc · 1046000 VND  
  Vé máy bay một chiều từ Đà Lạt (DLI) đến Phú Quốc (PQC). Hãng khai thác: VietJet Air, Vietnam Airlines, Sun PhuQuoc Airways. Thời gian bay khoảng 4 giờ 45 phút. Giá một chiều từ 1.046.000₫, khứ hồi từ 2.947.000₫.
- **Hotel Nikko Hai Phong** · hotel · Hải Phòng · 1973098 VND  
  Chỗ Nghỉ Thanh Lịch: Hotel Nikko Hải Phòng mang đến trải nghiệm 5 sao với các tiện nghi spa, trung tâm thể dục, khu vườn xanh tươi, hồ bơi ngoài trời và WiFi miễn phí.  Tiện Nghi Thoải Mái: Khách được hưởng quyền lợi nhận phòng và trả phòng riêng, quầy lễ tân 24 giờ, dịch vụ conc
- **Huệ Vinh Hotel** · hotel · Nghệ An · 350000 VND  
  Nằm ở Cửa Lò, cách Bãi biển Cửa Lò, Huệ Vinh Hotel cung cấp điều hòa chỗ nghỉ Và sân hiên. Chỗ nghỉ này có các tiện nghi như nhà hàng, dịch vụ phòng và quầy lễ tân 24 giờ, cùng với Wi-Fi miễn phí ở toàn bộ chỗ nghỉ. Khách sạn có phòng gia đình.  Tại khách sạn, các phòng được thiế
- **Seaside Boutique Resort Quy Nhon** · hotel · Quy Nhơn · 976933 VND  
  Vị trí bên bờ biển tuyệt vời: Seaside Boutique Resort Quy Nhon tại Quy Nhon cung cấp khu vực bãi biển riêng và lối đi thẳng ra bãi biển. Khách có thể thưởng thức tầm nhìn tuyệt đẹp ra biển và hồ bơi với cảnh quan đẹp.  Chỗ nghỉ thoải mái: Các phòng có điều hòa không khí, phòng tắ
- **Khách sạn & Spa Aqua (Aqua Hotel & Spa)** · hotel · Nha Trang · 325327 VND  
  Khách sạn & Spa Aqua tại Nha Trang: Tất cả những gì bạn cần biếtKhách sạn & Spa Aqua mang đến một điểm dừng chân hiện đại và thuận tiện tại Nha Trang, phù hợp cho cả chuyến công tác ngắn ngày lẫn kỳ nghỉ thư giãn bên gia đình. Được xây dựng mới vào năm 2024, khách sạn sở hữu 40 p
- **Khách sạn Alba Spa (Alba Spa Hotel)** · hotel · Huế · 1095238 VND  
  Khách sạn Alba Spa tại Huế: Tất cả những gì bạn cần biếtKhách sạn Alba Spa là điểm dừng chân lý tưởng ngay giữa lòng Huế, mang đến không gian thuận tiện và thư thái cho cả chuyến công tác ngắn ngày lẫn kỳ nghỉ khám phá văn hóa cố đô. Tọa lạc cách trung tâm thành phố 0 km, khách s
- **Muong Thanh Thanh Nien Hotel** · hotel · Nghệ An · 493541 VND  
  Muong Thanh Thanh Nien Hotel tại Vinh: Tất cả những gì bạn cần biếtMuong Thanh Thanh Nien Hotel mang đến điểm dừng chân thuận tiện và dễ chịu cho cả chuyến công tác lẫn hành trình khám phá Vinh, đặc biệt với vị trí chỉ cách trung tâm thành phố khoảng 1 km. Được xây dựng vào năm 2
- **Khách sạn boutique Palette Mũi Né (Palette Muine Boutique Hotel Near Mui Ne Beach)** · hotel · Phan Thiết · 988591 VND  
  Khách sạn boutique Palette Mũi Né tại Phan Thiết: Tất cả những gì bạn cần biếtKhách sạn boutique Palette Mũi Né mang đến một điểm dừng chân hiện đại và đầy cảm hứng tại Phan Thiết, phù hợp cho cả chuyến công tác ngắn ngày lẫn kỳ nghỉ thư giãn bên gia đình. Được xây dựng mới vào n
- **Quảng trường Lâm Viên** · attraction · Đà Lạt · None VND  
  Quảng trường Lâm Viên. Địa chỉ: Đ. Trần Quốc Toản, Xuân Hương - Đà Lạt, Lâm Đồng, Việt Nam. Giờ mở cửa: Mở cửa cả ngày. Thời gian tham quan đề xuất: 0.5–1 tiếng đồng hồ
- **Chùa Thiên Mụ** · attraction · Huế · None VND  
  Chùa Thiên Mụ. Loại hình: Thắng cảnh lịch sử. Địa chỉ: Kim Long, Huế 532761, Việt Nam. Giờ mở cửa: 07:00–17:30. Thời gian tham quan đề xuất: 1–2 tiếng đồng hồ
