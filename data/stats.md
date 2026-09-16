# Thống kê catalog

Tạo lúc 2026-09-16 · **2327 sản phẩm**

## Đối chiếu handbook §3

| Mục tiêu | Thực tế | |
|---|---|---|
| 2.000–5.000 sản phẩm | 2327 | ✅ |
| 10–15 điểm đến (≥ 20 sản phẩm mỗi nơi) | 15 | ✅ |
| Đủ hotel, flight, attraction, combo | attraction, combo, flight, golf, hotel | ✅ |
| Mô tả được nhận diện là tiếng Việt | 2275 (97.8%) | ✅ |
| Có giá | 2130 (91.5%) | ✅ |
| Được đánh dấu available trong dữ liệu | 2129 (91.5%) | |
| Có toạ độ | 2255 (96.9%) | |
| Sản phẩm trùng giữa các nguồn đã gộp | 53 | |

Nhãn ngôn ngữ được ước lượng từ tỷ lệ ký tự có dấu trong mô tả; không xác nhận tên hoặc toàn bộ nội dung đã là tiếng Việt. Cần đọc tay các mẫu bên dưới.
Cờ available được suy ra từ dữ liệu nguồn và giá tại thời điểm crawl; chưa xác minh đặt chỗ hiện tại. Các trường còn thiếu được liệt kê trong `quality_review.csv`.

## Điểm đến × loại sản phẩm

| Điểm đến | hotel | flight | attraction | combo | golf | tổng |
|---|---|---|---|---|---|---|
| Phú Quốc | 114 | 37 | 87 | 32 | 1 | 271 |
| Nha Trang | 144 | 23 | 67 | 22 | 1 | 257 |
| Hà Nội | 87 | 33 | 75 | 17 | 0 | 212 |
| Hải Phòng | 131 | 16 | 28 | 15 | 1 | 191 |
| TP. Hồ Chí Minh | 100 | 42 | 23 | 3 | 1 | 169 |
| Nghệ An | 80 | 17 | 35 | 17 | 0 | 149 |
| Hội An | 102 | 0 | 31 | 8 | 1 | 142 |
| Đà Nẵng | 95 | 34 | 10 | 0 | 0 | 139 |
| Huế | 99 | 14 | 18 | 0 | 0 | 131 |
| Đà Lạt | 97 | 16 | 18 | 0 | 0 | 131 |
| Quy Nhơn | 91 | 12 | 18 | 0 | 0 | 121 |
| Phan Thiết | 98 | 0 | 17 | 0 | 1 | 116 |
| Sa Pa | 89 | 0 | 18 | 0 | 0 | 107 |
| Hà Tĩnh | 86 | 0 | 5 | 7 | 0 | 98 |
| Hạ Long | 53 | 0 | 17 | 0 | 0 | 70 |
| Bắc Ninh *(ngoài kế hoạch)* | 7 | 0 | 0 | 0 | 0 | 7 |
| Thanh Hóa *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Quảng Bình *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Ninh Bình *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |
| Tây Ninh *(ngoài kế hoạch)* | 4 | 0 | 0 | 0 | 0 | 4 |

## Theo nguồn

- booking: 1092
- vinpearl: 508
- trip: 461
- agoda: 266

## Theo loại / cấp

- attraction/-: 467
- combo/-: 121
- flight/flight: 184
- flight/route: 60
- golf/-: 6
- hotel/property: 582
- hotel/room: 907

Độ dài mô tả trung vị: 826 ký tự

## Bị loại

- khách sạn trùng giữa các nguồn (đã gộp): 49
- điểm tham quan trip.com trùng vé Vinpearl (đã gộp): 4
- room của sản phẩm bị loại: 2
- tuyến bay ngoài kế hoạch: 1
- booking: vượt 30/điểm đến: 1
- flight của sản phẩm bị loại: 1

## Vị trí (toạ độ)

| Loại / cấp | Sản phẩm | Có toạ độ | |
|---|---|---|---|
| attraction/- | 467 | 411 | 88.0% |
| combo/- | 121 | 109 | 90.1% |
| flight/flight | 184 | 184 | 100.0% |
| flight/route | 60 | 60 | 100.0% |
| golf/- | 6 | 5 | 83.3% |
| hotel/property | 582 | 579 | 99.5% |
| hotel/room | 907 | 907 | 100.0% |

Nguồn toạ độ: booking.com 1137, osm 305, agoda.com 263, ourairports 244, trip.com 219, vinpearl 86, manual 1

