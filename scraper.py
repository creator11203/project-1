import feedparser
from datetime import datetime
import pytz
import json
import random

# 국내외 주요 RSS 피드 소스 리스트
RSS_FEEDS = [
    {"url": "https://www.yna.co.kr/rss/news.xml", "source": "연합뉴스"},
    {"url": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", "source": "Google News"}
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
    
    # 제외 대상 (경제, 주가, 연예, 사후 정치 공방 등)
    exclude_keywords = [
        '엔비디아', '코스피', '외국인', '매도', '하락', '상승', '주가', '증시', '최고경영자', '사임', '합병', '투자',
        '특검', '국정조사', '재판', '공판', '선고', '항소', '상고', '여야', '정치권', '규탄', '공방', 
        '토론', '사과', '반성', '회고', '기자회견', '입장문', '설명회', '무소속', '의원', '내홍', '지도부'
    ]
    if any(kw in text for kw in exclude_keywords):
        return None 

    # 1. 해외 분쟁·테러 (우크라이나, 러시아, 이란, 전쟁, 공습, 미사일 공격, 테러 등)
    global_conflict_keywords = [
        '우크라이나', '러시아', '이란', '이스라엘', '하마스', '헤즈볼라', '중동 전쟁', 
        '공습', '미사일 공격', '폭격', '전쟁', '테러', '무력 충돌', '군사 작전', '드론 공격'
    ]
    if any(kw in text for kw in global_conflict_keywords):
        return "해외 분쟁·테러"

    # 2. 국가 안보 (국내 군사적 위기, 북한 도발 등)
    security_incidents = ['계엄 선포', '비상계엄', '군 병력', '북한 도발', '미사일 발사', '영공 침범', '국방 비상']
    if any(kw in text for kw in security_incidents):
        return "국가 안보"

    # 3. 강력·치안
    crime_keywords = ['살인', '강도', '인질', '폭행', '흉기 난동', '마약', '긴급 체포', '수배', '112 출동', '경찰 출동', '구속영장', '투신']
    if any(kw in text for kw in crime_keywords):
        return "강력·치안"

    # 4. 사이버·금융
    cyber_keywords = ['해킹', '랜섬웨어', '개인정보 유출', '전산 장애', '서버 다운', '금융 사고', '보안 취약점', '스캠 피해']
    if any(kw in text for kw in cyber_keywords):
        return "사이버·금융"

    # 5. 재난·안전
    disaster_keywords = ['화재', '폭발', '붕괴', '지진', '홍수', '산사태', '침수', '119 출동', '구조', '교통 통제', '가스 유출', '정전 사고', '전복']
    if any(kw in text for kw in disaster_keywords):
        return "재난·안전"

    return None

def extract_location(text):
    # 1. 해외 분쟁 지역 키워드 매칭 우선 검사
    for keyword, info in GLOBAL_COORDS.items():
        if keyword in text:
            return info["label"], info["lat"], info["lng"]

    # 2. 국내 지역 매칭 검사
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

def scrape_news():
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    collected_items = []
    
    item_id = int(now.timestamp())

    for feed_info in RSS_FEEDS:
        parsed = feedparser.parse(feed_info["url"])
        for entry in parsed.entries[:25]:
            title = entry.get("title", "")
            summary = entry.get("summary", title)
            link = entry.get("link", "")
            
            full_text = title + " " + summary
            
            category = categorize_incident(title, summary)
            if not category:
                continue
                
            location_str, lat, lng = extract_location(full_text)
            if not location_str:
                continue  # 지역 정보가 명확히 매칭되지 않으면 제외
            
            lat += (random.random() - 0.5) * 0.01
            lng += (random.random() - 0.5) * 0.01

            item = {
                "id": item_id,
                "category": category,
                "title": title,
                "summary": summary[:120] + "...",
                "content": summary,
                "location": location_str,
                "lat": round(lat, 4),
                "lng": round(lng, 4),
                "time": "방금 전",
                "source": feed_info["source"],
                "link": link
            }
            collected_items.append(item)
            item_id += 1

    return collected_items

if __name__ == "__main__":
    data = scrape_news()
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Successfully scraped and filtered {len(data)} items into news.json")
