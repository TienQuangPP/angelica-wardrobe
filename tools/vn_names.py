"""Vietnamese names for fashion sets.

1. Official names: the item mall (gshop) lists sets with their Vietnamese name and an icon named after the
   Chinese set ("图鉴2023年仙踪蝶舞女装128.dds"). Icons and model folders spell sets differently
   (年, zodiac years for Tết sets, homophones), so names are matched loosely.
2. Everything else gets a word-by-word translation of its Chinese folder name (marked as translated).
"""
from __future__ import annotations

import csv
import difflib
import re
from pathlib import Path

ZODIAC = {2014: "马", 2015: "羊", 2016: "猴", 2017: "鸡", 2018: "狗", 2019: "猪", 2020: "鼠", 2021: "牛",
          2022: "虎", 2023: "兔", 2024: "龙", 2025: "蛇"}
NOISE = re.compile(r"[男女装服套的款系列时年]|原色|变色|图鉴|新品|一级")
SLOT = re.compile(r"(上衣|下衣|裤子|鞋子|护腕|手套|靴子|裙子|头发|头饰)$")


def normalize(name: str) -> str:
    s = re.sub(r"(128\d*|大|\d{3,})$", "", name)
    s = re.sub(r"(128\d*|大)$", "", s)
    s = SLOT.sub("", s.replace("图鉴", ""))
    # "2023年兔年" (zodiac year) and "2023春节" are the same Tết set
    m = re.match(r"(20\d\d)年?(.)年", s)
    if m and ZODIAC.get(int(m.group(1))) == m.group(2):
        s = m.group(1) + "春节" + s[m.end():]
    s = NOISE.sub("", s)
    s = re.sub(r"^(?:GM)?20(\d\d)", r"\1", s)
    return re.sub(r"[衣裙群服\-]+$", "", s)


def year(s: str) -> str:
    m = re.match(r"(\d{2})(?!\d)", s)
    return m.group(1) if m else ""