Độ chính xác: exact 1703, venue 306, airport 244, poi 2 (exact = vị trí riêng của sản phẩm; venue = khu vui chơi/sân golf dùng vé; poi = điểm tham quan trip.com; airport = sân bay đến)

- vé có toạ độ địa điểm: 306
- vé thuộc địa điểm chưa có toạ độ dùng được: 71
- điểm đến sửa theo bằng chứng (destination_overrides.csv): 14
- khách sạn: toạ độ xa tâm điểm đến: 10
- khách sạn: trùng toạ độ khách sạn khác: 4
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

Bản đồ: 825 ghim trong `map/` (mymaps-khach-san.csv, mymaps-vui-choi.csv, mymaps-san-bay.csv, places.geojson). Cần kiểm tra tay: 34 dòng trong `map/can-kiem-tra.csv`.

## Mẫu để đọc tay (kiểm tra chất lượng tên + mô tả)

- **Hòn Tằm Resort** · hotel · Nha Trang · 2219215 VND  
  Với vẻ đẹp của thiên nhiên kết hợp cùng kiến trúc bungalow và villa sang trọng, Hòn Tằm Resort Nha Trang mang đến cho du khách một kỳ nghỉ đẳng cấp, riêng tư và ấn tượng khó quên. Khu nghỉ dưỡng được bao phủ bởi cảnh quan xanh mát, yên ả của rừng và biển giúp thư giãn cả cơ thể l
- **[VIN33 - Platinum] - [VinWonders Nam Hội An] Vé vào cửa tiêu chuẩn | TẶNG Voucher Ẩm thực** · attraction · Hội An · 591500 VND  
  LƯU Ý QUAN TRỌNG: Vui lòng lựa chọn ngày sử dụng và kiểm tra kỹ thông tin ngày sử dụng trong quá trình đặt vé. Vé vào cửa trực tiếp khu vui chơi VinWonders Nam Hội An sử dụng trong ngày dành cho 01 người Vé chỉ có hiệu lực 01 lần trong thời gian sử dụng ghi trên vé Vé không được 
- **[Người địa phương] - Cáp Treo 2 Chiều - Cửa Hội** · attraction · Nghệ An · 140000 VND  
  IMPORTANT NOTE: Please select your preferred usage date and carefully check the date information during the booking process. - Direct entry ticket to VinWonders Cua Hoi amusement park for same-day use. - Ticket valid for single use within the specified usage period. - Tickets are
