import feedparser
import json
from datetime import datetime
import pytz
import re

# RSS 피드 리스트 (연합뉴스, YTN, 기상청/재난 속보 등)
RSS_FEEDS = [
    "https://www.yonhapnewstv.co.kr/browse/feed/",  # 연합뉴스TV 속보
    "https://www.ytn.co.kr/ln/rss.xml",             # YTN 뉴스
]

# 카테고리별 판별 키워드 매핑
CATEGORY_KEYWORDS = {
    "국가 안보": [
        "북한", "미사일", "핵", "ICBM", "방사포", "드론", "무인기", "군사분계선", "NLL", "DMZ", 
        "합참", "국방부", "한미연합훈련", "을지자유방패", "공군", "해군", "육군", "특전사", "방위비", 
        "주한미군", "대공", "테러", "방첩", "국가정보원", "안보위기", "사이버전", "정찰위성"
    ],
    "강력·치안": [
        "살인", "강도", "강간", "성폭행", "성추행", "납치", "감금", "폭행", "상해", "흉기", 
        "칼부림", "살인미수", "특수상해", "인질", "마약", "필로폰", "대마초", "조직폭력배", 
        "조폭", "도박장", "사기", "보이스피싱", "횡령", "배임", "방화", "절도", "경찰청", 
        "경찰서", "지구대", "파출소", "112", "긴급출동", "구속영장", "압수수색", "현행범", "피의자"
    ],
    "사이버·금융": [
        "랜섬웨어", "해킹", "개인정보 유출", "다크웹", "스미싱", "파밍", "디도스", "DDoS", 
        "악성코드", "정보통신망", "서버 다운", "시스템 마비", "주가조작", "불법공매도", 
        "코인 사기", "가상자산", "유사투자자문", "금융사기", "불법대부업", "PF 부실", "자금세탁"
    ],
    "재난·안전": [
        "지진", "여진", "태풍", "호우", "홍수", "폭우", "산사태", "산불", "폭설", "한파", 
        "폭염", "가뭄", "해일", "풍랑", "낙뢰", "화재", "폭발", "가스누출", "붕괴", "침수", 
        "탈선", "전복", "추돌", "충돌", "대형사고", "화학물질 누출", "정전", "단수", "싱크홀", 
        "소방서", "119", "행정안전부", "중대본", "경보", "주의보", "특보", "대피령", "재난문자"
    ]
}

# 전국 17개 시·도 및 주요 섬 지역(울릉도, 독도, 제주 등) 키워드 매핑
REGION_KEYWORDS = {
    "서울특별시": ["서울", "중구", "강남구", "송파구", "마포구", "영등포구", "역삼", "명동", "여의도"],
    "부산광역시": ["부산", "해운대", "서면", "남포동", "영도"],
    "대구광역시": ["대구", "동성로", "수성구", "달서구"],
    "인천광역시": ["인천", "송도", "영종", "강화", "옹진"],
    "광주광역시": ["광주", "상무", "충장로"],
    "대전광역시": ["대전", "둔산", "유성"],
    "울산광역시": ["울산", "삼산", "울주"],
    "세종특별자치시": ["세종", "조치원"],
    "경기도": ["경기", "수원", "성남", "고양", "용인", "화성", "동탄", "부천", "안산"],
    "강원특별자치도": ["강원", "춘천", "원주", "강릉", "속초", "동해"],
    "충청북도": ["충북", "청주", "충주", "제천"],
    "충청남도": ["충남", "천안", "아산", "서산", "당진"],
    "전북특별자치도": ["전북", "전주", "군산", "익산"],
    "전라남도": ["전남", "목포", "여수", "순천", "광양"],
    "경상북도": ["경북", "포항", "경주", "구미", "안동", "울릉", "독도"],
    "경상남도": ["경남", "창원", "김해", "진주", "거제", "통영"],
    "제주특별자치도": ["제주", "서귀포", "우도", "마라도", "제주공항"]
}

def detect_category(text):
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return cat
    return "재난·안전"  # 기본 분류

def detect_location(text):
    for sido, keywords in REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                # 시군구 추정 (간이 매핑)
                sigungu = "종합"
                if sido == "제주특별자치도":
                    sigungu = "서귀포시" if "서귀포" in text else "제주시"
                elif sido == "경상북도" and ("울릉" in text or "독도" in text):
                    sigungu = "울릉군"
                elif sido == "서울특별시":
                    if "강남" in text: sigungu = "강남구"
                    elif "중구" in text: sigungu = "중구"
                    elif "영등포" in text: sigungu = "영등포구"
                    else: sigungu = "중구"
                return sido, sigungu, "전체 읍·면·동"
    
    # 기본값 (키워드 매칭 안 될 경우 서울 중구)
    return "서울특별시", "중구", "소공동"

def fetch_news():
    collected_news = []
    kst = pytz.timezone('Asia/Seoul')
    current_time_str = datetime.now(kst).strftime("%H:%M 전파")

    item_id = 1
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]: # 피드당 최근 15개
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                link = entry.get('link', '')
                source = feed.feed.get('title', '대한민국 실시간 뉴스')

                combined_text = title + " " + summary
                
                category = detect_category(combined_text)
                sido, sigungu, dong = detect_location(combined_text)

                news_item = {
                    "id": item_id,
                    "category": category,
                    "title": title,
                    "summary": summary[:150] + "..." if len(summary) > 150 else summary,
                    "content": summary,
                    "sido": sido,
                    "sigungu": sigungu,
                    "dong": dong,
                    "location": f"{sido} {sigungu} {dong}",
                    "lat": 37.5665 + (item_id % 5) * 0.02, # 시각화용 임시 좌표 분산
                    "lng": 126.9780 + (item_id % 5) * 0.02,
                    "time": current_time_str,
                    "source": source,
                    "link": link,
                    "type": "news"
                }
                collected_news.append(news_item)
                item_id += 1
        except Exception as e:
            print(f"Error fetching RSS {url}: {e}")

    return collected_news

if __name__ == "__main__":
    news_list = fetch_news()
    
    # 결과 파일 저장
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(news_list, f, ensure_ascii=False, indent=4)
    print(f"Successfully scraped {len(news_list)} items into news.json")
