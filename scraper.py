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

    cursor.execute('SELECT * FROM news ORDER BY timestamp DESC LIMIT 600')
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

# 💡 주요 언론사 공식 RSS 및 키워드 기반 구글 뉴스 실시간 서치 피드 대거 통합
RSS_FEEDS = [
    # 주요 종합일간지 및 통신사 공식 RSS
    {"url": "https://www.yna.co.kr/rss/news.xml", "source": "연합뉴스"},
    {"url": "https://www.chosun.com/arc/outboundbyfeed/rss/?outputType=xml", "source": "조선일보"},
    {"url": "https://rss.joins.com/joins_news_list.xml", "source": "중앙일보"},
    {"url": "https://rss.donga.com/total.xml", "source": "동아일보"},
    {"url": "https://www.hankyung.com/feed/all", "source": "한국경제"},
    {"url": "https://www.mk.co.kr/rss/30000001/", "source": "매일경제"},
    {"url": "https://www.hani.co.kr/rss/", "source": "한겨레"},
    {"url": "https://www.khan.co.kr/rss/rssdata/total_news.xml", "source": "경향신문"},
    {"url": "https://www.segye.com/rss/all.xml", "source": "세계일보"},
    {"url": "https://rss.kmib.co.kr/data/kmibAllNews.xml", "source": "국민일보"},
    {"url": "https://www.seoul.co.kr/xml/rss.xml", "source": "서울신문"},

    # 방송 및 뉴스통신사 공식 RSS
    {"url": "https://news.kbs.co.kr/rss/rss.do", "source": "KBS"},
    {"url": "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01&plink=RSS", "source": "SBS"},
    {"url": "https://imnews.imbc.com/rss/news/news_00.xml", "source": "MBC"},
    {"url": "https://www.ytn.co.kr/rss/rss.xml", "source": "YTN"},
    {"url": "https://www.yonhapnewstv.co.kr/browse/feed", "source": "연합뉴스TV"},
    {"url": "https://rss.ichannela.com/rss/channels_news.xml", "source": "채널A"},
    {"url": "https://news.tvchosun.com/svc/common/rss/rss.xml", "source": "TV조선"},
    {"url": "https://www.mbn.co.kr/rss/", "source": "MBN"},
    {"url": "https://www.newsis.com/RSS/sisa.xml", "source": "뉴시스"},
    {"url": "https://www.news1.kr/rss/", "source": "뉴스1"},

    # 경제·전문지 공식 RSS
    {"url": "https://www.wowtv.co.kr/newscenter/rss", "source": "한국경제TV"},
    {"url": "https://biz.sbs.co.kr/rss/rss.xml", "source": "SBS Biz"},
    {"url": "https://biz.chosun.com/arc/outboundbyfeed/rss/?outputType=xml", "source": "조선비즈"},
    {"url": "https://rss.mt.co.kr/mt_news.xml", "source": "머니투데이"},
    {"url": "https://www.edaily.co.kr/rss/edaily_news.xml", "source": "이데일리"},
    {"url": "https://www.fnnews.com/rss/fn_realnews.xml", "source": "파이낸셜뉴스"},
    {"url": "https://www.sedaily.com/Rss/RssList", "source": "서울경제"},
    {"url": "https://www.asiae.co.kr/rss/", "source": "아시아경제"},
    {"url": "https://www.dt.co.kr/rss/dt_rss.xml", "source": "디지털타임스"},
    {"url": "https://rss.etnews.com/EtNewsSection.xml", "source": "전자신문"},
    {"url": "https://zdnet.co.kr/rss/all.xml", "source": "ZDNet Korea"},

    # 💡 강력범죄·사건사고 키워드가 강력하게 반영된 구글 뉴스 실시간 검색 RSS 쿼리들
    {"url": "https://news.google.com/rss/search?q=%EC%82%AC%EA%B3%A0+OR+%EC%82%AC%EA%B1%B4+OR+%ED%8F%AD%ED%96%89+OR+%EA%B2%BD%EC%B0%B0+OR+%EA%B5%AC%EC%86%8D+OR+%EC%82%AC%EA%B8%B0+OR+%ED%8F%AD%ED%8C%8D+OR+%ED%99%94%EC%9E%AC&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (종합 사건사고)"},
    {"url": "https://news.google.com/rss/search?q=%EC%82%B4%EC%9D%B8+OR+%EB%A7%88%EC%95%BD+OR+%EC%8A%A4%ED%86%A0%ED%82%B9+OR+%ED%9D%B9%EA%B8%B0+OR+%EC%84%B1%EB%B2%94%EC%A3%84+OR+%EC%9C%A0%EC%B6%9C+OR+%ED%95%B4%ED%82%B9&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (강력범죄·마약·사이버)"},
    {"url": "https://news.google.com/rss/search?q=%EA%B5%90%ED%86%B5%EC%82%AC%EA%B3%A0+OR+%EB%BF%5B%5D%EB%86%80%EB%8B%88+OR+%EB%B6%95%EA%B4%B4+OR+%EC%82%B0%EC%82%AC%ED%83%9C+OR+%EC%B9%A8%EC%88%98+OR+%EC%A0%95%EC%A0%84+OR+%EA%B0%80%EC%8A%A4%EC%9C%A0%EC%B6%9C&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (재난·사고·교통)"}
]

