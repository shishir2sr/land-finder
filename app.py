import streamlit as st
import requests
import time
import pandas as pd
import unicodedata
import re

# অ্যাপের কনফিগারেশন
st.set_page_config(page_title="ভূমি রেকর্ড অনুসন্ধান", page_icon="🗺️", layout="wide")

st.title("🗺️ ভূমি রেকর্ড অনুসন্ধান (Scraper)")
st.write("খতিয়ানের ধরন (নামজারি বা সার্ভে) নির্বাচন করে নির্দিষ্ট ব্যক্তির জায়গা খুঁজুন এবং বিস্তারিত দেখুন।")

# Session State ইনিশিয়ালাইজেশন (যাতে ইন্টার‍্যাক্ট করলে ডেটা হারিয়ে না যায়)
if 'search_results' not in st.session_state:
    st.session_state.search_results = []
if 'survey_key_used' not in st.session_state:
    st.session_state.survey_key_used = ""
if 'target_keyword_used' not in st.session_state:
    st.session_state.target_keyword_used = ""


# বাংলা টেক্সট ক্লিন করার ফাংশন
def clean_text(text):
    if not text:
        return ""
    text = text.replace('\u200c', '').replace('\u200d', '')
    text = unicodedata.normalize('NFC', text)
    return text.strip()


# সাইডবার - টোকেন ইনপুট
st.sidebar.header("🔑 অথেনটিকেশন টোকেন")
auth_token = st.sidebar.text_input("Authorization", value="Bearer 4FLyu8fLf7BW2xomL5yWFy534TlGRnkb")
user_token = st.sidebar.text_area("User-Token", value="Bearer eyJ0eXAiOiJKV...")

# ডেটা রিলোড বাটন
if st.sidebar.button("ডেটা রিলোড করুন 🔄"):
    st.cache_data.clear()
    st.rerun()


def get_headers(auth, user):
    final_auth = auth if auth.startswith("Bearer ") else f"Bearer {auth}"
    final_user = user if user.startswith("Bearer ") else f"Bearer {user}"
    return {
        'Accept': 'application/json',
        'Authorization': final_auth,
        'User-Token': final_user,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }


@st.cache_data(ttl=3600)
def fetch_options(url, auth, user):
    try:
        res = requests.get(url, headers=get_headers(auth, user))
        if res.status_code == 200:
            return res.json().get('data', [])
    except Exception as e:
        pass
    return []


# গ্লোবাল ডেটা লোড
divisions_data = fetch_options("https://gateway.dlrms.land.gov.bd/core-api/api/public/divisions?ROW_STATUS=1",
                               auth_token, user_token)
districts_data = fetch_options("https://gateway.dlrms.land.gov.bd/core-api/api/public/districts?ROW_STATUS=1",
                               auth_token, user_token)
upazilas_data = fetch_options("https://gateway.dlrms.land.gov.bd/core-api/api/public/upazilas?ROW_STATUS=1", auth_token,
                              user_token)
global_surveys_data = fetch_options("https://gateway.dlrms.land.gov.bd/core-api/api/public/surveys?ROW_STATUS=1",
                                    auth_token, user_token)

global_survey_keys = {s['NAME']: s['KEY'] for s in global_surveys_data}

st.sidebar.markdown("---")
st.sidebar.header("📍 অনুসন্ধানের ফিল্টার")

if not divisions_data:
    st.warning("⚠️ ডেটা লোড হয়নি! দয়া করে সঠিক টোকেন দিয়ে বামপাশের 'ডেটা রিলোড করুন 🔄' বাটনে ক্লিক করুন।")

search_type = st.sidebar.radio(
    "খতিয়ানের ধরন নির্বাচন করুন:",
    ("নামজারি খতিয়ান (Mutation)", "সার্ভে খতিয়ান (Survey)")
)

# ২. বিভাগ, জেলা, উপজেলা নির্বাচন
div_dict = {d['NAME']: d['BBS_CODE'] for d in divisions_data}
selected_div_name = st.sidebar.selectbox("বিভাগ নির্বাচন করুন", list(div_dict.keys()) if div_dict else ["নাই"])
selected_div_code = div_dict.get(selected_div_name, "") if selected_div_name != "নাই" else ""

filtered_districts = [d for d in districts_data if d.get('DIVISION_BBS_CODE') == selected_div_code]
dist_dict = {d['NAME']: d['BBS_CODE'] for d in filtered_districts}
selected_dist_name = st.sidebar.selectbox("জেলা নির্বাচন করুন", list(dist_dict.keys()) if dist_dict else ["নাই"])
selected_dist_code = dist_dict.get(selected_dist_name, "") if selected_dist_name != "নাই" else ""

