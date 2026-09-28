import re
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st


# ============================================================
# 기본 설정
# ============================================================

SCHOOL_API_URL = "https://open.neis.go.kr/hub/schoolInfo"
MEAL_API_URL = "https://open.neis.go.kr/hub/mealServiceDietInfo"

KST = ZoneInfo("Asia/Seoul")

APP_TITLE = "급식에 가장 자주 등장하는 식재료와 가장많이 나온 반찬 top5"


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🍚",
    layout="centered",
)

st.title(APP_TITLE)


# ============================================================
# 세션 상태
# ============================================================

if "schools" not in st.session_state:
    st.session_state.schools = []

if "selected_school" not in st.session_state:
    st.session_state.selected_school = None

if "analysis_data" not in st.session_state:
    st.session_state.analysis_data = None


# ============================================================
# 학교 검색
# ============================================================

def search_schools(school_name):
    """나이스 학교기본정보 API로 학교를 검색한다."""

    params = {
        "Type": "json",
        "SCHUL_NM": school_name,
    }

    try:
        response = requests.get(
            SCHOOL_API_URL,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

    except (requests.RequestException, ValueError):
        return None, "api_error"

    school_info = data.get("schoolInfo")

    if not school_info or len(school_info) < 2:
        return [], "no_data"

    rows = school_info[1].get("row", [])

    if not rows:
        return [], "no_data"

    return rows, "success"


def make_fallback_school_name(name):
    """
    학교 이름 축약어를 정식 학교명 형태로 바꾼다.

    수도여고 -> 수도여자고등학교
    서울여고 -> 서울여자고등학교
    서울고 -> 서울고등학교
    """

    result = name.strip()

    # 이미 '고등학교'가 들어 있으면 변경하지 않는다.
    if "고등학교" in result:
        return result

    # 여고 -> 여자고등학교
    if "여고" in result:
        result = result.replace(
            "여고",
            "여자고등학교",
        )
        return result

    # 마지막 글자가 '고'일 때만 고등학교로 변경
    if result.endswith("고"):
        result = result[:-1] + "고등학교"

    return result


def search_schools_with_fallback(school_name):
    """일반 검색 후 결과가 없으면 축약어를 풀어서 재검색한다."""

    school_name = school_name.strip()

    if not school_name:
        return [], "empty"

    # 첫 번째 검색
    schools, status = search_schools(school_name)

    if status == "api_error":
        return None, "api_error"

    if schools:
        return schools, "success"

    # 두 번째 검색
    fallback_name = make_fallback_school_name(school_name)

    if fallback_name == school_name:
        return [], "no_data"

    schools, status = search_schools(fallback_name)

    if status == "api_error":
        return None, "api_error"

    if schools:
        return schools, "success"

    return [], "no_data"


# ============================================================
# 급식 데이터 조회
# ============================================================

def get_meals_for_period(school, start_date, end_date):
    """
    인증키 없이 사용할 때 나이스 API가 첫 5건만 반환하므로
    5일 단위로 여러 번 요청해서 전체 기간을 수집한다.

    반환값:
        meals: 날짜별 급식 데이터 목록
        status: success / no_data / api_error
    """

    all_meals = []

    current_date = start_date

    while current_date <= end_date:

        # 인증키가 없을 때 최대 5건만 받으므로
        # 5일 단위로 조회한다.
        chunk_end = min(
            current_date + timedelta(days=4),
            end_date,
        )

        params = {
            "Type": "json",
            "ATPT_OFCDC_SC_CODE": school[
                "ATPT_OFCDC_SC_CODE"
            ],
            "SD_SCHUL_CODE": school[
                "SD_SCHUL_CODE"
            ],
            "MMEAL_SC_CODE": "2",
            "MLSV_FROM_YMD": current_date.strftime(
                "%Y%m%d"
            ),
            "MLSV_TO_YMD": chunk_end.strftime(
                "%Y%m%d"
            ),
            "pSize": "1000",
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

        except (requests.RequestException, ValueError):
            return None, "api_error"

        meal_service = data.get(
            "mealServiceDietInfo"
        )

        if meal_service and len(meal_service) >= 2:
            rows = meal_service[1].get(
                "row",
                [],
            )

            if rows:
                all_meals.extend(rows)

        current_date = chunk_end + timedelta(days=1)

    if not all_meals:
        return [], "no_data"

    return all_meals, "success"


# ============================================================
# 메뉴 처리
# ============================================================

def split_menu(menu_text):
    """<br/>로 연결된 메뉴를 개별 메뉴로 분리한다."""

    if not menu_text:
        return []

    menus = re.split(
        r"<br\s*/?>",
        menu_text,
        flags=re.IGNORECASE,
    )

    return [
        menu.strip()
        for menu in menus
        if menu.strip()
    ]


def remove_allergy_numbers(menu):
    """
    메뉴 뒤의 알레르기 번호를 제거한다.

    예:
    김치찌개(5.6.9) -> 김치찌개

    통계 계산을 위한 용도이며,
    화면에 표시하는 원래 메뉴에는 적용하지 않는다.
    """

    return re.sub(
        r"\(\s*\d+(?:\.\d+)*\s*\)\s*$",
        "",
        menu,
    ).strip()


def normalize_menu(menu):
    """통계용 메뉴 이름을 정리한다."""

    menu = remove_allergy_numbers(menu)

    # 앞뒤 특수문자와 공백 정리
    menu = re.sub(
        r"^[\s\-•·]+|[\s\-•·]+$",
        "",
        menu,
    )

    return menu.strip()


# ============================================================
# 식재료 추출
# ============================================================

# 메뉴명에 자주 등장하는 식재료 후보.
# 나이스 API에는 실제 재료 정보가 없기 때문에
# 메뉴명에 나타난 단어를 기반으로 통계를 낸다.

INGREDIENT_KEYWORDS = [
    "김치",
    "배추",
    "무",
    "양파",
    "대파",
    "파",
    "마늘",
    "고추",
    "고추장",
    "된장",
    "간장",
    "두부",
    "콩",
    "검은콩",
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
    "표고",
    "팽이",
    "새송이",
    "브로콜리",
    "옥수수",
    "계란",
    "달걀",
    "닭",
    "닭고기",
    "돼지",
    "돼지고기",
    "소고기",
    "쇠고기",
    "불고기",
    "갈비",
    "고등어",
    "오징어",
    "새우",
    "멸치",
    "참치",
    "연어",
    "미역",
    "다시마",
    "김",
    "우유",
    "치즈",
    "두유",
    "버섯",
    "참깨",
    "들깨",
    "깨",
    "땅콩",
]


def extract_ingredients(menu):
    """
    메뉴 이름에서 알려진 식재료 단어를 찾아낸다.

    실제 조리 재료 데이터가 아니므로
    '메뉴명에서 확인되는 식재료' 통계이다.
    """

    clean_menu = remove_allergy_numbers(menu)

    found = []

    for ingredient in INGREDIENT_KEYWORDS:
        if ingredient in clean_menu:
            found.append(ingredient)

    # 더 구체적인 단어가 있으면 일반적인 단어와 중복될 수 있으므로
    # 일부 중복을 제거한다.
    if "닭고기" in found and "닭" in found:
        found.remove("닭")

    if "돼지고기" in found and "돼지" in found:
        found.remove("돼지")

    if "소고기" in found and "쇠고기" in found:
        found.remove("쇠고기")

    if "달걀" in found and "계란" in found:
        found.remove("계란")

    if "애호박" in found and "호박" in found:
        found.remove("호박")

    return found


# ============================================================
# TOP 5 분석
# ============================================================

def analyze_meals(meals):
    """급식 데이터를 분석해 반찬과 식재료 TOP 5를 계산한다."""

    menu_counter = Counter()
    ingredient_counter = Counter()

    # 밥 / 국 / 찌개 / 김치 / 후식 등을 구분하기 위한
    # 간단한 제외 목록
    side_dish_exclude = [
        "밥",
        "국",
        "탕",
        "찌개",
        "죽",
        "스프",
        "스프",
        "김치",
        "깍두기",
        "열무김치",
        "배추김치",
        "총각김치",
        "나박김치",
        "동치미",
        "후식",
        "과일",
        "주스",
        "음료",
        "우유",
    ]

    for meal in meals:

        menu_text = meal.get(
            "DDISH_NM",
            "",
        )

        menus = split_menu(menu_text)

        for menu in menus:

            clean_menu = normalize_menu(menu)

            if not clean_menu:
                continue

            # 모든 메뉴의 등장 횟수
            menu_counter[clean_menu] += 1

            # 식재료 추출
            ingredients = extract_ingredients(
                clean_menu
            )

            for ingredient in ingredients:
                ingredient_counter[
                    ingredient
                ] += 1

    # 반찬 TOP5
    side_dish_counter = Counter()

    for menu, count in menu_counter.items():

        # 밥/국/찌개/후식 등은 반찬 통계에서 제외
        is_excluded = False

        for word in side_dish_exclude:
            if menu.startswith(word):
                is_excluded = True
                break

        if not is_excluded:
            side_dish_counter[menu] = count

    return (
        ingredient_counter.most_common(5),
        side_dish_counter.most_common(5),
    )


# ============================================================
# 학교 검색 화면
# ============================================================

st.subheader("🏫 학교 찾기")

school_name = st.text_input(
    "학교 이름을 입력하세요",
    placeholder="예: 수도여고",
)

if st.button(
    "학교 검색",
    type="primary",
):

    if not school_name.strip():

        st.warning(
            "학교 이름을 입력해 주세요."
        )

        st.session_state.schools = []
        st.session_state.selected_school = None

    else:

        with st.spinner(
            "학교를 찾는 중입니다..."
        ):
            schools, status = (
                search_schools_with_fallback(
                    school_name
                )
            )

        if status == "api_error":

            st.error(
                "학교 정보를 불러오는 중 문제가 발생했습니다. "
                "잠시 후 다시 시도해 주세요."
            )

            st.session_state.schools = []
            st.session_state.selected_school = None

        elif not schools:

            st.info(
                "검색된 학교가 없습니다. "
                "학교 이름을 다시 확인해 주세요."
            )

            st.session_state.schools = []
            st.session_state.selected_school = None

        else:

            st.session_state.schools = schools
            st.session_state.selected_school = None

            st.success(
                f"{len(schools)}개의 학교를 찾았습니다."
            )


# ============================================================
# 학교 선택
# ============================================================

if st.session_state.schools:

    st.subheader("학교 선택")

    schools = st.session_state.schools

    def school_label(school):
        name = school.get(
            "SCHUL_NM",
            "학교명 없음",
        )

        region = school.get(
            "LCTN_SC_NM",
            "지역 정보 없음",
        )

        return f"{name} ({region})"

    selected_index = st.selectbox(
        "검색된 학교 중 하나를 선택하세요",
        range(len(schools)),
        format_func=lambda index:
            school_label(schools[index]),
    )

    st.session_state.selected_school = (
        schools[selected_index]
    )


# ============================================================
# 날짜 선택
# ============================================================

if st.session_state.selected_school:

    st.divider()

    st.subheader("📅 급식 날짜")

    # 반드시 한국 시간 기준으로 오늘 날짜 계산
    today_kst = datetime.now(KST).date()

    selected_date = st.date_input(
        "날짜를 선택하세요",
        value=today_kst,
    )

    selected_school = (
        st.session_state.selected_school
    )

    st.caption(
        f"선택한 학교: "
        f"{selected_school.get('SCHUL_NM', '')} "
        f"({selected_school.get('LCTN_SC_NM', '')})"
    )

    # ========================================================
    # 선택한 날짜의 급식
    # ========================================================

    st.subheader("🍚 오늘의 중식")

    with st.spinner(
        "급식 정보를 불러오는 중입니다..."
    ):

        one_day_meals, meal_status = (
            get_meals_for_period(
                selected_school,
                selected_date,
                selected_date,
            )
        )

    if meal_status == "api_error":

        st.error(
            "급식 정보를 불러오는 중 문제가 발생했습니다. "
            "잠시 후 다시 시도해 주세요."
        )

    elif not one_day_meals:

        st.info(
            "선택한 날짜에는 등록된 중식 급식이 없습니다."
        )

    else:

        # 선택 날짜에 해당하는 데이터만 찾는다.
        target_date = selected_date.strftime(
            "%Y%m%d"
        )

        today_meals = [
            meal
            for meal in one_day_meals
            if meal.get("MLSV_YMD")
            == target_date
        ]

        if not today_meals:

            st.info(
                "선택한 날짜에는 등록된 중식 급식이 없습니다."
            )

        else:

            meal = today_meals[0]

            menus = split_menu(
                meal.get(
                    "DDISH_NM",
                    "",
                )
            )

            for menu in menus:
                st.markdown(
                    f"- {menu}"
                )

            cal_info = meal.get(
                "CAL_INFO",
                "",
            )

            if cal_info:
                st.metric(
                    "칼로리",
                    cal_info,
                )

    # ========================================================
    # 최근 1년 TOP 5 분석
    # ========================================================

    st.divider()

    st.subheader(
        "📊 최근 1년 급식 TOP 5"
    )

    st.caption(
        "최근 1년간 등록된 중식 메뉴를 기준으로 계산합니다."
    )

    if st.button(
        "최근 1년 TOP 5 분석하기",
        type="secondary",
    ):

        # 분석 기간
        analysis_end = today_kst
        analysis_start = (
            analysis_end
            - timedelta(days=364)
        )

        with st.spinner(
            "최근 1년간 급식 데이터를 분석하고 있습니다..."
        ):

            meals, status = (
                get_meals_for_period(
                    selected_school,
                    analysis_start,
                    analysis_end,
                )
            )

        if status == "api_error":

            st.error(
                "급식 데이터를 불러오는 중 문제가 발생했습니다. "
                "잠시 후 다시 시도해 주세요."
            )

        elif not meals:

            st.info(
                "분석할 급식 데이터가 없습니다."
            )

        else:

            ingredients_top5, side_dishes_top5 = (
                analyze_meals(meals)
            )

            st.session_state.analysis_data = {
                "ingredients": ingredients_top5,
                "side_dishes": side_dishes_top5,
                "meal_count": len(meals),
                "start": analysis_start,
                "end": analysis_end,
            }


# ============================================================
# 분석 결과 표시
# ============================================================

if st.session_state.analysis_data:

    data = st.session_state.analysis_data

    st.divider()

    st.caption(
        f"분석 기간: "
        f"{data['start'].strftime('%Y-%m-%d')} ~ "
        f"{data['end'].strftime('%Y-%m-%d')}"
    )

    st.caption(
        f"분석에 사용한 급식 데이터: "
        f"{data['meal_count']}건"
    )

    # --------------------------------------------------------
    # 식재료 TOP5
    # --------------------------------------------------------

    st.subheader(
        "🥕 가장 자주 등장한 식재료 TOP 5"
    )

    st.caption(
        "※ 나이스 API에는 실제 조리 재료 목록이 없으므로 "
        "메뉴명에서 확인되는 식재료를 기준으로 집계합니다."
    )

    ingredients = data["ingredients"]

    if ingredients:

        for rank, (ingredient, count) in enumerate(
            ingredients,
            start=1,
        ):

            st.markdown(
                f"### {rank}위. {ingredient}"
            )

            st.write(
                f"메뉴명에 **{count}회** 등장"
            )

    else:

        st.info(
            "메뉴명에서 확인할 수 있는 식재료가 없습니다."
        )

    # --------------------------------------------------------
    # 반찬 TOP5
    # --------------------------------------------------------

    st.subheader(
        "🍱 가장 많이 나온 반찬 TOP 5"
    )

    side_dishes = data["side_dishes"]

    if side_dishes:

        for rank, (dish, count) in enumerate(
            side_dishes,
            start=1,
        ):

            st.markdown(
                f"### {rank}위. {dish}"
            )

            st.write(
                f"총 **{count}회** 등장"
            )

    else:

        st.info(
            "분석할 반찬 데이터가 없습니다."
        )


# ============================================================
# 안내
# ============================================================

st.divider()

st.caption(
    "급식 정보 출처: 나이스 교육정보 개방 포털"
)
