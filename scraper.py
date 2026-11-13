import feedparser
from datetime import datetime
import pytz
import json
import random

# RSS 피드 소스 리스트
RSS_FEEDS = [
    {"url": "https://www.yna.co.kr/rss/news.xml", "source": "연합뉴스"},
    {"url": "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", "source": "Google News"}
]

# 3단계 지역 매핑 데이터
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

def categorize_incident(title, content):
    text = (title + " " + content).lower()
    
    # 0. 엄격한 제외 대상 (정치 공방, 경제 주가 변동, 기업 인사, 재판/수사/정치적 발언 등은 절대 안전/안보로 분류 불가)
    exclude_keywords = [
        '엔비디아', '코스피', '외국인', '매도', '하락', '상승', '주가', '증시', '최고경영자', '사임', '합병', '투자',
        '특검', '국정조사', '재판', '공판', '선고', '항소', '상고', '여야', '정치권', '규탄', '공방', 
        '토론', '사과', '반성', '회고', '기자회견', '입장문', '설명회', '무소속', '의원', '내홍', '지도부'
    ]
    if any(kw in text for kw in exclude_keywords):
        return None # 안전/안보/사건사고와 무관한 일반 경제/정치 기사는 완전히 제외

    # 1. 국가 안보 (실시간 군사적 위기, 도발, 비상조치 직접 발생)
    security_incidents = ['계엄 선포', '비상계엄', '군 병력', '도발', '미사일 발사', '영공 침범', '테러 위협', '국방 비상']
    if any(kw in text for kw in security_incidents):
        return "국가 안보"

    # 2. 강력·치안 (실시간 범죄, 112 출동, 사건 발생, 검거)
    crime_keywords = ['살인', '강도', '인질', '폭행', '흉기 난동', '마약', '긴급 체포', '수배', '112 출동', '경찰 출동', '구속영장', '투신']
    if any(kw in text for kw in crime_keywords):
        return "강력·치안"

    # 3. 사이버·금융 (해킹, 대규모 시스템 장애, 랜섬웨어 등 실제 보안 사고)
    cyber_keywords = ['해킹', '랜섬웨어', '개인정보 유출', '전산 장애', '서버 다운', '금융 사고', '보안 취약점', '스캠 피해']
    if any(kw in text for kw in cyber_keywords):
        return "사이버·금융"

    # 4. 재난·안전 (실제 화재, 폭발, 지진, 붕괴, 119 구조, 대형 교통사고 등)
    disaster_keywords = ['화재', '폭발', '붕괴', '지진', '홍수', '산사태', '침수', '119 출동', '구조', '교통 통제', '가스 유출', '정전 사고', '전복']
    if any(kw in text for kw in disaster_keywords):
        return "재난·안전"

    # 위 어떤 안전/사건사고 카테고리에도 명확히 부합하지 않으면 수집 대상에서 제외
    return None

def extract_location(text):
    for sido, s_data in REGION_COORDS.items():
        if sido in text:
            for sigungu, g_data in s_data["sigungu"].items():
                if sigungu in text:
                    for dong, d_coords in g_data["dong"].items():
                        if dong in text:
                            return sido, sigungu, dong, d_coords["lat"], d_coords["lng"]
                    return sido, sigungu, "전체 읍·면·동", g_data["lat"], g_data["lng"]
            return sido, "중구", "전체 읍·면·동", s_data["lat"], s_data["lng"]
    
    return None, None, None, None, None

def scrape_news():
    kst = pytz.timezone('Asia/Seoul')
    now = datetime.now(kst)
    collected_items = []
    
    item_id = int(now.timestamp())

    for feed_info in RSS_FEEDS:
        parsed = feedparser.parse(feed_info["url"])
        for entry in parsed.entries[:20]:
            title = entry.get("title", "")
            summary = entry.get("summary", title)
            link = entry.get("link", "")
            
            # 카테고리 판별 (기준에 맞지 않으면 버림)
            category = categorize_incident(title, summary)
            if not category:
                continue
                
            # 지역 정보 추출
            sido, sigungu, dong, lat, lng = extract_location(title + " " + summary)
            
            # 기사 내에 명확한 국내 지역(시도) 이름이 없으면 엉뚱한 곳에 찍히지 않도록 수집에서 제외
            if not sido:
                continue
            
            lat += (random.random() - 0.5) * 0.01
            lng += (random.random() - 0.5) * 0.01

            item = {
                "id": item_id,
                "category": category,
                "title": title,
                "summary": summary[:120] + "...",
                "content": summary,
                "sido": sido,
                "sigungu": sigungu,
                "dong": dong,
                "location": f"{sido} {sigungu} {dong}",
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