filtered_upazilas = [u for u in upazilas_data if u.get('DISTRICT_BBS_CODE') == selected_dist_code]
upz_dict = {u['NAME']: u['BBS_CODE'] for u in filtered_upazilas}
selected_upz_name = st.sidebar.selectbox("উপজেলা নির্বাচন করুন", list(upz_dict.keys()) if upz_dict else ["নাই"])
selected_upz_code = upz_dict.get(selected_upz_name, "") if selected_upz_name != "নাই" else ""

# ৩. ডায়নামিক সার্ভে নির্বাচন
selected_survey_id = None
selected_survey_key = "MUTATION"

if search_type == "সার্ভে খতিয়ান (Survey)" and selected_dist_code and selected_upz_code:
    survey_api_url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/upazilas/surveys?DISTRICT_BBS_CODE={selected_dist_code}&UPAZILA_BBS_CODE={selected_upz_code}"
    available_surveys = fetch_options(survey_api_url, auth_token, user_token)

    if available_surveys:
        survey_dict = {s['LOCAL_NAME']: s['SURVEY_ID'] for s in available_surveys}
        selected_survey_name = st.sidebar.selectbox("সার্ভের ধরন (CS/RS/SA)", list(survey_dict.keys()))
        selected_survey_id = survey_dict.get(selected_survey_name)
        selected_survey_key = global_survey_keys.get(selected_survey_name, "")
    else:
        st.sidebar.warning("এই উপজেলায় কোনো সার্ভে পাওয়া যায়নি!")

target_keyword = st.sidebar.text_input("যার নাম খুঁজছেন", value="")


def get_mouzas(dist_code, upz_code, is_mutation=False, survey_id=None):
    url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/mouzas/jl-numbers?DISTRICT_BBS_CODE={dist_code}&UPAZILA_BBS_CODE={upz_code}"
    if not is_mutation and survey_id:
        url += f"&SURVEY_ID={survey_id}"

    try:
        res = requests.get(url, headers=get_headers(auth_token, user_token))
        if res.status_code == 200:
            return res.json().get('data', [])
    except Exception as e:
        pass
    return []


def search_khatians(survey_key, mouza_id, mouza_name, target_name):
    matches = []
    page_no = 1
    cleaned_target = clean_text(target_name)

    while True:
        url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/index-khatian/{survey_key}?SURVEY={survey_key}&JL_NUMBER_ID={mouza_id}&PAGE_NO={page_no}&PAGE_SIZE=100"

        success = False
        res = None
        for attempt in range(3):
            try:
                res = requests.get(url, headers=get_headers(auth_token, user_token), timeout=10)
                success = True
                break
            except requests.exceptions.RequestException:
                time.sleep(2)

        if not success:
            break

        if res.status_code != 200:
            break

        data = res.json().get('data', {}).get('items', [])
        if not data:
            break

        for item in data:
            owners = item.get('OWNERS')
            if owners:
                cleaned_owners = clean_text(owners)
                if cleaned_target in cleaned_owners:
                    matches.append({
                        'ID': item.get('ID'),  # বিস্তারিত দেখার জন্য API-তে এই ID লাগবে
                        'মৌজার নাম': mouza_name,
                        'খতিয়ান নম্বর': item.get('KHATIAN_NO'),
                        'মালিকের নাম': owners
                    })

        if len(data) < 100:
            break

        page_no += 1
        time.sleep(1)

    return matches


# নতুন ফাংশন: খতিয়ানের বিস্তারিত তথ্য আনা
def get_khatian_details(survey_key, khatian_id):
    url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/index-khatian/{survey_key}/{khatian_id}"
    try:
        res = requests.get(url, headers=get_headers(auth_token, user_token), timeout=10)
        if res.status_code == 200:
            return res.json().get('data', {})
    except Exception as e:
        pass
    return None


