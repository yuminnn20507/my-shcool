import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st


SCHOOL_API_URL = "https://open.neis.go.kr/hub/schoolInfo"
MEAL_API_URL = "https://open.neis.go.kr/hub/mealServiceDietInfo"

KST = ZoneInfo("Asia/Seoul")


st.set_page_config(
    page_title="학교 급식",
    page_icon="🍚",
)

st.title("🍚 학교 급식 조회")


# -----------------------------
# 학교 검색
# -----------------------------

def search_school(name):
    params = {
        "Type": "json",
        "SCHUL_NM": name,
    }

    try:
        response = requests.get(
            SCHOOL_API_URL,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

    except Exception:
        return None

    school_info = data.get("schoolInfo")

    if not school_info or len(school_info) < 2:
        return []

    return school_info[1].get("row", [])


def change_short_name(name):
    """학교 이름 줄임말을 정식 이름 형태로 바꾼다."""

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


def search_school_with_fallback(name):
    # 먼저 사용자가 입력한 이름 그대로 검색
    schools = search_school(name)

    if schools:
        return schools

    # 결과가 없을 때만 줄임말을 풀어서 검색
    changed_name = change_short_name(name)

    if changed_name == name:
        return []

    return search_school(changed_name)


# -----------------------------
# 급식 조회
# -----------------------------

def get_meal(school, date):
    date_text = date.strftime("%Y%m%d")

    params = {
        "Type": "json",
        "ATPT_OFCDC_SC_CODE":
            school["ATPT_OFCDC_SC_CODE"],
        "SD_SCHUL_CODE":
            school["SD_SCHUL_CODE"],
        "MMEAL_SC_CODE": "2",
        "MLSV_FROM_YMD": date_text,
        "MLSV_TO_YMD": date_text,
        "pSize": "5",
        "pIndex": "1",
    }

    try:
        response = requests.get(
            MEAL_API_URL,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

    except Exception:
        return None

    meal_info = data.get("mealServiceDietInfo")

    if not meal_info or len(meal_info) < 2:
        return []

    return meal_info[1].get("row", [])


# -----------------------------
# 학교 입력
# -----------------------------

st.subheader("🏫 학교 찾기")

school_name = st.text_input(
    "학교 이름을 입력하세요",
    placeholder="예: 수도여고",
)

if st.button("학교 검색", type="primary"):

    if not school_name.strip():
        st.warning("학교 이름을 입력해 주세요.")

    else:

        with st.spinner("학교를 찾는 중..."):
            schools = search_school_with_fallback(
                school_name
            )

        if not schools:

            st.info(
                "검색된 학교가 없습니다. "
                "학교 이름을 다시 확인해 주세요."
            )

            st.session_state["schools"] = []

        else:

            st.session_state["schools"] = schools


# -----------------------------
# 학교 선택
# -----------------------------

if st.session_state.get("schools"):

    schools = st.session_state["schools"]

    st.subheader("학교 선택")

    selected_index = st.selectbox(
        "검색된 학교를 선택하세요.",
        range(len(schools)),
        format_func=lambda i:
            f"{schools[i]['SCHUL_NM']} "
            f"({schools[i]['LCTN_SC_NM']})",
    )

    school = schools[selected_index]

    st.session_state["selected_school"] = school


# -----------------------------
# 날짜 선택
# -----------------------------

if st.session_state.get("selected_school"):

    school = st.session_state["selected_school"]

    st.divider()

    st.subheader("📅 급식 날짜")

    # 배포 서버 시간이 한국 시간이 아니어도
    # 한국 시간 기준 오늘 날짜를 사용한다.
    today = datetime.now(KST).date()

    selected_date = st.date_input(
        "날짜를 선택하세요.",
        value=today,
    )

    st.write(
        f"**학교:** {school['SCHUL_NM']}"
    )

    st.write(
        f"**지역:** {school['LCTN_SC_NM']}"
    )

    st.divider()

    # -----------------------------
    # 급식 조회
    # -----------------------------

    meals = get_meal(
        school,
        selected_date,
    )

    if not meals:

        st.info(
            "선택한 날짜에는 등록된 중식 급식이 없습니다."
        )

    else:

        meal = meals[0]

        st.subheader("🍚 중식")

        menu_text = meal.get(
            "DDISH_NM",
            "",
        )

        menus = re.split(
            r"<br\s*/?>",
            menu_text,
            flags=re.IGNORECASE,
        )

        for menu in menus:

            menu = menu.strip()

            if menu:
                st.markdown(
                    f"- {menu}"
                )

        calorie = meal.get(
            "CAL_INFO",
            "",
        )

        if calorie:
            st.metric(
                "칼로리",
                calorie,
            )
