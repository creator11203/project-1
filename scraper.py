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
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    kst = pytz.timezone('Asia/Seoul')
    cutoff_timestamp = (datetime.now(kst) - timedelta(days=7)).timestamp()
    cursor.execute('DELETE FROM news WHERE timestamp < ?', (cutoff_timestamp,))
    conn.commit()

    cursor.execute('SELECT * FROM news ORDER BY timestamp DESC LIMIT 400')
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
            'apnews.com': 'AP News',
            'bbc.com': 'BBC'
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
    {"url": "https://news.google.com/rss/search?q=%EC%82%AC%EA%B3%A0+%EC%82%AC%EA%B1%B4+%ED%8F%AD%ED%96%89+%EA%B2%BD%EC%B0%B0+%EC%86%A1%EC%B9%98+%EA%B5%AC%EC%86%8D+%EC%82%AC%EA%B8%B0+%ED%8F%AD%ED%8C%8D&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (사건·사고)"}
]

TELEGRAM_CHANNELS = [
    {"url": "https://t.me/s/FastStockNews", "source": "FastStockNews"},
    {"url": "https://t.me/s/cahier_de_market", "source": "cahier_de_market"}
]

# 세부 동(洞) 및 시·군·구 좌표 매핑 대폭 확대
KR_CITY_COORDS = {
    # 서울 주요 구/동
    "강남구": {"lat": 37.5172, "lng": 127.0473, "label": "서울특별시 강남구"},
    "역삼동": {"lat": 37.5006, "lng": 127.0364, "label": "서울특별시 강남구 역삼동"},
    "대치동": {"lat": 37.4946, "lng": 127.0632, "label": "서울특별시 강남구 대치동"},
    "신사동": {"lat": 37.5210, "lng": 127.0229, "label": "서울특별시 강남구 신사동"},
    "서초구": {"lat": 37.4836, "lng": 127.0327, "label": "서울특별시 서초구"},
    "송파구": {"lat": 37.5145, "lng": 127.1059, "label": "서울특별시 송파구"},
    "마포구": {"lat": 37.5663, "lng": 126.9016, "label": "서울특별시 마포구"},
    "홍대": {"lat": 37.5563, "lng": 126.9236, "label": "서울특별시 마포구 서교동"},
    "종로구": {"lat": 37.5730, "lng": 126.9794, "label": "서울특별시 종로구"},
    "중구": {"lat": 37.5636, "lng": 126.9975, "label": "서울특별시 중구"},
    "영등포구": {"lat": 37.5264, "lng": 126.8962, "label": "서울특별시 영등포구"},
    "여의도": {"lat": 37.5219, "lng": 126.9245, "label": "서울특별시 영등포구 여의도동"},
    "관악구": {"lat": 37.4784, "lng": 126.9515, "label": "서울특별시 관악구"},
    "신림동": {"lat": 37.4842, "lng": 126.9297, "label": "서울특별시 관악구 신림동"},
    "구로구": {"lat": 37.4954, "lng": 126.8874, "label": "서울특별시 구로구"},
    "송파": {"lat": 37.5145, "lng": 127.1059, "label": "서울특별시 송파구"},
    
    # 경기/인천 주요 지역
    "수원": {"lat": 37.2636, "lng": 127.0286, "label": "경기도 수원시"},
    "성남": {"lat": 37.4200, "lng": 127.1267, "label": "경기도 성남시"},
    "분당": {"lat": 37.3827, "lng": 127.1189, "label": "경기도 성남시 분당구"},
    "고양": {"lat": 37.6584, "lng": 126.8320, "label": "경기도 고양시"},
    "용인": {"lat": 37.2411, "lng": 127.1776, "label": "경기도 용인시"},
    "부천": {"lat": 37.5034, "lng": 126.7660, "label": "경기도 부천시"},
    "안산": {"lat": 37.3219, "lng": 126.8309, "label": "경기도 안산시"},
    "안양": {"lat": 37.3943, "lng": 126.9568, "label": "경기도 안양시"},
    "화성": {"lat": 37.1996, "lng": 126.8312, "label": "경기도 화성시"},
    "평택": {"lat": 36.9921, "lng": 127.1129, "label": "경기도 평택시"},
    "인천": {"lat": 37.4563, "lng": 126.7052, "label": "인천광역시"},
    
    # 충청권 (천안, 아산 등)
    "천안": {"lat": 36.8151, "lng": 127.1139, "label": "충청남도 천안시"},
    "두정동": {"lat": 36.8312, "lng": 127.1352, "label": "충청남도 천안시 서북구 두정동"},
    "불당동": {"lat": 36.8118, "lng": 127.1102, "label": "충청남도 천안시 서북구 불당동"},
    "성성동": {"lat": 36.8501, "lng": 127.1351, "label": "충청남도 천안시 서북구 성성동"},
    "아산": {"lat": 36.7898, "lng": 127.0018, "label": "충청남도 아산시"},
    "배방": {"lat": 36.7845, "lng": 127.0310, "label": "충청남도 아산시 배방읍"},
    "대전": {"lat": 36.3504, "lng": 127.3845, "label": "대전광역시"},
    "세종": {"lat": 36.4800, "lng": 127.2890, "label": "세종특별자치시"},
    "청주": {"lat": 36.6424, "lng": 127.4890, "label": "충청북도 청주시"},
    
    # 기타 광역시 및 지방
    "부산": {"lat": 35.1796, "lng": 129.0756, "label": "부산광역시"},
    "해운대": {"lat": 35.1631, "lng": 129.1636, "label": "부산광역시 해운대구"},
    "대구": {"lat": 35.8714, "lng": 128.6014, "label": "대구광역시"},
    "광주": {"lat": 35.1595, "lng": 126.8526, "label": "광주광역시"},
    "울산": {"lat": 35.5384, "lng": 129.3114, "label": "울산광역시"},
    "제주": {"lat": 33.4996, "lng": 126.5312, "label": "제주특별자치도"}
}

