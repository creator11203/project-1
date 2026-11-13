import feedparser
from datetime import datetime, timedelta
import time
import pytz
import json
import sqlite3
import random
import urllib.request
import urllib.parse
import re
from html.parser import HTMLParser

DB_NAME = "news.db"

def init_db():
    """SQLite 데이터베이스 및 테이블 초기화"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE,
            summary TEXT,
            content TEXT,
            category TEXT,
            location TEXT,
            lat REAL,
            lng REAL,
            time TEXT,
            source TEXT,
            link TEXT,
            timestamp REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_to_db(items):
    """수집된 기사를 SQLite DB에 안전하게 저장 (중복 방지)"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for item in items:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO news (title, summary, content, category, location, lat, lng, time, source, link, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['title'], item['summary'], item['content'], item['category'],
                item['location'], item['lat'], item['lng'], item['time'],
                item['source'], item['link'], item['timestamp']
            ))
        except Exception as e:
            print(f"DB 저장 오류: {e}")
    conn.commit()
    conn.close()

def export_db_to_json():
    """프론트엔드 연동을 위해 DB에서 최근 7일 데이터를 읽어 news.json으로 내보내기"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    kst = pytz.timezone('Asia/Seoul')
    cutoff_timestamp = (datetime.now(kst) - timedelta(days=7)).timestamp()
    cursor.execute('DELETE FROM news WHERE timestamp < ?', (cutoff_timestamp,))
    conn.commit()

    cursor.execute('SELECT * FROM news ORDER BY timestamp DESC LIMIT 300')
    rows = cursor.fetchall()
    
    news_list = [dict(row) for row in rows]
    conn.close()

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=4)

class HTMLFilter(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.text = []

    def handle_data(self, d):
        self.text.append(d)

    def get_data(self):
        return ''.join(self.text)

def remove_html_tags(html_content):
    if not html_content:
        return ""
    f = HTMLFilter()
    f.feed(html_content)
    return re.sub(r'\s+', ' ', f.get_data()).strip()

def translate_to_korean(text):
    if not text:
        return ""
    try:
        encoded_text = urllib.parse.quote(text[:800])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q={encoded_text}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            translated = "".join([item[0] for item in res_data[0] if item[0]])
            return translated
    except Exception:
        return text

def extract_domain_source(url):
    if not url or "t.me" in url:
        return ""
    try:
        parsed_url = urllib.parse.urlparse(url)
        netloc = parsed_url.netloc.lower()
        netloc = re.sub(r'^www\.', '', netloc)
        
        domain_mapping = {
            'yna.co.kr': '연합뉴스',
            'news.google.com': 'Google News',
            'hankyung.com': '한국경제',
            'edaily.co.kr': '이데일리',
            'reuters.com': 'Reuters',
            'bloomberg.com': 'Bloomberg',
            'ft.com': 'Financial Times',
            'wsj.com': 'Wall Street Journal',
            'apnews.com': 'AP News',
            'bbc.com': 'BBC',
            'cnn.com': 'CNN'
        }
        for d, name in domain_mapping.items():
            if d in netloc:
                return name
        return netloc
    except Exception:
        return "외부 원문 기사"

RSS_FEEDS = [
    {"url": "https://www.yna.co.kr/rss/news.xml", "source": "연합뉴스"},
    {"url": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", "source": "Google News"},
    {"url": "https://news.google.com/rss/search?q=%EC%82%AC%EA%B3%A0+%EC%82%AC%EA%B1%B4+%ED%8F%AD%ED%96%89+%EA%B2%BD%EC%B0%B0&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (사건·사고)"}
]

TELEGRAM_CHANNELS = [
    {"url": "https://t.me/s/FastStockNews", "source": "FastStockNews"},
    {"url": "https://t.me/s/FastStockNewsUSA", "source": "FastStockNewsUSA"},
    {"url": "https://t.me/s/cahier_de_market", "source": "cahier_de_market"}
]

KR_CITY_COORDS = {
    "천안": {"lat": 36.8151, "lng": 127.1139, "label": "충청남도 천안시"},
    "아산": {"lat": 36.7898, "lng": 127.0018, "label": "충청남도 아산시"},
    "서산": {"lat": 36.7845, "lng": 126.4503, "label": "충청남도 서산시"},
    "당진": {"lat": 36.8898, "lng": 126.6459, "label": "충청남도 당진시"},
    "공주": {"lat": 36.4465, "lng": 127.1189, "label": "충청남도 공주시"},
    "보령": {"lat": 36.3335, "lng": 126.6129, "label": "충청남도 보령시"},
    "논산": {"lat": 36.1872, "lng": 127.0987, "label": "충청남도 논산시"},
    "홍성": {"lat": 36.6013, "lng": 126.6608, "label": "충청남도 홍성군"},
    "청주": {"lat": 36.6424, "lng": 127.4890, "label": "충청북도 청주시"},
    "충주": {"lat": 36.9910, "lng": 127.9259, "label": "충청북도 충주시"},
    "제천": {"lat": 37.1326, "lng": 128.1910, "label": "충청북도 제천시"},
    "대전": {"lat": 36.3504, "lng": 127.3845, "label": "대전광역시"},
    "세종": {"lat": 36.4800, "lng": 127.2890, "label": "세종특별자치시"},
    "수원": {"lat": 37.2636, "lng": 127.0286, "label": "경기도 수원시"},
    "성남": {"lat": 37.4200, "lng": 127.1267, "label": "경기도 성남시"},
    "분당": {"lat": 37.3827, "lng": 127.1189, "label": "경기도 성남시 분당구"},
    "용인": {"lat": 37.2411, "lng": 127.1776, "label": "경기도 용인시"},
    "고양": {"lat": 37.6584, "lng": 126.8320, "label": "경기도 고양시"},
    "일산": {"lat": 37.6584, "lng": 126.7700, "label": "경기도 고양시 일산"},
    "화성": {"lat": 37.1996, "lng": 126.8312, "label": "경기도 화성시"},
    "부천": {"lat": 37.5034, "lng": 126.7660, "label": "경기도 부천시"},
    "남양주": {"lat": 37.6360, "lng": 127.2165, "label": "경기도 남양주시"},
    "안산": {"lat": 37.3219, "lng": 126.8309, "label": "경기도 안산시"},
    "안양": {"lat": 37.3943, "lng": 126.9568, "label": "경기도 안양시"},
    "평택": {"lat": 36.9921, "lng": 127.1129, "label": "경기도 평택시"},
    "시흥": {"lat": 37.3800, "lng": 126.8029, "label": "경기도 시흥시"},
    "파주": {"lat": 37.7599, "lng": 126.7802, "label": "경기도 파주시"},
    "의정부": {"lat": 37.7381, "lng": 127.0337, "label": "경기도 의정부시"},
    "김포": {"lat": 37.6152, "lng": 126.7156, "label": "경기도 김포시"},
    "광주": {"lat": 35.1595, "lng": 126.8526, "label": "광주광역시"},
    "인천": {"lat": 37.4563, "lng": 126.7052, "label": "인천광역시"},
    "강남": {"lat": 37.5172, "lng": 127.0473, "label": "서울특별시 강남구"},
    "송파": {"lat": 37.5145, "lng": 127.1059, "label": "서울특별시 송파구"},
    "강서": {"lat": 37.5509, "lng": 126.8495, "label": "서울특별시 강서구"},
    "영등포": {"lat": 37.5264, "lng": 126.8962, "label": "서울특별시 영등포구"},
    "마포": {"lat": 37.5663, "lng": 126.9016, "label": "서울특별시 마포구"},
    "종로": {"lat": 37.5730, "lng": 126.9794, "label": "서울특별시 종로구"},
    "춘천": {"lat": 37.8813, "lng": 127.7298, "label": "강원특별자치도 춘천시"},
    "원주": {"lat": 37.3422, "lng": 127.9202, "label": "강원특별자치도 원주시"},
    "강릉": {"lat": 37.7519, "lng": 128.8761, "label": "강원특별자치도 강릉시"},
    "속초": {"lat": 38.2070, "lng": 128.5918, "label": "강원특별자치도 속초시"},
    "부산": {"lat": 35.1796, "lng": 129.0756, "label": "부산광역시"},
    "해운대": {"lat": 35.1631, "lng": 129.1636, "label": "부산광역시 해운대구"},
    "대구": {"lat": 35.8714, "lng": 128.6014, "label": "대구광역시"},
    "울산": {"lat": 35.5384, "lng": 129.3114, "label": "울산광역시"},
    "창원": {"lat": 35.2280, "lng": 128.6811, "label": "경상남도 창원시"},
    "김해": {"lat": 35.2285, "lng": 128.8894, "label": "경상남도 김해시"},
    "진주": {"lat": 35.1800, "lng": 128.1076, "label": "경상남도 진주시"},
    "거제": {"lat": 34.8806, "lng": 128.6211, "label": "경상남도 거제시"},
    "양산": {"lat": 35.3350, "lng": 129.0372, "label": "경상남도 양산시"},
    "포항": {"lat": 36.0190, "lng": 129.3435, "label": "경상북도 포항시"},
    "구미": {"lat": 36.1195, "lng": 128.3446, "label": "경상북도 구미시"},
    "경주": {"lat": 35.8562, "lng": 129.2247, "label": "경상북도 경주시"},
    "안동": {"lat": 36.5684, "lng": 128.7294, "label": "경상북도 안동시"},
    "전주": {"lat": 35.8242, "lng": 127.1480, "label": "전북특별자치도 전주시"},
    "익산": {"lat": 35.9483, "lng": 126.9576, "label": "전북특별자치도 익산시"},
    "군산": {"lat": 35.9677, "lng": 126.7366, "label": "전북특별자치도 군산시"},
    "여수": {"lat": 34.7604, "lng": 127.6622, "label": "전라남도 여수시"},
    "순천": {"lat": 34.9506, "lng": 127.4872, "label": "전라남도 순천시"},
    "목포": {"lat": 34.8118, "lng": 126.3922, "label": "전라남도 목포시"},
    "제주": {"lat": 33.4996, "lng": 126.5312, "label": "제주특별자치도"},
    "서귀포": {"lat": 33.2541, "lng": 126.5601, "label": "제주특별자치도 서귀포시"}
}

KR_PROVINCE_COORDS = {
    "서울": {"lat": 37.5665, "lng": 126.9780, "label": "서울특별시"},
    "경기": {"lat": 37.4138, "lng": 127.5183, "label": "경기도"},
    "강원": {"lat": 37.8228, "lng": 128.1555, "label": "강원특별자치도"},
    "충북": {"lat": 36.6357, "lng": 127.4917, "label": "충청북도"},
    "충남": {"lat": 36.5184, "lng": 126.8000, "label": "충청남도"},
    "전북": {"lat": 35.7175, "lng": 127.1530, "label": "전북특별자치도"},
    "전남": {"lat": 34.8679, "lng": 126.9910, "label": "전라남도"},
    "경북": {"lat": 36.4919, "lng": 128.8889, "label": "경상북도"},
    "경남": {"lat": 35.4606, "lng": 128.2132, "label": "경상남도"}
}

GLOBAL_COORDS = {
    "우크라이나": {"lat": 50.4501, "lng": 30.5234, "label": "우크라이나 키이우"},
    "러시아": {"lat": 55.7558, "lng": 37.6173, "label": "러시아 모스크바"},
    "이란": {"lat": 35.6892, "lng": 51.3890, "label": "이란 테헤란"},
    "이스라엘": {"lat": 31.7683, "lng": 35.2137, "label": "이스라엘 예루살렘"},
    "가자": {"lat": 31.5017, "lng": 34.4668, "label": "팔레스타인 가자지구"},
    "중동": {"lat": 24.7136, "lng": 46.6753, "label": "중동 지역"},
    "미국": {"lat": 38.8951, "lng": -77.0364, "label": "미국 워싱턴D.C."},
    "중국": {"lat": 39.9042, "lng": 116.4074, "label": "중국 베이징"},
    "대만": {"lat": 25.0330, "lng": 121.5654, "label": "대만 타이베이"},
    "일본": {"lat": 35.6762, "lng": 139.6503, "label": "일본 도쿄"},
    "북한": {"lat": 39.0392, "lng": 125.7625, "label": "북한 평양"}
}

WORLD_COUNTRIES = [
    "미국", "중국", "일본", "러시아", "우크라이나", "영국", "프랑스", "독일", "이탈리아", "캐나다",
    "호주", "인도", "대만", "이란", "이스라엘", "북한", "시리아", "이라크", "아프가니스탄", "파키스탄",
    "사우디", "예멘", "리비아", "수단", "소말리아", "레바논", "팔레스타인", "터키", "튀르키예", "폴란드",
    "필리핀", "베트남", "인도네시아", "태국", "미얀마", "브라질", "멕시코", "스페인", "스위스",
    "아르헨티나", "이집트", "남아공", "나이지리아", "베네수엘라", "쿠바", "벨라루스", "스웨덴", "노르웨이"
]

CONFLICT_KEYWORDS = [
    '공습', '미사일', '폭격', '전쟁', '테러', '무력 충돌', '군사 작전', '드론 공격', '충돌', 
    '포격', '격전', '교전', '침공', '점령', '군사 행동', '비상사태', '계엄', '테러 조직', '무장 세력',
    '폭발', '사망', '부상', '함정', '전투기', '핵무기', '나토', 'NATO', '군사 위기',
    'strike', 'missile', 'war', 'attack', 'conflict', 'explosion', 'combat', 'invasion', 
    'bombing', 'airstrike', 'shelling', 'troops', 'military', 'casualty', 'casualties', 
    'hostage', 'terrorist', 'terrorism', 'assassination', 'clash', 'artillery', 'defense'
]

WEEKDAYS_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

def format_datetime_with_weekday(dt):
    weekday_str = WEEKDAYS_KR[dt.weekday()]
    return f"{dt.strftime('%Y.%m.%d')} ({weekday_str}) {dt.strftime('%H:%M')}"

def categorize_incident(title, content):
    text = (title + " " + content).lower()
    
    exclude_keywords = [
        '비트코인', '이더리움', '코인', '가상화폐', '암호화폐', '주가', '증시', '코스피', '코스닥', 
        '나스닥', '환율', '금리', '시세', '상장', '매수', '매도', '외국인 순매수', '주가 하락', 
        '증시 전망', '최고경영자', '사임', '합병 승인', '특검', '국정조사', '재판', '공판', '선고', '항소', '상고',
        '바둑', '체스', '이세돌', '신진서', '박정환', '알파고', '프로기사', '기전', '대국', '우승', '준우승', 
        '리그', '토너먼트', '경기력', '감독', '선수', '득점', '골퍼', '야구', '축구', '농구', '배구', '올림픽', '아시안게임',
        '연예', '아이돌', '배우', '영화', '드라마', '앨범', '컴백', '결혼', '이혼', '열애'
    ]
    if any(kw in text for kw in exclude_keywords):
        return None 

    has_country = any(country.lower() in text for country in WORLD_COUNTRIES)
    has_conflict_term = any(term in text for term in CONFLICT_KEYWORDS)

    if has_country and has_conflict_term:
        return "해외 분쟁·테러"

    global_force_terms = ['우크라이나', '러시아', '이란', '이스라엘', '하마스', '헤즈볼라', '중동', '공습', '미사일', '폭격', '전쟁', '테러']
    if any(term in text for term in global_force_terms) and has_conflict_term:
        return "해외 분쟁·테러"

    if any(kw in text for kw in ['계엄', '군 병력', '북한 도발', '미사일 발사', '영공 침범', '국방 비상']):
        return "국가 안보"

    if any(kw in text for kw in ['성폭행', '성추행', '성범죄', '살인', '강도', '인질', '폭행', '흉기', '마약', '긴급 체포', '수배', '경찰 출동', '구속영장', '입건', '송치', '피의자']):
        return "강력·치안"

    if any(kw in text for kw in ['해킹', '랜섬웨어', '개인정보 유출', '전산 장애', '서버 다운', '금융 사고', '보안 취약점']):
        return "사이버·금융"

    if any(kw in text for kw in ['화재', '폭발', '건물 붕괴', '교량 붕괴', '지진', '홍수', '산사태', '침수', '구조 작전', '교통 통제', '가스 유출', '정전 사고']):
        return "재난·안전"

    return None

def extract_location(title, content):
    cleaned_title = re.sub(r'[\(\[]?[가-힣]+=(연합뉴스|뉴스1|뉴시스|파이낸셜뉴스|이데일리)[\)\]]?', '', title)
    cleaned_content = re.sub(r'[\(\[]?[가-힣]+=(연합뉴스|뉴스1|뉴시스|파이낸셜뉴스|이데일리)[\)\]]?', '', content)

    for search_text in [cleaned_title, cleaned_content]:
        earliest_pos = len(search_text) + 1
        matched_info = None

        for city, info in KR_CITY_COORDS.items():
            pos = search_text.find(city)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
                matched_info = (info["label"], info["lat"], info["lng"])
        
        if matched_info:
            return matched_info

        for prov, info in KR_PROVINCE_COORDS.items():
            pos = search_text.find(prov)
            if pos != -1 and pos < earliest_pos:
                earliest_pos = pos
                matched_info = (info["label"], info["lat"], info["lng"])

        if matched_info:
            return matched_info

        for keyword, info in GLOBAL_COORDS.items():
            if keyword in search_text:
                return info["label"], info["lat"], info["lng"]

        for country in WORLD_COUNTRIES:
            if country in search_text:
                return f"해외 분쟁지역 ({country})", 35.0, 40.0

    return "대한민국 (세부 위치 미상)", 36.3504, 127.3845

def scrape_telegram_channel(channel_info):
    items = []
    url = channel_info["url"]
    kst = pytz.timezone('Asia/Seoul')
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8')
            message_blocks = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', html, re.DOTALL)
            link_blocks = re.findall(r'<a href="(https?://[^"]+)"[^>]*>.*?</a>', html, re.DOTALL)
            
            for i, raw_msg in enumerate(message_blocks[:25]):
                clean_text = remove_html_tags(raw_msg).strip()
                if not clean_text:
                    continue
                
                urls_in_msg = re.findall(r'(https?://[^\s]+)', clean_text)
                target_link = ""
                for u in urls_in_msg:
                    if "t.me" not in u and "twitter.com" not in u and "x.com" not in u:
                        target_link = u
                        break
                
                if not target_link and i < len(link_blocks):
                    candidate = link_blocks[i]
                    if "t.me" not in candidate:
                        target_link = candidate
                
                if not target_link:
                    continue

                translated_text = translate_to_korean(clean_text)
                title = translated_text.split('\n')[0][:60]
                summary = translated_text[:130] + ("..." if len(translated_text) > 130 else "")
                
                category = categorize_incident(title, translated_text)
                if not category:
                    continue

                location_str, lat, lng = extract_location(title, translated_text)
                real_source_name = extract_domain_source(target_link)
                
                now_dt = datetime.now(kst)
                datetime_str = format_datetime_with_weekday(now_dt)

                items.append({
                    "title": title,
                    "summary": summary,
                    "content": translated_text,
                    "location": location_str,
                    "lat": lat,
                    "lng": lng,
                    "category": category,
                    "time": datetime_str,
                    "source": real_source_name,
                    "link": target_link,
                    "timestamp": now_dt.timestamp()
                })
    except Exception as e:
        print(f"Error scraping telegram {url}: {e}")
        
    return items

def scrape_news():
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    seven_days_ago = now - timedelta(days=7)
    collected_items = []

    for feed_info in RSS_FEEDS:
        parsed = feedparser.parse(feed_info["url"])
        for entry in parsed.entries[:100]:
            title = remove_html_tags(entry.get("title", ""))
            raw_summary = entry.get("summary", title)
            clean_content = remove_html_tags(raw_summary)
            link = entry.get("link", "")
            
            pub_dt = now
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                pub_dt = datetime.fromtimestamp(time.mktime(published_parsed), kst)
                if pub_dt < seven_days_ago:
                    continue
            
            datetime_str = format_datetime_with_weekday(pub_dt)
            
            category = categorize_incident(title, clean_content)
            if not category:
                continue
                
            location_str, lat, lng = extract_location(title, clean_content)
            
            lat += (random.random() - 0.5) * 0.008
            lng += (random.random() - 0.5) * 0.008

            collected_items.append({
                "category": category,
                "title": title,
                "summary": clean_content[:130] + ("..." if len(clean_content) > 130 else ""),
                "content": clean_content,
                "location": location_str,
                "lat": round(lat, 4),
                "lng": round(lng, 4),
                "time": datetime_str,
                "source": feed_info["source"],
                "link": link,
                "timestamp": pub_dt.timestamp()
            })

    for channel in TELEGRAM_CHANNELS:
        tg_items = scrape_telegram_channel(channel)
        for item in tg_items:
            item["lat"] = round(item["lat"] + (random.random() - 0.5) * 0.008, 4)
            item["lng"] = round(item["lng"] + (random.random() - 0.5) * 0.008, 4)
            collected_items.append(item)

    return collected_items

if __name__ == "__main__":
    print("=== SQLite 기반 실시간 뉴스 관제 크롤러가 시작되었습니다 ===")
    init_db()
    try:
        data = scrape_news()
        save_to_db(data)
        export_db_to_json()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 및 DB 갱신 완료")
    except Exception as e:
        print(f"실행 중 오류 발생: {e}")