def score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if year(a) and year(b) and year(a) != year(b):
        return 0.0
    if a == b:
        return 1.0
    core_a, core_b = re.sub(r"^\d{2}", "", a), re.sub(r"^\d{2}", "", b)
    if core_a == core_b and len(core_a) >= 2:
        return 0.95
    if min(len(core_a), len(core_b)) >= 3 and (core_a in core_b or core_b in core_a):
        return 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def load_shop(catalog_csv: Path) -> list[tuple[str, str, str, Path, str]]:
    """[(gender, normalized icon name, Vietnamese name, icon png, item id)] for clothing sets in the mall."""
    genders = {"Thời trang nam": "男", "Thời trang nữ": "女"}
    out = []
    with open(catalog_csv, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            g = genders.get(r["Danh mục"])
            if not g:
                continue
            stem = Path(r["Icon"].replace("\\", "/")).stem
            out.append((g, normalize(stem), r["Tên"].strip(), catalog_csv.parent / r["PNG"] if r["PNG"] else None,
                        r["ID vật phẩm"]))
    return out


def match_shop(set_name: str, gender: str, shop: list) -> tuple | None:
    key = normalize(set_name)
    best, best_s = None, 0.0
    for g, norm, vn, png, item in shop:
        if g != gender:
            continue
        s = score(key, norm)
        if s > best_s:
            best, best_s = (vn, png, item), s
    if best_s < 0.85:
        return None
    # a few mall entries are named after one piece ("Tóc …", "Giày …") but stand for the whole set
    vn = re.sub(r"^(Tóc|Giày|Áo|Quần|Váy|Găng)\s+", "Bộ ", best[0])
    return (vn, *best[1:])


# Chinese -> Vietnamese words for translated names (longest match first)
WORDS = {
    "专用服装": "Trang phục riêng", "职业装": "Trang phục nghề", "工会战服": "Chiến bào bang hội", "礼服": "Lễ phục",
    "婚礼服": "Lễ phục cưới", "婚纱": "Váy cưới", "婚礼": "Hôn lễ", "西式": "kiểu Tây", "中式": "kiểu Trung",
    "圣诞节": "Giáng Sinh", "圣诞": "Giáng Sinh", "春节": "Tết", "情人节": "Lễ Tình Nhân", "七夕": "Thất Tịch",
    "中秋": "Trung Thu", "端午": "Đoan Ngọ", "元宵": "Nguyên Tiêu", "新年": "Năm Mới", "万圣节": "Halloween",
    "周年": "năm kỷ niệm", "纪念版": "bản kỷ niệm", "纪念": "kỷ niệm", "原色": "nguyên sắc", "变色": "đổi màu",
    "固定色": "màu cố định", "盲盒": "Hộp mù", "媒卡": "Media", "媒体": "Media", "球衣": "Áo bóng đá",
    "战场装": "Chiến trường", "战场": "Chiến trường", "格斗场": "Đấu trường", "制霸装": "Chế Bá", "制霸": "Chế Bá",
    "军装": "Quân phục", "校服": "Đồng phục", "制服": "Chế phục", "套装": "Bộ", "套裙": "Váy bộ", "泳装": "Đồ bơi",
    "比基尼": "Bikini", "和服": "Kimono", "旗袍": "Sườn xám", "古装": "Cổ trang", "古风": "Cổ phong", "汉服": "Hán phục",
    "唐装": "Đường trang", "宫廷": "Cung đình", "拉拉队": "Cổ vũ", "玩偶": "Búp bê", "仲夏": "Giữa hè", "夏日": "Ngày hè",
    "冬季": "Mùa đông", "嘻哈": "Hip-hop", "牛仔": "Denim", "豹纹": "Da báo", "皮衣": "Áo da", "毛衣": "Áo len",
    "吊带": "Hai dây", "抹胸裙": "Váy quây", "抹胸": "Quây ngực", "印花": "In hoa", "半透": "Bán trong suốt",
    "暗色": "Tối màu", "休闲": "Thường ngày", "时尚": "Thời thượng", "清凉": "Mát mẻ", "可爱": "Đáng yêu",
    "俏皮": "Tinh nghịch", "唯美": "Duy mỹ", "甜心": "Ngọt ngào", "定制": "Đặt riêng", "完美": "Hoàn Mỹ",
    "祖龙": "Tổ Long", "郡主": "Quận chúa", "公主": "Công chúa", "王子": "Hoàng tử", "女王": "Nữ hoàng",
    "公爵": "Công tước", "女仆": "Hầu gái", "护士": "Y tá", "忍者": "Ninja", "海盗": "Hải tặc", "骑士": "Kỵ sĩ",
    "天使": "Thiên thần", "恶魔": "Ác ma", "精灵": "Tinh linh", "新娘": "Cô dâu", "伴娘": "Phù dâu", "少女": "Thiếu nữ",
    "少年": "Thiếu niên", "舞会": "Vũ hội", "夜幕": "Màn đêm", "学院": "Học viện", "运动": "Thể thao", "东方不败": "Đông Phương Bất Bại",
    "小乔": "Tiểu Kiều", "中国风": "Phong Trung Hoa", "威尼斯狂欢": "Lễ hội Venice", "印第安": "Da đỏ", "埃及": "Ai Cập",
    "印度": "Ấn Độ", "俄罗斯": "Nga", "巴西": "Brazil", "德国": "Đức", "意大利": "Ý", "法国": "Pháp", "荷兰": "Hà Lan",
    "葡萄牙": "Bồ Đào Nha", "西班牙": "Tây Ban Nha", "阿根廷": "Argentina", "英伦": "Anh quốc", "剑灵": "Kiếm Linh",
    "魅灵": "Mị Linh", "刺客": "Thích Khách", "巫师": "Vu Sư", "法师": "Pháp Sư", "武侠": "Võ Hiệp", "羽灵": "Vũ Linh",
    "羽芒": "Vũ Mang", "夜影": "Dạ Ảnh", "月仙": "Nguyệt Tiên", "妖精": "Yêu Tinh", "妖兽": "Yêu Thú", "琴剑": "Cầm Kiếm",
    "熊猫": "Gấu trúc", "天鹅": "Thiên nga", "青蛙": "Ếch", "小鸟": "Chim nhỏ", "兔女郎": "Thỏ nữ lang", "蝴蝶": "Hồ điệp",
    "草莓": "Dâu tây", "樱桃": "Anh đào", "柠檬": "Chanh", "菠萝": "Dứa", "西瓜": "Dưa hấu", "香蕉": "Chuối",
    "苹果": "Táo", "葡萄": "Nho", "冰淇淋": "Kem", "蛋糕": "Bánh kem", "奶昔": "Sữa lắc", "南瓜": "Bí ngô",
    "向日葵": "Hướng dương", "玫瑰": "Hoa hồng", "樱花": "Hoa anh đào", "荷花": "Hoa sen", "百合": "Bách hợp",
    "百花": "Bách Hoa", "翅膀": "Cánh", "流萤": "Đom đóm", "星河": "Ngân hà", "璀璨": "Rực rỡ", "仙踪": "Tiên Tung",
    "蝶舞": "Điệp Vũ", "黄金": "Hoàng Kim", "白银": "Bạch Ngân", "钻石": "Kim cương", "蓝宝石": "Lam bảo thạch",
    "宝石": "Bảo thạch", "水晶": "Thủy tinh", "珍珠": "Trân châu", "雪之女王": "Nữ hoàng Tuyết", "冰雪": "Băng tuyết",
    "黑色": "đen", "白色": "trắng", "红色": "đỏ", "粉色": "hồng", "蓝色": "xanh lam", "绿色": "xanh lục", "紫色": "tím",
    "黄色": "vàng", "双色": "hai màu", "猫": "Mèo", "兔": "Thỏ", "狐": "Hồ ly", "熊": "Gấu", "猪": "Heo", "狗": "Chó",
    "鼠": "Chuột", "虎": "Hổ", "牛": "Trâu", "羊": "Cừu", "猴": "Khỉ", "鸡": "Gà", "鸭": "Vịt", "鹿": "Hươu",
    "龙": "Rồng", "凤": "Phượng", "蛇": "Rắn", "狮": "Sư tử", "鸟": "Chim", "花": "Hoa", "雪": "Tuyết", "冰": "Băng",
    "星": "Sao", "月": "Nguyệt", "仙": "Tiên", "侠": "Hiệp", "叶子": "Lá", "糖": "Kẹo", "喜": "Hỷ", "裙": "Váy",
    "短裤": "Quần short", "国服": "Quốc phục", "风情": "Phong tình",
}
DROP = re.compile(r"时装|服装|装|新九军|九军")
_KEYS = sorted(WORDS, key=len, reverse=True)


def translate(name: str) -> str | None:
    """Word-by-word Vietnamese rendering of a Chinese set name, or None if too much stays untranslated."""
    yr = re.match(r"^(20)?(\d{2})(年)?", name)
    rest = name[yr.end():] if yr else name
    rest = re.sub(r"^[ab](?=[一-鿿])", "", rest)
    words, i, unknown = [], 0, 0
    while i < len(rest):
        for k in _KEYS:
            if rest.startswith(k, i):
                words.append(WORDS[k])
                i += len(k)
                break
        else:
            ch = rest[i]
            if DROP.match(rest, i):
                i += DROP.match(rest, i).end() - i
                continue
            if ch in "男女":
                i += 1
                continue
            if ch.isdigit() or ch.isascii():
                words.append(ch)
            else:
                unknown += 1
            i += 1
    text = " ".join(w for w in words if w).replace(" ,", ",")
    text = re.sub(r"(\d) (?=\d)", r"\1", text).strip()
    if not text or unknown > max(1, len(rest) // 4):
        return None
    if yr:
        text += f" ({'20' if len(yr.group(2)) == 2 else ''}{yr.group(2)})"
    return text[0].upper() + text[1:]
