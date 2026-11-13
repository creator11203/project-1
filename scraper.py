import feedparser
from datetime import datetime, timedelta
import time
import pytz
import json
import random
import urllib.request
import urllib.parse
import re
from html.parser import HTMLParser

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
    f = HTMLFilter()
    f.feed(html_content)
    return f.get_data()

def translate_to_korean(text):
    if not text:
        return ""
    try:
        encoded_text = urllib.parse.quote(text[:500])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=ko&dt=t&q={encoded_text}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            translated = "".join([item[0] for item in res_data[0] if item[0]])
            return translated
    except Exception as e:
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
    {"url": "https://news.google.com/rss/search?q=%EC%82%AC%EA%B3%A0+%EC%82%AC%EA%B1%B4+%ED%8F%AD%ED%96%89+%EA%B2%BD%EC%B0%c2&hl=ko&gl=KR&ceid=KR:ko", "source": "구글 뉴스 (사건·사고)"}
]

TELEGRAM_CHANNELS = [
    {"url": "https://t.me/s/FastStockNews", "source": "FastStockNews"},
    {"url": "https://t.me/s/FastStockNewsUSA", "source": "FastStockNewsUSA"},
    {"url": "https://t.me/s/cahier_de_market", "source": "cahier_de_market"}
]

REGION_COORDS = {
    "서울특별시": {
        "lat": 37.5665, "lng": 126.9780, 
        "sigungu": {
            "강남구": {"lat": 37.5172, "lng": 127.0473, "dong": {"역삼동": {"lat": 37.5006, "lng": 127.0364}, "청담동": {"lat": 37.5260, "lng": 127.0449}}}, 
            "중구": {"lat": 37.5636, "lng": 126.9975, "dong": {"명동": {"lat": 37.5636, "lng": 126.9858}}}
        }
    },
    "부산광역시": {
        "lat": 35.1796, "lng": 129.0756, 
        "sigungu": {
            "해운대구": {"lat": 35.1631, "lng": 129.1636, "dong": {"우동": {"lat": 35.1587, "lng": 129.1398}}}
        }
    },
    "경기도": {
        "lat": 37.4138, "lng": 127.5183, 
        "sigungu": {
            "수원시": {"lat": 37.2636, "lng": 127.0286, "dong": {"권선구": {"lat": 37.2575, "lng": 126.9721}}}
        }
    }
}

