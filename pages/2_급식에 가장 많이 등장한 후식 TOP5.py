import re
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st


MEAL_API_URL = (
    "https://open.neis.go.kr/hub/mealServiceDietInfo"
)

KST = ZoneInfo("Asia/Seoul")


st.title(
    "🍎 급식에 가장 많이 등장한 후식 TOP5"
)


# -----------------------------
# 학교 검색
# -----------------------------

def search_school(name):

    url = (
        "https://open.neis.go.kr/hub/schoolInfo"
    )

    params = {
        "Type": "json",
        "SCHUL_NM": name,
    }

    try:

        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

        response.raise_for_status()

        data = response.json()

    except Exception:

        return []

    school_info = data.get("schoolInfo")

    if not school_info or len(school_info) < 2:
        return []

    return school_info[1].get("row", [])


def change_short_name(name):

    name = name.strip()

    if "고등학교" in name:
        return name

    if "여고" in name:
        return name.replace(
            "여고",
            "여자고등학교",
        )

    if name.endswith("고"):
        return name[:-1] + "고등학교"

    return name


def find_school(name):

    schools = search_school(name)

    if schools:
        return schools

    changed = change_short_name(name)

    if changed == name:
        return []

    return search_school(changed)


# -----------------------------
# 최근 1년 급식 조회
# -----------------------------

def get_meals(
    school,
    start_date,
    end_date,
):

    meals = []

    current = start_date

    while current <= end_date:

        chunk_end = min(
            current + timedelta(days=4),
            end_date,
        )

        params = {
            "Type": "json",
            "ATPT_OFCDC_SC_CODE":
                school["ATPT_OFCDC_SC_CODE"],
            "SD_SCHUL_CODE":
                school["SD_SCHUL_CODE"],
            "MMEAL_SC_CODE": "2",
            "MLSV_FROM_YMD":
                current.strftime("%Y%m%d"),
            "MLSV_TO_YMD":
                chunk_end.strftime("%Y%m%d"),
            "pSize": "5",
            "pIndex": "1",
        }

        try:

            response = requests.get(
                MEAL_API_URL,
                params=params,
                timeout=15,
            )

            response.raise_for_status()

            data = response.json()

        except Exception:

            current = (
                chunk_end
                + timedelta(days=1)
            )

            continue

        meal_info = data.get(
            "mealServiceDietInfo"
        )

        if meal_info and len(meal_info) >= 2:

            rows = meal_info[1].get(
                "row",
                [],
            )

            meals.extend(rows)

        current = (
            chunk_end
            + timedelta(days=1)
        )

    return meals


# -----------------------------
# 메뉴 분리
# -----------------------------

def split_menu(menu_text):

    return [
        x.strip()
        for x in re.split(
            r"<br\s*/?>",
            menu_text,
            flags=re.IGNORECASE,
        )
        if x.strip()
    ]


def clean_menu(menu):

    return re.sub(
        r"\([^()]*\)\s*$",
        "",
        menu,
    ).strip()


# -----------------------------
# 후식 판단
# -----------------------------

dessert_words = [
    "후식",
    "과일",
    "사과",
    "배",
    "바나나",
    "귤",
    "감귤",
    "오렌지",
    "포도",
    "딸기",
    "수박",
    "복숭아",
    "키위",
    "파인애플",
    "망고",
    "멜론",
    "참외",
    "요구르트",
    "요거트",
    "우유",
    "두유",
    "주스",
    "음료",
    "아이스크림",
    "케이크",
    "빵",
    "쿠키",
    "떡",
    "푸딩",
    "젤리",
    "초콜릿",
    "마카롱",
    "와플",
    "팬케이크",
]


def is_dessert(menu):

    for word in dessert_words:

        if word in menu:
            return True

    return False


# -----------------------------
# 학교 검색
# -----------------------------

school_name = st.text_input(
    "학교 이름을 입력하세요.",
    placeholder="예: 수도여고",
)

if st.button(
    "학교 검색",
    type="primary",
):

    schools = find_school(
        school_name
    )

    if not schools:

        st.warning(
            "검색된 학교가 없습니다."
        )

    else:

        st.session_state[
            "question2_schools"
        ] = schools


# -----------------------------
# 학교 선택
# -----------------------------

if st.session_state.get(
    "question2_schools"
):

    schools = st.session_state[
        "question2_schools"
    ]

    selected = st.selectbox(
        "학교를 선택하세요.",
        range(len(schools)),
        format_func=lambda i:
            f"{schools[i]['SCHUL_NM']} "
            f"({schools[i]['LCTN_SC_NM']})",
    )

    school = schools[selected]

    st.write(
        f"**선택한 학교:** "
        f"{school['SCHUL_NM']}"
    )

    st.write(
        f"**지역:** "
        f"{school['LCTN_SC_NM']}"
    )

    if st.button(
        "후식 TOP5 분석하기",
        type="primary",
    ):

        today = datetime.now(KST).date()

        start = today - timedelta(
            days=364
        )

        with st.spinner(
            "최근 1년 급식을 분석하는 중..."
        ):

            meals = get_meals(
                school,
                start,
                today,
            )

        if not meals:

            st.info(
                "분석할 급식 데이터가 없습니다."
            )

        else:

            dessert_counter = Counter()

            for meal in meals:

                menu_text = meal.get(
                    "DDISH_NM",
                    "",
                )

                for menu in split_menu(
                    menu_text
                ):

                    menu = clean_menu(menu)

                    if is_dessert(menu):

                        dessert_counter[
                            menu
                        ] += 1

            top5 = (
                dessert_counter.most_common(5)
            )

            st.divider()

            st.subheader(
                "🍎 급식에 가장 많이 등장한 후식 TOP 5"
            )

            if top5:

                for rank, (
                    name,
                    count,
                ) in enumerate(
                    top5,
                    1,
                ):

                    st.write(
                        f"**{rank}위. {name}** "
                        f"— {count}회"
                    )

            else:

                st.info(
                    "후식으로 분류할 수 있는 "
                    "메뉴가 없습니다."
                )
