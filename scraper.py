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

    cursor.execute('SELECT * FROM news ORDER BY timestamp DESC LIMIT 800')
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

def parse_date_string(date_str):
    if not date_str:
        return datetime.now().timestamp()
    
    clean_str = re.sub(r'\s+', ' ', date_str.strip())
    kst = pytz.timezone('Asia/Seoul')
    
    match_am_pm = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})\.?[^\d]*(오전|오후)\s*(\d{1,2}):(\d{2})', clean_str)
    if match_am_pm:
        year, month, day, meridian, hour, minute = match_am_pm.groups()
        hour = int(hour)
        if meridian == '오후' and hour < 12:
            hour += 12
        elif meridian == '오전' and hour == 12:
            hour = 0
        try:
            dt = kst.localize(datetime(int(year), int(month), int(day), hour, int(minute)))
            return dt.timestamp()
        except ValueError:
            pass

    match_24 = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})\D+(\d{1,2}):(\d{2})', clean_str)
    if match_24:
        year, month, day, hour, minute = match_24.groups()
        try:
            dt = kst.localize(datetime(int(year), int(month), int(day), int(hour), int(minute)))
            return dt.timestamp()
        except ValueError:
            pass

    match_date_only = re.search(r'(\d{4})[./-](\d{1,2})[./-](\d{1,2})', clean_str)
    if match_date_only:
        year, month, day = match_date_only.groups()
        try:
            dt = kst.localize(datetime(int(year), int(month), int(day)))
            return dt.timestamp()
        except ValueError:
            pass

    return datetime.now(kst).timestamp()

RSS_FEEDS = [
    {"url": "https://news.google.com/rss/search?q=%EC%82%AC%EA%B3%A0+OR+%EC%82%AC%EA%B1%B4+OR+%ED%8F%AD%ED%96%89+OR+%EA%B2%BD%EC%B0%B0+OR+%EA%B5%AC%EC%86%8D+OR+%EC%82%AC%EC%88%98+OR+%ED%99%94%EC%9E%AC&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (종합 사건사고)"},
    {"url": "https://news.google.com/rss/search?q=%EC%82%B4%EC%9D%B8+OR+%EB%A7%88%EC%95%BD+OR+%EC%8A%A4%ED%86%A0%ED%82%B9+OR+%ED%9D%B9%EA%B8%B0+OR+%EC%84%B1%EB%B2%94%EC%A3%84+OR+%EC%9C%A0%EC%B6%9C+OR+%ED%95%B4%ED%82%B9&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (강력범죄·마약·사이버)"},
    {"url": "https://news.google.com/rss/search?q=%EC%95%88%EC%A0%84+OR+%EC%82%AC%EA%B3%A0+OR+%EA%B5%90%ED%86%B5%EC%82%AC%EA%B3%A0+OR+%EB%B6%95%EA%B4%B4+OR+%EC%82%AC%EC%82%AC%ED%83%9C+OR+%EC%B9%A8%EC%88%98+OR+%EC%A0%95%EC%A0%84&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (재난·사고·교통)"},
    {"url": "https://www.yna.co.kr/rss/news.xml", "source": "연합뉴스"},
    {"url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSS", "source": "SBS"},
    {"url": "https://news.kbs.co.kr/rss/rss.do", "source": "KBS"},
    {"url": "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml", "source": "조선일보"},
    {"url": "https://fs.jtbc.co.kr/RSS/newsflash.xml", "source": "JTBC"},
    {"url": "https://imnews.imbc.com/rss/news/news_00.xml", "source": "MBC"}
]

KR_CITY_COORDS = {
    "강남구": {"lat": 37.5172, "lng": 127.0473, "label": "서울특별시 강남구"},
    "서초구": {"lat": 37.4836, "lng": 127.0327, "label": "서울특별시 서초구"},
    "송파구": {"lat": 37.5145, "lng": 127.1059, "label": "서울특별시 송파구"},
    "마포구": {"lat": 37.5663, "lng": 126.9016, "label": "서울특별시 마포구"},
    "종로구": {"lat": 37.5730, "lng": 126.9794, "label": "서울특별시 종로구"},
    "중구": {"lat": 37.5636, "lng": 126.9975, "label": "서울특별시 중구"},
    "영등포구": {"lat": 37.5264, "lng": 126.8962, "label": "서울특별시 영등포구"},
    "관악구": {"lat": 37.4784, "lng": 126.9515, "label": "서울특별시 관악구"},
    "수원": {"lat": 37.2636, "lng": 127.0286, "label": "경기도 수원시"},
    "성남": {"lat": 37.4200, "lng": 127.1267, "label": "경기도 성남시"},
    "고양": {"lat": 37.6584, "lng": 126.8320, "label": "경기도 고양시"},
    "용인": {"lat": 37.2411, "lng": 127.1776, "label": "경기도 용인시"},
    "부천": {"lat": 37.5034, "lng": 126.7660, "label": "경기도 부천시"},
    "인천": {"lat": 37.4563, "lng": 126.7052, "label": "인천광역시"},
    "천안": {"lat": 36.8151, "lng": 127.1139, "label": "충청남도 천안시"},
    "두정동": {"lat": 36.8312, "lng": 127.1352, "label": "충청남도 천안시 서북구 두정동"},
    "불당동": {"lat": 36.8118, "lng": 127.1102, "label": "충청남도 천안시 서북구 불당동"},
    "아산": {"lat": 36.7898, "lng": 127.0018, "label": "충청남도 아산시"},
    "대전": {"lat": 36.3504, "lng": 127.3845, "label": "대전광역시"},
    "세종": {"lat": 36.4800, "lng": 127.2890, "label": "세종특별자치시"},
    "부산": {"lat": 35.1796, "lng": 129.0756, "label": "부산광역시"},
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
    "충남": {"lat": 36.5184, "lng": 126.8000, "label": "충청남도"},
    "부산": {"lat": 35.1796, "lng": 129.0756, "label": "부산광역시"}
}

