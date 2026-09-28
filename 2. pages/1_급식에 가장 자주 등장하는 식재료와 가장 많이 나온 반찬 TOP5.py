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
    "🥕 급식에 가장 자주 등장하는 식재료와 "
    "가장 많이 나온 반찬 TOP5"
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
# 급식 여러 날짜 조회
# -----------------------------

def get_meals(school, start_date, end_date):

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
# 메뉴 처리
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

    # 알레르기 번호 제거
    menu = re.sub(
        r"\([^()]*\)\s*$",
        "",
        menu,
    )

    return menu.strip()


# -----------------------------
# 식재료 추출
# -----------------------------

ingredients = [
    "김치",
    "양파",
    "대파",
    "마늘",
    "감자",
    "고구마",
    "당근",
    "호박",
    "애호박",
    "오이",
    "가지",
    "시금치",
    "부추",
    "버섯",
    "두부",
    "콩",
    "옥수수",
    "계란",
    "달걀",
    "닭고기",
    "돼지고기",
    "소고기",
    "불고기",
    "고등어",
    "오징어",
    "새우",
    "멸치",
    "참치",
    "연어",
    "미역",
    "김",
    "우유",
    "치즈",
    "참깨",
    "들깨",
]


def find_ingredients(menu):

    found = []

    for ingredient in ingredients:

        if ingredient in menu:
            found.append(ingredient)

    return found


# -----------------------------
# 학교 선택
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
            "question1_schools"
        ] = schools


if st.session_state.get(
    "question1_schools"
):

    schools = st.session_state[
        "question1_schools"
    ]

    selected = st.selectbox(
        "학교를 선택하세요.",
        range(len(schools)),
        format_func=lambda i:
            f"{schools[i]['SCHUL_NM']} "
            f"({schools[i]['LCTN_SC_NM']})",
    )

    school = schools[selected]

    st.divider()

    st.write(
        f"**선택한 학교:** "
        f"{school['SCHUL_NM']}"
    )

    st.write(
        f"**지역:** "
        f"{school['LCTN_SC_NM']}"
    )

    if st.button(
        "TOP5 분석하기",
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

            menu_counter = Counter()
            ingredient_counter = Counter()

            # 밥/국/찌개 등은 반찬 TOP5에서 제외
            exclude = [
                "밥",
                "국",
                "탕",
                "찌개",
                "죽",
                "김치",
                "깍두기",
                "후식",
                "과일",
                "음료",
                "우유",
            ]

            for meal in meals:

                menu_text = meal.get(
                    "DDISH_NM",
                    "",
                )

                for menu in split_menu(
                    menu_text
                ):

                    menu = clean_menu(menu)

                    if not menu:
                        continue

                    menu_counter[menu] += 1

                    for ingredient in find_ingredients(
                        menu
                    ):
                        ingredient_counter[
                            ingredient
                        ] += 1

            # 반찬 TOP5
            side_dishes = Counter()

            for menu, count in menu_counter.items():

                if not any(
                    menu.startswith(x)
                    for x in exclude
                ):
                    side_dishes[
                        menu
                    ] = count

            st.divider()

            # -------------------------
            # 식재료 TOP5
            # -------------------------

            st.subheader(
                "🥕 가장 자주 등장한 식재료 TOP 5"
            )

            st.caption(
                "메뉴명에 표시된 식재료 단어를 "
                "기준으로 집계했습니다."
            )

            top_ingredients = (
                ingredient_counter.most_common(5)
            )

            if top_ingredients:

                for rank, (
                    name,
                    count,
                ) in enumerate(
                    top_ingredients,
                    1,
                ):

                    st.write(
                        f"**{rank}위. {name}** "
                        f"— {count}회"
                    )

            else:

                st.info(
                    "식재료를 확인할 수 있는 "
                    "메뉴가 없습니다."
                )

            # -------------------------
            # 반찬 TOP5
            # -------------------------

            st.subheader(
                "🍱 가장 많이 나온 반찬 TOP 5"
            )

            top_side_dishes = (
                side_dishes.most_common(5)
            )

            if top_side_dishes:

                for rank, (
                    name,
                    count,
                ) in enumerate(
                    top_side_dishes,
                    1,
                ):

                    st.write(
                        f"**{rank}위. {name}** "
                        f"— {count}회"
                    )

            else:

                st.info(
                    "반찬 데이터가 없습니다."
                )
