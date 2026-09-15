"""Chuẩn hoá điểm đến: gom tên thành phố/phường/tỉnh/địa danh về một tên điểm đến thống nhất."""

from __future__ import annotations

import re

from .textutil import fold

# Tên chuẩn → các cách viết thường gặp (so khớp không dấu, theo ranh giới từ).
# Thứ tự trong dict không quan trọng: alias dài/cụ thể được thử trước.
DESTINATION_ALIASES: dict[str, list[str]] = {
    "Nha Trang": ["nha trang", "cam ranh", "hon tre", "hon tam", "vinwonders nha trang", "bai dai cam ranh", "khanh hoa"],
    "Phú Quốc": ["phu quoc", "duong dong", "an thoi", "ganh dau", "bai truong", "ham ninh", "cua can", "grand world", "kien giang"],
    "Hạ Long": ["ha long", "halong", "bai chay", "tuan chau", "hon gai", "quang ninh"],
    "Hội An": ["hoi an", "nam hoi an", "cua dai", "an bang", "thang binh", "duy xuyen", "dien ban", "quang nam"],
    "Đà Nẵng": ["da nang", "danang", "son tra", "ngu hanh son", "my khe", "ba na", "bana hills", "hai chau", "lien chieu", "thanh khe", "hoa vang"],
    "Hà Nội": ["ha noi", "hanoi", "hoan kiem", "ba dinh", "tay ho", "long bien", "cau giay", "dong da", "hai ba trung", "times city", "ocean park", "gia lam"],
    "TP. Hồ Chí Minh": ["ho chi minh", "tp hcm", "hcmc", "sai gon", "saigon", "thu duc", "binh thanh", "phu nhuan", "tan binh", "go vap", "can gio", "district 1", "quan 1"],
    "Đà Lạt": ["da lat", "dalat", "lam dong"],
    "Sa Pa": ["sa pa", "sapa", "lao cai"],
    "Huế": ["hue", "thua thien", "lang co"],
    "Quy Nhơn": ["quy nhon", "nhon ly", "ky co", "binh dinh"],
    "Phan Thiết": ["phan thiet", "mui ne", "ham tien", "ke ga", "binh thuan"],
    "Vũng Tàu": ["vung tau", "ba ria", "long hai", "ho tram"],
    "Côn Đảo": ["con dao", "con son"],
    "Cần Thơ": ["can tho"],
    "Hải Phòng": ["hai phong", "cat ba", "do son", "vinhomes imperia"],
    "Ninh Bình": ["ninh binh", "trang an", "tam coc", "hoa lu", "bai dinh"],
    "Quảng Bình": ["quang binh", "dong hoi", "phong nha"],
    "Nghệ An": ["nghe an", "cua lo", "cua hoi", "thanh pho vinh", "tp vinh"],
    "Hà Tĩnh": ["ha tinh", "cua sot", "thien cam"],
    "Bắc Ninh": ["bac ninh"],
    "Hà Giang": ["ha giang", "dong van", "meo vac"],
    "Mộc Châu": ["moc chau"],
    "Tam Đảo": ["tam dao"],
    "Tuy Hòa": ["tuy hoa", "phu yen"],
    "Phan Rang": ["phan rang", "ninh thuan", "vinh hy"],
    "Quảng Ngãi": ["quang ngai", "ly son"],
    "Buôn Ma Thuột": ["buon ma thuot", "dak lak"],
    "Hà Nam": ["ha nam", "tam chuc"],
    "Thanh Hóa": ["thanh hoa", "sam son"],
    "Mai Châu": ["mai chau", "hoa binh"],
    "Cao Bằng": ["cao bang", "ban gioc"],
    "Rạch Giá": ["rach gia", "ha tien"],
    "Châu Đốc": ["chau doc", "an giang"],
}

_ALIAS_TABLE: list[tuple[re.Pattern, str]] = sorted(
    (
        (re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"), canonical)
        for canonical, aliases in DESTINATION_ALIASES.items()
        for alias in aliases
    ),
    key=lambda x: -len(x[0].pattern),
)


def normalise_destination(*candidates: str | None) -> str | None:
    """Thử lần lượt các chuỗi (cụ thể nhất trước: thành phố → địa chỉ → tỉnh → tên).
    Không khớp alias nào thì trả lại chuỗi đầu tiên không rỗng, để không mất thông tin."""
    for c in candidates:
        f = fold(c)
        if not f:
            continue
        for pat, canonical in _ALIAS_TABLE:
            if pat.search(f):
                return canonical
    for c in candidates:
        if c and c.strip():
            return c.strip()
    return None