KR_PROVINCE_COORDS = {
    "서울": {"lat": 37.5665, "lng": 126.9780, "label": "서울특별시"},
    "경기": {"lat": 37.4138, "lng": 127.5183, "label": "경기도"},
    "인천": {"lat": 37.4563, "lng": 126.7052, "label": "인천광역시"},
    "강원": {"lat": 37.8228, "lng": 128.1555, "label": "강원특별자치도"},
    "충북": {"lat": 36.6357, "lng": 127.4917, "label": "충청북도"},
    "충남": {"lat": 36.5184, "lng": 126.8000, "label": "충청남도"},
    "전북": {"lat": 35.7175, "lng": 127.1530, "label": "전북특별자치도"},
    "전남": {"lat": 34.8679, "lng": 126.9910, "label": "전라남도"},
    "경북": {"lat": 36.4919, "lng": 128.8889, "label": "경상북도"},
    "경남": {"lat": 35.4606, "lng": 128.2132, "label": "경상남도"},
    "부산": {"lat": 35.1796, "lng": 129.0756, "label": "부산광역시"}
}

GLOBAL_COORDS = {
    "우크라이나": {"lat": 50.4501, "lng": 30.5234, "label": "우크라이나 키이우"},
    "러시아": {"lat": 55.7558, "lng": 37.6173, "label": "러시아 모스크바"},
    "이란": {"lat": 35.6892, "lng": 51.3890, "label": "이란 테헤란"},
    "이스라엘": {"lat": 31.7683, "lng": 35.2137, "label": "이스라엘 예루살렘"}
}

WORLD_COUNTRIES = ["미국", "중국", "일본", "러시아", "우크라이나", "이란", "이스라엘", "북한"]

CONFLICT_KEYWORDS = ['공습', '미사일', '폭격', '전쟁', '테러', '무력 충돌', '군사 작전']

WEEKDAYS_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

def format_datetime_with_weekday(dt):
    return f"{dt.strftime('%Y.%m.%d')} ({WEEKDAYS_KR[dt.weekday()]}) {dt.strftime('%H:%M')}"

def categorize_incident(title, content):
    text = (title + " " + content).lower()
    
    # 제외 대상 (스포츠, 연예, 증시 등)
    exclude_keywords = [
        '비트코인', '이더리움', '코인', '가상화폐', '암호화폐', '주가', '증시', '코스피', '코스닥', 
        '나스닥', '환율', '금리', '시세', '상장', '매수', '매도', '바둑', '체스', '이세돌', '신진서', 
        '우승', '준우승', '리그', '토너먼트', '경기력', '감독', '선수', '연예', '아이돌', '배우', '영화', '드라마'
    ]
    if any(kw in text for kw in exclude_keywords):
        return None 

    # 1. 해외 분쟁·테러
    if any(c.lower() in text for c in WORLD_COUNTRIES) and any(t in text for t in CONFLICT_KEYWORDS):
        return "해외 분쟁·테러"

    # 2. 국가 안보
    if any(kw in text for kw in ['계엄', '군 병력', '북한 도발', '미사일 발사', '영공 침범', '국방 비상']):
        return "국가 안보"

    # 3. 강력·치안 (요청하신 온갖 범죄 및 일상 사건 키워드 대거 포함)
    crime_keywords = [
        '스토킹', '마약', '해킹', '개인정보 유출', '몰카', '소형카메라', '화장실 몰카', '흉기 난동', 
        '방화', '묻지마 폭행', '난투극', '조폭', '조직폭력배', '원한 범죄', '집단 폭행', '폭행', 
        '집단 성폭행', '성폭행', '성추행', '성범죄', '그루밍', '그루밍 범죄', '자살', '동반 자살', 
        '실종', '아동 실종', '성인 실종', '납치', '절도', '강도', '특수 절도', '상해', '사기죄', 
        '금품 갈취', '갈취', '살인', '마약류', '필로폰', '대마초', '공갈', '협박', '특수상해', '특수폭행'
    ]
    if any(kw in text for kw in crime_keywords):
        return "강력·치안"

    # 4. 재난·안전 및 사고 (교통사고, 붕괴 등 요청 키워드 포함)
    safety_keywords = [
        '교통사고', '뺑소니', '건물 붕괴', '다리 붕괴', '지반 붕괴', '시설물', '고속도로 사고', 
        '우회전 사고', '자전거 충돌', '보행자 사고', '화재', '폭발', '지진', '홍수', '산사태', 
        '침수', '정전', '가스 유출', '구조 작전', '교통 통제', '차량 충돌'
    ]
    if any(kw in text for kw in safety_keywords):
        return "재난·안전"

    # 5. 사이버·금융 사고
    if any(kw in text for kw in ['랜섬웨어', '전산 장애', '서버 다운', '금융 사고', '보안 취약점', '보이스피싱', '스미싱']):
        return "사이버·금융"

    # 기본 포괄 분류 (일상의 사소한 사건사고도 누락되지 않도록 캐치)
    if any(kw in text for kw in ['사건', '사고', '경찰', '소방', '출동', '조사', '입건', '구속', '수사', '피해', '부상', '사망']):
        return "강력·치안"

    return None

