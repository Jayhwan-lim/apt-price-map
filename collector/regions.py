"""LAWD_CD (first 5 digits of the legal-dong code) for Seoul and Gyeonggi.

Each entry: code -> (sido, sigungu, gu). `gu` is empty for cities without
general-purpose districts.

Two Gyeonggi cities changed their district structure inside our collection
window, so their codes are not fixed:
  * Bucheon (41190): districts restored in 2024.
  * Hwaseong (41590): four districts (Manse, Hyohaeng, Byeongjeom, Dongtan)
    launched in February 2026.
For these we always query the parent code AND any child codes discovered by
probing (see fetch.py), then de-duplicate trades. Complexes are keyed by the
parent ("stable") code so history does not break across the split.
"""

SEOUL = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}

# code -> (sigungu, gu)
GYEONGGI = {
    "41111": ("수원시", "장안구"), "41113": ("수원시", "권선구"),
    "41115": ("수원시", "팔달구"), "41117": ("수원시", "영통구"),
    "41131": ("성남시", "수정구"), "41133": ("성남시", "중원구"),
    "41135": ("성남시", "분당구"),
    "41150": ("의정부시", ""),
    "41171": ("안양시", "만안구"), "41173": ("안양시", "동안구"),
    "41190": ("부천시", ""),
    "41210": ("광명시", ""), "41220": ("평택시", ""), "41250": ("동두천시", ""),
    "41271": ("안산시", "상록구"), "41273": ("안산시", "단원구"),
    "41281": ("고양시", "덕양구"), "41285": ("고양시", "일산동구"),
    "41287": ("고양시", "일산서구"),
    "41290": ("과천시", ""), "41310": ("구리시", ""), "41360": ("남양주시", ""),
    "41370": ("오산시", ""), "41390": ("시흥시", ""), "41410": ("군포시", ""),
    "41430": ("의왕시", ""), "41450": ("하남시", ""),
    "41461": ("용인시", "처인구"), "41463": ("용인시", "기흥구"),
    "41465": ("용인시", "수지구"),
    "41480": ("파주시", ""), "41500": ("이천시", ""), "41550": ("안성시", ""),
    "41570": ("김포시", ""), "41590": ("화성시", ""), "41610": ("광주시", ""),
    "41630": ("양주시", ""), "41650": ("포천시", ""), "41670": ("여주시", ""),
    "41800": ("연천군", ""), "41820": ("가평군", ""), "41830": ("양평군", ""),
}

# Parent code -> candidate child codes to probe (odd numbers by convention).
SPLIT_PROBES = {
    "41190": [str(c) for c in range(41191, 41200, 2)],
    "41590": [str(c) for c in range(41591, 41600, 2)],
}


def base_regions():
    """Return {code: (sido, sigungu, gu)} for every fixed code."""
    out = {code: ("서울특별시", name, "") for code, name in SEOUL.items()}
    out.update({code: ("경기도", sgg, gu) for code, (sgg, gu) in GYEONGGI.items()})
    return out


def stable_code(code):
    """Map a (possibly new child) code to the code used for complex identity."""
    for parent, children in SPLIT_PROBES.items():
        if code == parent or code in children:
            return parent
    return code