TELEGRAM_CHANNELS = [
    {"url": "https://t.me/s/cahier_de_market", "source": "Telegram 채널"}
]

KR_CITY_COORDS = {
    "강남구": {"lat": 37.5172, "lng": 127.0473, "label": "서울특별시 강남구"},
    "역삼동": {"lat": 37.5006, "lng": 127.0364, "label": "서울특별시 강남구 역삼동"},
    "대치동": {"lat": 37.4946, "lng": 127.0632, "label": "서울특별시 강남구 대치동"},
    "신사동": {"lat": 37.5210, "lng": 127.0229, "label": "서울특별시 강남구 신사동"},
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
    
    # 💡 금융, 주식, 연예, 가십성 노이즈 철저 차단 필터
    strict_exclude_keywords = [
        '비트코인', '이더리움', '코인', '가상화폐', '암호화폐', '주가', '증시', '코스피', '코스닥', 
        '나스닥', '환율', '금리', '시세', '상장', '매수', '매도', '젠슨 황', '엔비디아', '테슬라', 
        '애플', '마이크로소프트', '실적', '배당', '펀드', '주식', '투자', '시황', '목표주가', '반등',
        '불륜', '스캔들', '이혼', '결혼', '열애', '연예', '아이돌', '배우', '영화', '드라마', '앨범', 
        '바둑', '체스', '우승', '리그', '토너먼트', '경기력', '선수', '감독', '골프'
    ]
    if any(kw in text for kw in strict_exclude_keywords):
        return None 

    # 해외 분쟁·테러
    if any(c.lower() in text for c in WORLD_COUNTRIES) and any(t in text for t in CONFLICT_KEYWORDS):
        return "해외 분쟁"

    # 국가 안보
    if any(kw in text for kw in ['계엄', '군 병력', '북한 도발', '미사일 발사', '영공 침범', '국방 비상']):
        return "국가 안보"

    # 세분화 카테고리 매칭 1: 살인·폭행·흉기 (강력범죄)
    if any(kw in text for kw in ['살인', '흉기 난동', '묻지마 폭행', '난투극', '조폭', '조직폭력배', '원한', '집단 폭행', '폭행', '상해', '특수상해', '특수폭행']):
        return "강력범죄"

    # 세분화 카테고리 매칭 2: 성범죄·마약·스토킹
    if any(kw in text for kw in ['성범죄', '성폭행', '성추행', '몰카', '소형카메라', '마약', '필로폰', '대마초', '스토킹', '그루밍']):
        return "성범죄·마약"

    # 세분화 카테고리 매칭 3: 사기·절도·해킹
    if any(kw in text for kw in ['사기', '절도', '강도', '해킹', '개인정보 유출', '보이스피싱', '스미싱', '금품 갈취', '공갈', '협박', '특수 절도']):
        return "사기·금융"

    # 세분화 카테고리 매칭 4: 화재·붕괴·안전 (재난·사고)
    if any(kw in text for kw in ['화재', '폭발', '건물 붕괴', '다리 붕괴', '지반 붕괴', '산사태', '홍수', '침수', '정전', '가스 유출', '지진', '구조 작전']):
        return "재난·사고"

    # 세분화 카테고리 매칭 5: 교통사고·뺑소니
    if any(kw in text for kw in ['교통사고', '뺑소니', '고속도로 사고', '우회전 사고', '자전거 충돌', '보행자 사고', '차량 충돌', '추돌사고']):
        return "교통사고"

    # 일반 강력·치안 (기타 입건/구속 등)
    if any(kw in text for kw in ['경찰 출동', '구속영장', '입건', '실종', '자살']):
        return "실종·제보"

    return None

def extract_location(title, content):
    cleaned_title = re.sub(r'[\(\[]?[가-힣]+=(연합뉴스|뉴스1|뉴시스)[\)\]]?', '', title)
    cleaned_content = re.sub(r'[\(\[]?[가-힣]+=(연합뉴스|뉴스1|뉴시스)[\)\]]?', '', content)
    search_text = cleaned_title + " " + cleaned_content

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
            for raw_msg in message_blocks[:30]:
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
                    "source": "Telegram",
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
        try:
            parsed = feedparser.parse(feed_info["url"])
            for entry in parsed.entries[:60]:
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
        except Exception as e:
            print(f"RSS 수집 오류 ({feed_info['source']}): {e}")

    for channel in TELEGRAM_CHANNELS:
        collected_items.extend(scrape_telegram_channel(channel))

    return collected_items

if __name__ == "__main__":
    print("=== 대규모 언론사 및 구글 검색 RSS 기반 관제 크롤러 실행 ===")
    init_db()
    try:
        data = scrape_news()
        save_to_db(data)
        export_db_to_json()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 및 DB 갱신 완료 (총 {len(data)}건)")
    except Exception as e:
        print(f"오류 발생: {e}")
