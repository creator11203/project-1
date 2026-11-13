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

# 기본 뉴스 및 속보 소스
RSS_FEEDS = [
    {"url": "https://www.yna.co.kr/rss/news.xml", "source": "연합뉴스"},
    {"url": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", "source": "Google News"}
]

# 텔레그램 공개 채널
TELEGRAM_CHANNELS = [
    {"url": "https://t.me/s/FastStockNews", "source": "FastStockNews (텔레그램)"},
    {"url": "https://t.me/s/FastStockNewsUSA", "source": "FastStockNewsUSA (텔레그램)"},
    {"url": "https://t.me/s/cahier_de_market", "source": "cahier_de_market (텔레그램)"}
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
    "미국": {"lat": 38.8951, "lng": -77.0364, "label": "미국 워싱턴D.C."}
}

def categorize_incident(title, content):
    text = (title + " " + content).lower()
    
    # 경제/정치 노이즈 엄격 제외 (단, 안보/분쟁 관련 긴급 키워드가 포함된 경우는 예외 처리)
    emergency_override = ['공습', '미사일', '폭격', '전쟁', '테러', '충돌', '비상계엄', '북한 도발']
    has_emergency = any(em in text for em in emergency_override)

    if not has_emergency:
        exclude_keywords = [
            '코스피', '외국인 순매수', '주가 하락', '증시 전망', '최고경영자', '사임', '합병 승인',
            '특검', '국정조사', '재판', '공판', '선고', '항소', '상고', '여야 공방', '정치권 규탄'
        ]
        if any(kw in text for kw in exclude_keywords):
            return None 

    # 카테고리 매핑 규칙
    if any(kw in text for kw in ['우크라이나', '러시아', '이란', '이스라엘', '하마스', '헤즈볼라', '중동', '공습', '미사일', '폭격', '전쟁', '테러', '충돌', 'strike', 'war', 'attack']):
        return "해외 분쟁·테러"

    if any(kw in text for kw in ['계엄', '군 병력', '북한', '미사일 발사', '영공', '국방']):
        return "국가 안보"

    if any(kw in text for kw in ['살인', '강도', '인질', '폭행', '흉기', '마약', '긴급 체포', '수배', '경찰 출동', '구속영장']):
        return "강력·치안"

    if any(kw in text for kw in ['해킹', '랜섬웨어', '개인정보 유출', '전산 장애', '서버 다운', '금융 사고']):
        return "사이버·금융"

    if any(kw in text for kw in ['화재', '폭발', '붕괴', '지진', '홍수', '산사태', '침수', '구조', '통제', '가스 유출', '정전']):
        return "재난·안전"

    # 속보 채널 특성상 긴급 성격의 소식은 기본적으로 '해외 분쟁·테러' 또는 '재난·안전'으로 유연하게 수용
    if has_emergency:
        return "해외 분쟁·테러"

    return None

def extract_location(text):
    for keyword, info in GLOBAL_COORDS.items():
        if keyword in text:
            return info["label"], info["lat"], info["lng"]

    for sido, s_data in REGION_COORDS.items():
        if sido in text:
            for sigungu, g_data in s_data["sigungu"].items():
                if sigungu in text:
                    for dong, d_coords in g_data["dong"].items():
                        if dong in text:
                            return f"{sido} {sigungu} {dong}", d_coords["lat"], d_coords["lng"]
                    return f"{sido} {sigungu} 전체", g_data["lat"], g_data["lng"]
            return f"{sido} 중심부", s_data["lat"], s_data["lng"]
    
    return None, None, None

def scrape_telegram_channel(channel_info):
    items = []
    url = channel_info["url"]
    source_name = channel_info["source"]
    
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8')
            message_blocks = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', html, re.DOTALL)
            link_blocks = re.findall(r'<a href="(https?://[^"]+)"[^>]*>.*?</a>', html, re.DOTALL)
            
            for i, raw_msg in enumerate(message_blocks[:20]):
                clean_text = remove_html_tags(raw_msg).strip()
                if not clean_text:
                    continue
                
                urls_in_msg = re.findall(r'(https?://[^\s]+)', clean_text)
                target_link = ""
                for u in urls_in_msg:
                    if "t.me" not in u:
                        target_link = u
                        break
                
                if not target_link and i < len(link_blocks):
                    candidate = link_blocks[i]
                    if "t.me" not in candidate:
                        target_link = candidate
                
                if not target_link:
                    target_link = url

                translated_text = translate_to_korean(clean_text)
                title = translated_text.split('\n')[0][:50]
                summary = translated_text[:120] + "..."
                
                category = categorize_incident(title, translated_text)
                if not category:
                    continue

                location_str, lat, lng = extract_location(translated_text)
                if not location_str:
                    location_str, lat, lng = "미국 워싱턴D.C.", 38.8951, -77.0364

                items.append({
                    "title": title,
                    "summary": summary,
                    "content": translated_text,
                    "location": location_str,
                    "lat": lat,
                    "lng": lng,
                    "category": category,
                    "time": "최근 5일 이내",
                    "source": source_name,
                    "link": target_link
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

    # 1. RSS 뉴스 수집 (최신 5일 이내 엄격 적용)
    for feed_info in RSS_FEEDS:
        parsed = feedparser.parse(feed_info["url"])
        for entry in parsed.entries[:50]:
            title = entry.get("title", "")
            summary = entry.get("summary", title)
            link = entry.get("link", "")
            
            published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if published_parsed:
                pub_dt = datetime.fromtimestamp(time.mktime(published_parsed), kst)
                if pub_dt < five_days_ago:
                    continue
            
            full_text = title + " " + summary
            category = categorize_incident(title, summary)
            if not category:
                continue
                
            location_str, lat, lng = extract_location(full_text)
            if not location_str:
                continue
            
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
                "time": "최근 5일 이내",
                "source": feed_info["source"],
                "link": link
            })
            item_id += 1

    # 2. 텔레그램 속보 채널 수집
    for channel in TELEGRAM_CHANNELS:
        tg_items = scrape_telegram_channel(channel)
        for item in tg_items:
            item["id"] = item_id
            item["lat"] = round(item["lat"] + (random.random() - 0.5) * 0.01, 4)
            item["lng"] = round(item["lng"] + (random.random() - 0.5) * 0.01, 4)
            collected_items.append(item)
            item_id += 1

    return collected_items

if __name__ == "__main__":
    data = scrape_news()
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Successfully scraped and filtered {len(data)} valid items into news.json")