GLOBAL_COORDS = {
    "우크라이나": {"lat": 50.4501, "lng": 30.5234, "label": "우크라이나 키이우"},
    "러시아": {"lat": 55.7558, "lng": 37.6173, "label": "러시아 모스크바"},
    "이란": {"lat": 35.6892, "lng": 51.3890, "label": "이란 테헤란"},
    "이스라엘": {"lat": 31.7683, "lng": 35.2137, "label": "이스라엘 예루살렘"},
    "중동": {"lat": 24.7136, "lng": 46.6753, "label": "중동 지역"},
    "미국": {"lat": 38.8951, "lng": -77.0364, "label": "미국 워싱턴D.C."},
    "중국": {"lat": 39.9042, "lng": 116.4074, "label": "중국 베이징"},
    "대만": {"lat": 25.0330, "lng": 121.5654, "label": "대만 타이베이"},
    "일본": {"lat": 35.6762, "lng": 139.6503, "label": "일본 도쿄"}
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

def format_date_with_weekday(dt):
    weekday_str = WEEKDAYS_KR[dt.weekday()]
    return f"{dt.strftime('%Y.%m.%d')} ({weekday_str})"

def categorize_incident(title, content):
    text = (title + " " + content).lower()
    
    financial_exclude_keywords = [
        '비트코인', '이더리움', '코인', '가상화폐', '암호화폐', '주가', '증시', '코스피', '코스닥', 
        '나스닥', '환율', '금리', '시세', '상장', '매수', '매도', '외국인 순매수', '주가 하락', 
        '증시 전망', '최고경영자', '사임', '합병 승인', '특검', '국정조사', '재판', '공판', '선고', '항소', '상고'
    ]
    if any(kw in text for kw in financial_exclude_keywords):
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

def extract_location(text):
    for keyword, info in GLOBAL_COORDS.items():
        if keyword in text:
            return info["label"], info["lat"], info["lng"]

    for country in WORLD_COUNTRIES:
        if country in text:
            return f"해외 분쟁지역 ({country})", 35.0, 40.0

    for sido, s_data in REGION_COORDS.items():
        if sido in text:
            for sigungu, g_data in s_data["sigungu"].items():
                if sigungu in text:
                    for dong, d_coords in g_data["dong"].items():
                        if dong in text:
                            return f"{sido} {sigungu} {dong}", d_coords["lat"], d_coords["lng"]
                    return f"{sido} {sigungu} 전체", g_data["lat"], g_data["lng"]
            return f"{sido} 중심부", s_data["lat"], s_data["lng"]
    
    return "서울특별시 중구", 37.5636, 126.9975

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
                title = translated_text.split('\n')[0][:50]
                summary = translated_text[:120] + "..."
                
                category = categorize_incident(title, translated_text)
                if not category:
                    continue

                location_str, lat, lng = extract_location(translated_text)
                real_source_name = extract_domain_source(target_link)
                
                now_dt = datetime.now(kst)
                date_str = format_date_with_weekday(now_dt)

                items.append({
                    "title": title,
                    "summary": summary,
                    "content": translated_text,
                    "location": location_str,
                    "lat": lat,
                    "lng": lng,
                    "category": category,
                    "time": date_str,
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
    five_days_ago = now - timedelta(days=5)
    collected_items = []
    
    item_id = int(now.timestamp())

    for feed_info in RSS_FEEDS:
        parsed = feedparser.parse(feed_info["url"])
        for entry in parsed.entries[:60]:
            title = entry.get("title", "")
            summary = entry.get("summary", title)
            link = entry.get("link", "")
            
            pub_dt = now
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                pub_dt = datetime.fromtimestamp(time.mktime(published_parsed), kst)
                if pub_dt < five_days_ago:
                    continue
            
            date_str = format_date_with_weekday(pub_dt)
            
            full_text = title + " " + summary
            category = categorize_incident(title, summary)
            if not category:
                continue
                
            location_str, lat, lng = extract_location(full_text)
            
            lat += (random.random() - 0.5) * 0.01
            lng += (random.random() - 0.5) * 0.01

            collected_items.append({
                "id": item_id,
                "category": category,
                "title": title,
                "summary": summary[:120] + "...",
                "content": summary,
                "location": location_str,
                "lat": round(lat, 4),
                "lng": round(lng, 4),
                "time": date_str,
                "source": feed_info["source"],
                "link": link,
                "timestamp": pub_dt.timestamp()
            })
            item_id += 1

    for channel in TELEGRAM_CHANNELS:
        tg_items = scrape_telegram_channel(channel)
        for item in tg_items:
            item["id"] = item_id
            item["lat"] = round(item["lat"] + (random.random() - 0.5) * 0.01, 4)
            item["lng"] = round(item["lng"] + (random.random() - 0.5) * 0.01, 4)
            collected_items.append(item)
            item_id += 1

    collected_items.sort(key=lambda x: x["timestamp"], reverse=True)
    return collected_items

if __name__ == "__main__":
    print("=== 실시간 뉴스 관제 크롤러가 시작되었습니다 (3분 간격 자동 실행) ===")
    while True:
        try:
            data = scrape_news()
            with open("news.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 수집 완료: 총 {len(data)}건의 기사가 news.json에 갱신되었습니다.")
        except Exception as e:
            print(f"실행 중 오류 발생: {e}")
        
        # 3분(180초) 대기 후 반복 실행
        time.sleep(180)
