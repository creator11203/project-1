import feedparser
from datetime import datetime, timedelta
import time
import pytz
import json
import random
import urllib.request
import re
from html.parser import HTMLParser

# HTML 태그 제거용 유틸리티
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

# RSS 피드 소스 리스트
RSS_FEEDS = [
    {"url": "https://www.yna.co.kr/rss/news.xml", "source": "연합뉴스"},
    {"url": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", "source": "Google News"}
]

# 연동할 텔레그램 공개 채널 목록 (t.me/s/ 형태의 웹 미리보기 페이지 활용)
TELEGRAM_CHANNELS = [
    {"url": "https://t.me/s/FastStockNews", "source": "FastStockNews (텔레그램)"},
    {"url": "https://t.me/s/FastStockNewsUSA", "source": "FastStockNewsUSA (텔레그램)"},
    {"url": "https://t.me/s/cahier_de_market", "source": "cahier_de_market (텔레그램)"}
]

# 3단계 국내 지역 매핑 데이터
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

# 해외 주요 분쟁 지역 및 도시 좌표 매핑
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
    
    exclude_keywords = [
        '코스피', '외국인', '매도', '하락', '상승', '주가', '증시', '최고경영자', '사임', '합병', '투자',
        '특검', '국정조사', '재판', '공판', '선고', '항소', '상고', '여야', '정치권', '규탄', '공방', 
        '토론', '사과', '반성', '회고', '기자회견', '입장문', '설명회', '무소속', '의원', '내홍', '지도부'
    ]
    if any(kw in text for kw in exclude_keywords):
        return None 

    global_conflict_keywords = [
        '우크라이나', '러시아', '이란', '이스라엘', '하마스', '헤즈볼라', '중동 전쟁', 
        '공습', '미사일 공격', '폭격', '전쟁', '테러', '무력 충돌', '군사 작전', '드론 공격'
    ]
    if any(kw in text for kw in global_conflict_keywords):
        return "해외 분쟁·테러"

    security_incidents = ['계엄 선포', '비상계엄', '군 병력', '북한 도발', '미사일 발사', '영공 침범', '국방 비상']
    if any(kw in text for kw in security_incidents):
        return "국가 안보"

    crime_keywords = ['살인', '강도', '인질', '폭행', '흉기 난동', '마약', '긴급 체포', '수배', '112 출동', '경찰 출동', '구속영장', '투신']
    if any(kw in text for kw in crime_keywords):
        return "강력·치안"

    cyber_keywords = ['해킹', '랜섬웨어', '개인정보 유출', '전산 장애', '서버 다운', '금융 사고', '보안 취약점', '스캠 피해']
    if any(kw in text for kw in cyber_keywords):
        return "사이버·금융"

    disaster_keywords = ['화재', '폭발', '붕괴', '지진', '홍수', '산사태', '침수', '119 출동', '구조', '교통 통제', '가스 유출', '정전 사고', '전복']
    if any(kw in text for kw in disaster_keywords):
        return "재난·안전"

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
            
            # 텔레그램 웹 미리보기 페이지에서 메시지 박스 추출
            message_blocks = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', html, re.DOTALL)
            link_blocks = re.findall(r'<a href="(https?://[^"]+)"[^>]*>.*?</a>', html, re.DOTALL)
            
            for i, raw_msg in enumerate(message_blocks[:15]):
                clean_text = remove_html_tags(raw_msg).strip()
                if not clean_text:
                    continue
                
                # 메시지 본문 안에 포함된 외부 링크 추출 시도
                urls_in_msg = re.findall(r'(https?://[^\s]+)', clean_text)
                target_link = ""
                for u in urls_in_msg:
                    # 텔레그램 자체 링크나 단축 링크가 아닌 실제 원문 링크 우선 선택
                    if "t.me" not in u:
                        target_link = u
                        break
                
                # 본문에 링크가 없으면 채널 포스트에 포함된 외부 링크 매칭 시도
                if not target_link and i < len(link_blocks):
                    candidate = link_blocks[i]
                    if "t.me" not in candidate:
                        target_link = candidate
                
                # 만약 원문 링크를 못 찾았으면 기본 채널 링크 사용
                if not target_link:
                    target_link = url

                title = clean_text.split('\n')[0][:50]
                summary = clean_text[:120] + "..."
                
                category = categorize_incident(title, clean_text)
                if not category:
                    # 카테고리가 안 잡히면 기본적으로 분쟁/안전 관련일 때 '해외 분쟁·테러' 또는 기본 분류 부여
                    if any(w in clean_text.lower() for w in ['우크라이나', '러시아', '이란', '미국', '전쟁', '공습', '충돌']):
                        category = "해외 분쟁·테러"
                    else:
                        continue

                location_str, lat, lng = extract_location(clean_text)
                if not location_str:
                    # 위치가 명시되지 않은 글로벌 채널 기사는 미국/중동 기본값 또는 우크라이나 매칭
                    location_str, lat, lng = "미국 워싱턴D.C.", 38.8951, -77.0364

                items.append({
                    "title": title,
                    "summary": summary,
                    "content": clean_text,
                    "location": location_str,
                    "lat": lat,
                    "lng": lng,
                    "category": category,
                    "time": "최근 5일 이내",
                    "source": source_name,
                    "link": target_link  # 원문 기사/웹사이트 링크로 대체됨
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

    # 1. 기존 RSS 뉴스 수집
    for feed_info in RSS_FEEDS:
        parsed = feedparser.parse(feed_info["url"])
        for entry in parsed.entries[:40]:
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

    # 2. 텔레그램 공개 채널 수집 및 원문 링크 매핑
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
    print(f"Successfully scraped and filtered {len(data)} items (including Telegram) into news.json")
