import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

SOURCES = [
    {
        "name": "연합뉴스 속보",
        "url": "https://www.yna.co.kr/rss/news.xml",
        "category": "재난·안전",
    },
    {
        "name": "YTN 실시간 뉴스",
        "url": "https://www.ytn.co.kr/_ln/0103_rss.xml",
        "category": "재난·안전",
    },
    {
        "name": "국민재난안전포털",
        "url": "https://www.safekorea.go.kr/idsiSFK/neo/rss/rss.xml",
        "category": "재난·안전",
    },
    {
        "name": "BBC World",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "category": "국가 안보",
    },
    {
        "name": "Reuters World",
        "url": "https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best",
        "category": "국가 안보",
    },
]

# 전국 17개 시·도 및 제주·울릉도 등 도서지역 상세 키워드 매핑
REGION_KEYWORDS = {
    "제주특별자치도 제주시": ["제주", "제주시", "제주공항", "애월", "조천", "한림", "구좌", "우도"],
    "제주특별자치도 서귀포시": ["서귀포", "중문", "성산", "표선", "남원", "대정", "안덕", "마라도"],
    "경상북도 울릉군": ["울릉", "울릉도", "독도", "사동", "도동", "저동"],
    "서울특별시 중구": ["서울", "서울시", "중구", "광화문", "시청", "명동", "남대문", "강남", "역삼", "송파", "마포", "영등포"],
    "부산광역시 중구": ["부산", "부산시", "해운대", "서면", "남포동", "자갈치", "영도", "기장"],
    "대구광역시 중구": ["대구", "대구시", "동성로", "수성구", "달서구", "달성"],
    "인천광역시 중구": ["인천", "인천시", "송도", "청라", "영종도", "강화도", "백령도", "옹진"],
    "광주광역시 서구": ["광주", "광주시", "상무지구", "충장로", "수완"],
    "대전광역시 서구": ["대전", "대전시", "둔산동", "유성구", "대덕구"],
    "울산광역시 남구": ["울산", "울산시", "간절곶", "태화강", "울주"],
    "세종특별자치시": ["세종", "세종시", "조치원"],
    "경기도 수원시": ["경기", "경기도", "수원", "성남", "용인", "고양", "화성", "안양", "안산", "부천", "평택", "파주", "남양주", "의정부"],
    "강원특별자치도 강릉시": ["강원", "강원도", "춘천", "원주", "강릉", "속초", "동해", "철원", "평창", "양양"],
    "충청북도 청주시": ["충북", "충청북도", "청주", "충주", "제천", "단양"],
    "충청남도 천안시": ["충남", "충청남도", "천안", "아산", "서산", "당진", "홍성", "태안"],
    "전북특별자치도 전주시": ["전북", "전라북도", "전주", "군산", "익산", "정읍", "남원", "부안"],
    "전라남도 목포시": ["전남", "전라남도", "목포", "여수", "순천", "광양", "완도", "진도", "흑산도", "신안"],
    "경상북도 포항시": ["경북", "경상북도", "포항", "경주", "구미", "안동", "영주", "문경"],
    "경상남도 창원시": ["경남", "경상남도", "창원", "김해", "진주", "거제", "통영", "남해", "사천"]
}

def detect_location(text):
    for location, keywords in REGION_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return location
    return "서울특별시 중구"

def fetch_rss(source):
    items = []
    try:
        req = urllib.request.Request(
            source["url"], 
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                description = item.find("description")
                
                title_text = title.text.strip() if title is not None and title.text else "제목 없음"
                link_text = link.text.strip() if link is not None and link.text else "#"
                
                desc_text = ""
                if description is not None and description.text:
                    desc_text = description.text.strip()
                    for tag in ["<p>", "</p>", "<br>", "<b>", "</b>"]:
                        desc_text = desc_text.replace(tag, "")

                full_text = title_text + " " + desc_text
                
                if "BBC" in source["name"] or "Reuters" in source["name"]:
                    location = "글로벌"
                else:
                    location = detect_location(full_text)

                items.append({
                    "title": title_text,
                    "summary": desc_text[:150] + "..." if len(desc_text) > 150 else desc_text,
                    "link": link_text,
                    "source": source["name"],
                    "category": source["category"],
                    "published": pub_date.text if pub_date is not None and pub_date.text else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "location": location
                })
    except Exception as e:
        print(f"Error fetching {source['name']}: {e}")
    
    return items

def main():
    all_news = []
    for source in SOURCES:
        print(f"Fetching from {source['name']}...")
        news_items = fetch_rss(source)
        all_news.extend(news_items)
    
    output_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "incidents": all_news if all_news else [
            {
                "title": "[안내] 실시간 뉴스 수집 중",
                "summary": "RSS 피드로부터 데이터를 불러오는 중입니다.",
                "link": "#",
                "source": "시스템 안내",
                "category": "재난·안전",
                "published": "방금 전",
                "location": "서울특별시 중구"
            }
        ]
    }
    
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
    print("news.json updated successfully.")

if __name__ == "__main__":
    main()