def extract_location(title, content):
    cleaned_title = re.sub(r'[\(\[]?[가-힣]+=(연합뉴스\vert{}뉴스1\vert{}뉴시스)[\)\]]?', '', title)
    cleaned_content = re.sub(r'[\(\[]?[가-힣]+=(연합뉴스\vert{}뉴스1\vert{}뉴시스)[\)\]]?', '', content)
    search_text = cleaned_title + " " + cleaned_content

    # 세부 동(洞) 또는 구(區) 단위 먼저 탐색 (정밀 위치 매핑)
    for city, info in KR_CITY_COORDS.items():
        if city in search_text:
            return info["label"], info["lat"], info["lng"]

    for prov, info in KR_PROVINCE_COORDS.items():
        if prov in search_text:
            return info["label"], info["lat"], info["lng"]

    for keyword, info in GLOBAL_COORDS.items():
        if keyword in search_text:
            return info["label"], info["lat"], info["lng"]

    return "대한민국 (세부 위치 미상)", 36.3504, 127.3845

def scrape_telegram_channel(channel_info):
    items = []
    url = channel_info["url"]
    kst = pytz.timezone('Asia/Seoul')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8')
            message_blocks = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', html, re.DOTALL)
            for raw_msg in message_blocks[:25]:
                clean_text = remove_html_tags(raw_msg).strip()
                if not clean_text:
                    continue
                translated_text = translate_to_korean(clean_text)
                title = translated_text.split('\n')[0][:60]
                category = categorize_incident(title, translated_text)
                if not category:
                    continue
                location_str, lat, lng = extract_location(title, translated_text)
                now_dt = datetime.now(kst)
                items.append({
                    "title": title,
                    "summary": translated_text[:130],
                    "content": translated_text,
                    "location": location_str,
                    "lat": lat,
                    "lng": lng,
                    "category": category,
                    "time": format_datetime_with_weekday(now_dt),
                    "source": "Telegram 실시간",
                    "link": url,
                    "timestamp": now_dt.timestamp()
                })
    except Exception as e:
        print(f"Telegram error: {e}")
    return items

def scrape_news():
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    seven_days_ago = now - timedelta(days=7)
    collected_items = []

    for feed_info in RSS_FEEDS:
        parsed = feedparser.parse(feed_info["url"])
        for entry in parsed.entries[:120]:
            title = remove_html_tags(entry.get("title", ""))
            clean_content = remove_html_tags(entry.get("summary", title))
            link = entry.get("link", "")
            
            pub_dt = now
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                pub_dt = datetime.fromtimestamp(time.mktime(published_parsed), kst)
                if pub_dt < seven_days_ago:
                    continue
            
            category = categorize_incident(title, clean_content)
            if not category:
                continue
                
            location_str, lat, lng = extract_location(title, clean_content)
            lat += (random.random() - 0.5) * 0.005
            lng += (random.random() - 0.5) * 0.005

            collected_items.append({
                "category": category,
                "title": title,
                "summary": clean_content[:130] + ("..." if len(clean_content) > 130 else ""),
                "content": clean_content,
                "location": location_str,
                "lat": round(lat, 4),
                "lng": round(lng, 4),
                "time": format_datetime_with_weekday(pub_dt),
                "source": feed_info["source"],
                "link": link,
                "timestamp": pub_dt.timestamp()
            })

    for channel in TELEGRAM_CHANNELS:
        collected_items.extend(scrape_telegram_channel(channel))

    return collected_items

if __name__ == "__main__":
    print("=== 확장된 사건사고 필터 관제 크롤러 실행 ===")
    init_db()
    try:
        data = scrape_news()
        save_to_db(data)
        export_db_to_json()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 및 DB 갱신 완료 (총 {len(data)}건)")
    except Exception as e:
        print(f"오류 발생: {e}")