- **[Jumbo 10] - Combo 10 buổi Jjimjilbang tiêu chuẩn + TẶNG 02 buổi** · combo · Hà Nội · 6000000 VND  
  ► Jjimjilbang là tổ hợp xông hơi trị liệu truyền thống và đặc trưng của Hàn Quốc với các bồn tắm nóng xen kẽ các bồn tắm lạnh và các phòng xông khô sử dụng các nguyên liệu chuyên dụng khác nhau để mang lại hiệu quả thải độc cơ thể, thư giãn. ► Ra đời từ thời đại Joseon (khoảng cu
- **[Vinpearl Safari Phú Quốc] - Vé Vào Cửa Tiêu Chuẩn + Tặng Voucher Ẩm Thực** · attraction · Phú Quốc · 850000 VND  
  LƯU Ý QUAN TRỌNG: Vé chỉ có hiệu lực 1 lần trong thời gian sử dụng ghi trên vé. Vui lòng lựa chọn ngày sử dụng và kiểm tra kỹ thông tin ngày sử dụng trong quá trình đặt vé. Vé vào cửa trực tiếp khu vui chơi Vinpearl Safari Phú Quốc sử dụng trong ngày dành cho 01 người Vé chỉ có h
- **Vé máy bay Phú Quốc - Hà Nội** · flight · Hà Nội · 632000 VND  
  Vé máy bay một chiều từ Phú Quốc (PQC) đến Hà Nội (HAN). Hãng khai thác: VietJet Air, Sun PhuQuoc Airways. Thời gian bay khoảng 1 giờ 55 phút. Giá một chiều từ 632.000₫, khứ hồi từ 1.274.000₫. Tháng có giá trung bình rẻ nhất: 2027-01.
- **Em's House Hoi An Homestay 2** · hotel · Hội An · 995490 VND  
  Em's House Hoi An Homestay 2 tọa lạc ở Hội An.  Được thiết kế với ban công, các căn có điều hòa, TV màn hình phẳng, cùng phòng tắm riêng gồm vòi xịt/chậu rửa vệ sinh và đồ vệ sinh cá nhân miễn phí. Tủ lạnh và ấm đun nước đều được cung cấp.  Sân bay Quốc tế Đà Nẵng cách 26 km.
- **La Vela Saigon Hotel** · hotel · TP. Hồ Chí Minh · 3261901 VND  
  Chỗ Nghỉ Thanh Lịch: La Vela Saigon Hotel tại Thành phố Hồ Chí Minh mang đến trải nghiệm 5 sao với hồ bơi trên sân thượng, trung tâm thể dục, sân phơi nắng, nhà hàng, quầy bar và WiFi miễn phí.  Tiện Nghi Thoải Mái: Khách có thể tận hưởng phòng chờ, bồn tắm công cộng, phòng xông 
- **Hue Serene Palace Hotel** · hotel · Huế · 712800 VND  
  Hue Serene Palace Hotel tọa lạc ở Huế. Khách sạn 2 sao này có dịch vụ tiền sảnh và bàn bán tour. Chỗ nghỉ cung cấp lễ tân 24/24, dịch vụ đưa đón sân bay, dịch vụ phòng và Wi-Fi miễn phí ở toàn bộ chỗ nghỉ.  Khách sạn sẽ cung cấp cho khách các phòng được trang bị điều hòa có bàn l
- **Premier Residences Phu Quoc Managed by Diamond Suite** · hotel · Phú Quốc · 3400000 VND  
  Nhìn ra thành phố, Premier Residences Phu Quoc Managed by Diamond Suite nằm ở Phú Quốc và có nhà hàng, phòng chờ chung, quầy bar, khu vườn, hồ bơi ngoài trời mở quanh năm cũng như sân hiên. WiFi và chỗ đậu xe riêng đều có sẵn tại căn hộ miễn phí.  Được thiết kế với ban công, các 
- **CONIHOUSE - Homestay & Villa** · hotel · Huế · 413603 VND  
  CONIHOUSE - Homestay & Villa tại Huế: Tất cả những gì bạn cần biếtCONIHOUSE - Homestay & Villa mang đến một không gian lưu trú riêng tư và gần gũi tại Huế, phù hợp cho những chuyến công tác cần sự yên tĩnh lẫn kỳ nghỉ thư thả muốn khám phá nét duyên dáng của cố đô. Với chỉ 1 phòn
- **Khách sạn Gallant 154 - Gần sân bay Cát Bi (Gallant Hotel 154 - Near Cat Bi Airport)** · hotel · Hải Phòng · 358554 VND  
  Khách sạn Gallant 154 - Gần sân bay Cát Bi tại Hải Phòng: Tất cả những gì bạn cần biếtKhách sạn Gallant 154 - Gần sân bay Cát Bi là điểm dừng chân lý tưởng tại Hải Phòng, mang đến sự thuận tiện cho cả chuyến công tác bận rộn lẫn kỳ nghỉ khám phá thành phố. Tọa lạc cách trung tâm 
- **Nhật's Sapa Central Hostel** · hotel · Sa Pa · 291005 VND  
  Trải Nghiệm Nghỉ Dưỡng Sang Trọng Tại Nhà riêng 100 m² 3 Phòng Ngủ, 7 Phòng Tắm Riêng Tại Trung Tâm SapaKhám phá không gian nghỉ dưỡng lý tưởng ngay trung tâm Sapa với Nhà riêng 100 m² gồm 3 phòng ngủ rộng rãi, phù hợp cho gia đình hoặc nhóm bạn thân. Mỗi phòng đều được trang bị 
- **Phố Đường Tàu Hà Nội** · attraction · Hà Nội · None VND  
  Phố Đường Tàu Hà Nội. Loại hình: Cảnh đêm. Địa chỉ: 3 Trần Phú, Hoàn Kiếm, Hà Nội 100000, Việt Nam. Giờ mở cửa: Mở cửa cả ngày. Thời gian tham quan đề xuất: 1–2 tiếng đồng hồ
- **Bãi trứng - khu du lịch Ghềnh Ráng** · attraction · Quy Nhơn · None VND  
  Bãi trứng - khu du lịch Ghềnh Ráng. Địa chỉ: P6R8+W8, Quy Nhơn Nam, Gia Lai, Việt Nam. Giờ mở cửa: 07:00–20:00