WEEKDAYS_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]

def format_datetime_with_weekday(dt):
    return f"{dt.strftime('%Y.%m.%d')} ({WEEKDAYS_KR[dt.weekday()]}) {dt.strftime('%H:%M')}"

def categorize_incident(title, content):
    text = (title + " " + content).lower()
    
    # 투자, 연예 및 범죄 예방·캠페인·홍보성 기사 배제 키워드
    strict_exclude_keywords = [
        '비트코인', '이더리움', '코인', '가상화폐', '암호화폐', '주가', '증시', '코스피', '코스닥', 
        '나스닥', '환율', '금리', '시세', '상장', '매수', '매도', '젠슨 황', '엔비디아', '테슬라', 
        '애플', '마이크로소프트', '실적', '배당', '펀드', '주식', '투자', '시황', '목표주가', '반등',
        '불륜', '스캔들', '이혼', '결혼', '열애', '연예', '아이돌', '배우', '영화', '드라마', '앨범', 
        '바둑', '체스', '우승', '리그', '토너먼트', '경기력', '선수', '감독', '골프',
        # 예방 및 캠페인성 키워드 차단
        '예방', '캠페인', '근절', '홍보', '대책회의', '교육', '설명회', '서포터즈', '공모전', '주의당부'
    ]
    if any(kw in text for kw in strict_exclude_keywords):
        return None 

    # 1. 강력범죄 (납치, 유괴, 감금, 인질, 살인미수, 방화, 특수협박 등 추가)
    if any(kw in text for kw in ['살인', '살해', '살인미수', '토막', '토막살인', '토막 살인', '토막시신', '흉기', '난동', '묻지마', '조폭', '조직폭력배', '폭행', '상해', '특수상해', '특수폭행', '납치', '유괴', '감금', '인질', '방화', '특수협박']):
        return "강력범죄"

    # 2. 성범죄·마약 (딥페이크, 디지털성범죄, 성착취, 강제추행, 준강간, 강간, 케타민, 프로포폴, 향정신성의약품 등 추가)
    if any(kw in text for kw in ['성범죄', '강간', '준강간', '성폭행', '성추행', '강제추행', '불법촬영', '몰카', '몰래카메라', '카메라등이용촬영', '딥페이크', '디지털성범죄', '성착취', '마약', '필로폰', '대마초', '케타민', '프로포폴', '향정신성의약품', '스토킹', '교제폭력', '데이트폭력']):
        return "성범죄·마약"

    # 3. 사기·금융 (횡령, 배임, 투자사기, 리딩방, 주가조작, 유사수신, 랜섬웨어 등 추가)
    if any(kw in text for kw in ['사기', '절도', '강도', '해킹', '랜섬웨어', '개인정보', '보이스피싱', '스미싱', '갈취', '공갈', '협박', '전세사기', '횡령', '배임', '투자사기', '리딩방', '주가조작', '유사수신']):
        return "사기·금융"

    # 4. 재난·사고 (싱크홀, 도로함몰, 화학물질, 유독가스, 산불, 질식, 끼임, 추락 등 추가)
    if any(kw in text for kw in ['화재', '폭발', '붕괴', '산사태', '산불', '홍수', '침수', '정전', '가스', '유독가스', '지진', '구조', '안전사고', '싱크홀', '도로함몰', '화학물질', '질식', '끼임', '추락']):
        return "재난·사고"

    # 5. 교통사고 (무면허, 역주행, 보행자, 음주측정거부 등 추가)
    if any(kw in text for kw in ['교통사고', '뺑소니', '충돌', '추돌', '차량', '음주운전', '무면허', '역주행', '보행자', '음주측정거부']):
        return "교통사고"

    # 6. 실종·제보 (변사체, 시신 발견, 행방불명, 수배 등 추가)
    if any(kw in text for kw in ['사고', '사건', '경찰', '구속', '입건', '실종', '행방불명', '수배', '변사체', '시신 발견', '수사', '출동', '피해', '안전']):
        return "실종·제보"

    return "실종·제보"

def extract_location(title, content):
    search_text = title + " " + content
    for city, info in KR_CITY_COORDS.items():
        if city in search_text:
            return info["label"], info["lat"], info["lng"]
    for prov, info in KR_PROVINCE_COORDS.items():
        if prov in search_text:
            return info["label"], info["lat"], info["lng"]
    return "대한민국 (세부 위치 미상)", 36.3504, 127.3845

def scrape_news():
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    seven_days_ago_ts = (now - timedelta(days=7)).timestamp()
    collected_items = []

    for feed_info in RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_info["url"])
            for entry in parsed.entries[:300]:
                title = remove_html_tags(entry.get("title", ""))
                clean_content = remove_html_tags(entry.get("summary", title))
                link = entry.get("link", "")
                
                date_str = entry.get("published", "") or entry.get("updated", "")
                pub_timestamp = parse_date_string(date_str)
                
                if pub_timestamp < seven_days_ago_ts:
                    continue
                
                pub_dt = datetime.fromtimestamp(pub_timestamp, kst)
                
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
                    "timestamp": pub_timestamp
                })
        except Exception as e:
            print(f"RSS 수집 오류 ({feed_info['source']}): {e}")

    return collected_items

if __name__ == "__main__":
    print("=== 안전·사건사고 실시간 관제 크롤러 실행 ===")
    init_db()
    try:
        data = scrape_news()
        save_to_db(data)
        export_db_to_json()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 및 DB 갱신 완료 (총 {len(data)}건)")
    except Exception as e:
        print(f"오류 발생: {e}")