# সার্চ বাটন লজিক (রেজাল্টগুলো Session State-এ সেভ করা হচ্ছে)
if st.sidebar.button("সার্চ করুন 🔍"):
    if not selected_dist_code or not selected_upz_code:
        st.error("দয়া করে জেলা এবং উপজেলা সঠিকভাবে নির্বাচন করুন!")
    elif search_type == "সার্ভে খতিয়ান (Survey)" and not selected_survey_id:
        st.error("দয়া করে সার্ভের ধরন নির্বাচন করুন!")
    elif not target_keyword:
        st.warning("দয়া করে একটি নাম লিখুন!")
    else:
        st.info(f"**{selected_upz_name}** উপজেলায় '{target_keyword}'-এর তথ্য খোঁজা হচ্ছে...")

        is_mutation = (search_type == "নামজারি খতিয়ান (Mutation)")
        mouzas = get_mouzas(selected_dist_code, selected_upz_code, is_mutation, selected_survey_id)

        total_mouzas = len(mouzas)
        all_results = []

        if total_mouzas > 0:
            progress_bar = st.progress(0)
            status_text = st.empty()

            for index, mouza in enumerate(mouzas):
                mouza_id = mouza.get('ID')
                mouza_name = mouza.get('MOUZA_NAME')
                status_text.text(f"খোঁজা হচ্ছে: {mouza_name} মৌজায় ({index + 1}/{total_mouzas})")

                results = search_khatians(selected_survey_key, mouza_id, mouza_name, target_keyword)
                if results:
                    all_results.extend(results)

                progress_bar.progress((index + 1) / total_mouzas)

            status_text.text("স্ক্যান সম্পন্ন হয়েছে!")

            # ডেটা সেশন স্টেটে সংরক্ষণ
            st.session_state.search_results = all_results
            st.session_state.survey_key_used = selected_survey_key
            st.session_state.target_keyword_used = target_keyword
        else:
            st.error("কোনো মৌজা পাওয়া যায়নি। টোকেন বা সার্ভে আইডি চেক করুন।")
            st.session_state.search_results = []

# --- ফলাফল এবং বিস্তারিত দেখার অংশ (Main Body) ---
if st.session_state.search_results:
    st.markdown(f"### 📊 '{st.session_state.target_keyword_used}' এর জন্য ফলাফল")

    # ডেটাফ্রেম তৈরি (ID কলাম লুকিয়ে রাখা হলো সুন্দর দেখানোর জন্য)
    df = pd.DataFrame(st.session_state.search_results)
    display_df = df.drop(columns=['ID'])
    display_df.index = display_df.index + 1
    st.dataframe(display_df, use_container_width=True)

    st.markdown("---")

    # বিস্তারিত দেখার UI (Dropdown)
    st.markdown("### 📄 খতিয়ানের বিস্তারিত তথ্য দেখুন")
    st.write("দাগ নম্বর এবং জমির পরিমাণ দেখতে নিচের তালিকা থেকে একটি খতিয়ান নির্বাচন করুন:")

    # ড্রপডাউনের জন্য অপশন তৈরি করা (Key-Value pair)
    options_dict = {f"মৌজা: {r['মৌজার নাম']} | খতিয়ান: {r['খতিয়ান নম্বর']} | মালিক: {r['মালিকের নাম'][:30]}...": r['ID']
                    for r in st.session_state.search_results}

    selected_option = st.selectbox("খতিয়ান নির্বাচন করুন:", list(options_dict.keys()))

    if st.button("বিস্তারিত দেখুন 👁️"):
        khatian_id = options_dict[selected_option]
        survey_key = st.session_state.survey_key_used

        with st.spinner("বিস্তারিত তথ্য আনা হচ্ছে..."):
            details = get_khatian_details(survey_key, khatian_id)

        if details:
            # তথ্যগুলো সুন্দরভাবে কার্ড/কলাম আকারে দেখানো
            st.success("তথ্য সফলভাবে পাওয়া গেছে!")
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**মৌজা:** {details.get('MOUZA_NAME', 'তথ্য নেই')}")
                st.markdown(f"**খতিয়ান নং:** {details.get('KHATIAN_NO', 'তথ্য নেই')}")
                st.markdown(f"**দাগ নং (Dags):** {details.get('DAGS', 'তথ্য নেই')}")

            with col2:
                st.markdown(f"**মোট জমি:** {details.get('TOTAL_LAND', 'তথ্য নেই')}")
                st.markdown(f"**উপজেলা ও জেলা:** {details.get('UPAZILA_NAME', '')}, {details.get('DISTRICT_NAME', '')}")

            st.markdown(f"**মালিকানা:** {details.get('OWNERS', 'তথ্য নেই')}")
        else:
            st.error("বিস্তারিত তথ্য পাওয়া যায়নি। সার্ভারে সমস্যা হতে পারে।")

elif len(st.session_state.search_results) == 0 and st.session_state.target_keyword_used != "":
    st.warning("দুঃখিত! এই নামে কোনো রেকর্ড পাওয়া যায়নি।")