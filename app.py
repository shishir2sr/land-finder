import streamlit as st
import requests
import time
import pandas as pd
import unicodedata
import re
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

# অ্যাপের কনফিগারেশন
st.set_page_config(page_title="ভূমি রেকর্ড অনুসন্ধান", page_icon="🗺️", layout="wide")

st.title("🗺️ ভূমি রেকর্ড অনুসন্ধান (API Version)")
st.write("সম্পূর্ণ ব্রাউজার-মুক্ত, সুপারফাস্ট API স্ক্র্যাপার!")

# --- Session State ---
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False
if 'user_token' not in st.session_state:
    st.session_state.user_token = ""
if 'public_token' not in st.session_state:
    st.session_state.public_token = ""
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


# --- PURE API লগইন এবং Token Exchange (Final Bulletproof Version) ---
def login_and_get_tokens(phone, password):
    # মোবাইল নাম্বারের প্রথম ০ কেটে দেওয়া (যেহেতু পেলোডে username=1670911553 ছিল)
    phone = phone.strip()
    if phone.startswith("0"):
        phone = phone[1:]

    session = requests.Session()

    # ব্রাউজারের অরিজিনাল হেডার
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Origin": "https://lsg-land-owner.land.gov.bd",
        "Referer": "https://lsg-land-owner.land.gov.bd/login",
    })

    try:
        # ১. ডাইনামিক Public Token বের করা (হোমপেজ থেকে)
        public_token = "Bearer nuOYIjN0wzFmchpKokAMNzR8ppsA2Iw7"
        try:
            front_res = session.get("https://dlrms.land.gov.bd/", timeout=10)
            match = re.search(r'Bearer\s+[A-Za-z0-9]{30,50}', front_res.text)
            if match:
                public_token = match.group(0)
        except Exception:
            pass

        # ২. লগইন পেজ থেকে CSRF টোকেন আনা
        login_url = "https://lsg-land-owner.land.gov.bd/login"
        res = session.get(login_url, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        csrf_elem = soup.find("input", {"name": "_token"})
        if not csrf_elem:
            return False, "সার্ভার থেকে CSRF টোকেন পাওয়া যায়নি।", None
        csrf_token = csrf_elem["value"]

        # ৩. হুবহু আসল ব্রাউজারের মতো পেলোড সাজানো (আপনার দেওয়া ডেটা অনুযায়ী)
        payload = {
            '_token': csrf_token,
            'userOptionType': 'Citizen',
            'identity': 'mobile',
            'country_code': '880',
            'username': phone,
            'password': password,
            'qr-container-token': ''
        }

        # ৪. লগইন রিকোয়েস্ট পাঠানো
        # allow_redirects=False রাখছি যাতে আমরা 302 Found স্ট্যাটাস ধরতে পারি
        post_res = session.post(login_url, data=payload, allow_redirects=False, timeout=15)

        # লগইন এরর চেক: সফল হলে এটি 302 রিডাইরেক্ট করে /landing এ পাঠাবে
        if post_res.status_code != 302:
            # যদি 302 না হয়, তার মানে পেজেই এরর দেখিয়েছে
            error_soup = BeautifulSoup(post_res.text, "html.parser")
            error_elem = error_soup.find("div", class_="alert-danger") or error_soup.find("span", class_="text-danger")
            exact_error = error_elem.text.strip() if error_elem else "তথ্য ভুল অথবা সার্ভার এরর।"
            return False, f"লগইন ফেইলড! কারণ: {exact_error}", None

        # ৫. SSO Code জেনারেট করা
        sso_url = "https://lsg-land-owner.land.gov.bd/oauth/authorize"
        sso_params = {
            "client_id": "LSG-xfe-MYXd6OCc4smJAk-20241120-LIVE",
            "redirect_uri": "https://dlrms.land.gov.bd/citizen-callback",
            "response_type": "code",
            "scope": "view-user",
            "state": "12345"
        }

        auth_res = session.get(sso_url, params=sso_params, allow_redirects=False, timeout=15)
        location = auth_res.headers.get('Location', '')

        parsed_url = urlparse(location)
        code = parse_qs(parsed_url.query).get('code', [None])

        if not code or not code[0]:
            return False, "SSO কোড জেনারেট হয়নি।", None

        auth_code = code[0]

        # ৬. DLRMS ডাইরেক্ট Token Exchange
        dlrms_exchange_url = "https://dlrms.land.gov.bd/api/sso-authorize-code-grant"

        exchange_payload = {
            "code": auth_code,
            "isCitizen": True,
            "redirect_uri": "https://dlrms.land.gov.bd/citizen-callback"
        }

        exchange_headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://dlrms.land.gov.bd",
            "Referer": f"https://dlrms.land.gov.bd/citizen-callback?code={auth_code}"
        }

        token_res = session.post(dlrms_exchange_url, json=exchange_payload, headers=exchange_headers, timeout=15)

        if token_res.status_code != 200:
            return False, f"টোকেন এক্সচেঞ্জ ফেইল করেছে (Status: {token_res.status_code})", None

        token_data = token_res.json()
        access_token = token_data.get('access_token')

        if access_token:
            return True, f"Bearer {access_token}", public_token
        else:
            return False, "সার্ভার টোকেন দেয়নি।", None

    except Exception as e:
        return False, f"API এরর: {str(e)}", None

# --- ডাইনামিক হেডার ফাংশন ---
def get_public_headers():
    return {
        'Accept': 'application/json',
        'Authorization': st.session_state.public_token,
        'Referer': 'https://dlrms.land.gov.bd/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }


def get_auth_headers():
    return {
        'Accept': 'application/json',
        'Authorization': st.session_state.public_token,
        'User-Token': st.session_state.user_token,
        'Referer': 'https://dlrms.land.gov.bd/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }


# --- সাইডবার লগইন ---
st.sidebar.header("🔐 সিস্টেমে লগইন করুন")

if not st.session_state.is_logged_in:
    phone_input = st.sidebar.text_input("মোবাইল নম্বর", placeholder="017........")
    pass_input = st.sidebar.text_input("পাসওয়ার্ড", type="password")

    if st.sidebar.button("লগইন 🚀"):
        if not phone_input or not pass_input:
            st.sidebar.warning("দয়া করে ফোন নম্বর এবং পাসওয়ার্ড দিন!")
        else:
            with st.spinner("ব্রাউজার ছাড়া সরাসরি API দিয়ে লগইন হচ্ছে... (১-২ সেকেন্ড)"):
                success, user_token, public_token = login_and_get_tokens(phone_input, pass_input)

                if success:
                    st.session_state.is_logged_in = True
                    st.session_state.user_token = user_token
                    st.session_state.public_token = public_token
                    st.sidebar.success("✅ লগইন সফল! রকেটের গতিতে টোকেন জেনারেট হয়েছে!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(f"❌ {user_token}")
else:
    st.sidebar.success("✅ আপনি সিস্টেমে লগইন অবস্থায় আছেন!")
    if st.sidebar.button("লগআউট 🚪"):
        st.session_state.is_logged_in = False
        st.session_state.user_token = ""
        st.session_state.public_token = ""
        st.session_state.search_results = []
        st.cache_data.clear()
        st.rerun()

st.sidebar.markdown("---")

# --- মূল ড্যাশবোর্ড ও ফিল্টার ---
if st.session_state.is_logged_in:

    st.sidebar.header("📍 অনুসন্ধানের ফিল্টার")

    if st.sidebar.button("ডেটা রিলোড করুন 🔄"):
        st.cache_data.clear()
        st.rerun()


    @st.cache_data(ttl=3600)
    def fetch_public_data(url, current_public_token):
        try:
            res = requests.get(url, headers=get_public_headers(), timeout=10)
            if res.status_code == 200:
                return res.json().get('data', [])
        except Exception:
            pass
        return []


    # ড্রপডাউন ডেটা লোড
    divisions_data = fetch_public_data("https://gateway.dlrms.land.gov.bd/core-api/api/public/divisions?ROW_STATUS=1",
                                       st.session_state.public_token)
    districts_data = fetch_public_data("https://gateway.dlrms.land.gov.bd/core-api/api/public/districts?ROW_STATUS=1",
                                       st.session_state.public_token)
    upazilas_data = fetch_public_data("https://gateway.dlrms.land.gov.bd/core-api/api/public/upazilas?ROW_STATUS=1",
                                      st.session_state.public_token)
    global_surveys_data = fetch_public_data(
        "https://gateway.dlrms.land.gov.bd/core-api/api/public/surveys?ROW_STATUS=1", st.session_state.public_token)

    search_type = st.sidebar.radio("খতিয়ানের ধরন নির্বাচন করুন:",
                                   ("নামজারি খতিয়ান (Mutation)", "সার্ভে খতিয়ান (Survey)"))

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

    global_survey_keys = {s['NAME']: s['KEY'] for s in global_surveys_data}
    selected_survey_id = None
    selected_survey_key = "MUTATION"

    if search_type == "সার্ভে খতিয়ান (Survey)" and selected_dist_code and selected_upz_code:
        survey_api_url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/upazilas/surveys?DISTRICT_BBS_CODE={selected_dist_code}&UPAZILA_BBS_CODE={selected_upz_code}"
        available_surveys = fetch_public_data(survey_api_url, st.session_state.public_token)

        if available_surveys:
            survey_dict = {s['LOCAL_NAME']: s['SURVEY_ID'] for s in available_surveys}
            selected_survey_name = st.sidebar.selectbox("সার্ভের ধরন (CS/RS/SA)", list(survey_dict.keys()))
            selected_survey_id = survey_dict.get(selected_survey_name)
            selected_survey_key = global_survey_keys.get(selected_survey_name, "")
        else:
            st.sidebar.warning("এই উপজেলায় কোনো সার্ভে পাওয়া যায়নি!")

    target_keyword = st.sidebar.text_input("যার নাম খুঁজছেন", value="")


    def search_khatians(survey_key, mouza_id, mouza_name, target_name):
        matches = []
        page_no = 1
        cleaned_target = clean_text(target_name)

        while True:
            url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/index-khatian/{survey_key}?SURVEY={survey_key}&JL_NUMBER_ID={mouza_id}&PAGE_NO={page_no}&PAGE_SIZE=100"
            try:
                res = requests.get(url, headers=get_auth_headers(), timeout=10)
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
                                'ID': item.get('ID'),
                                'মৌজার নাম': mouza_name,
                                'খতিয়ান নম্বর': item.get('KHATIAN_NO'),
                                'মালিকের নাম': owners
                            })

                if len(data) < 100:
                    break

                page_no += 1
                time.sleep(0.3)
            except Exception:
                break

        return matches


    def get_khatian_details(survey_key, khatian_id):
        url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/index-khatian/{survey_key}/{khatian_id}"
        try:
            res = requests.get(url, headers=get_auth_headers(), timeout=10)
            if res.status_code == 200:
                return res.json().get('data', {})
        except Exception:
            pass
        return None


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
            mouza_url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/mouzas/jl-numbers?DISTRICT_BBS_CODE={selected_dist_code}&UPAZILA_BBS_CODE={selected_upz_code}"
            if not is_mutation and selected_survey_id:
                mouza_url += f"&SURVEY_ID={selected_survey_id}"

            mouzas = fetch_public_data(mouza_url, st.session_state.public_token)
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
                st.session_state.search_results = all_results
                st.session_state.survey_key_used = selected_survey_key
                st.session_state.target_keyword_used = target_keyword
            else:
                st.error("কোনো মৌজা পাওয়া যায়নি।")
                st.session_state.search_results = []

    # --- ফলাফল ও বিস্তারিত ---
    if st.session_state.search_results:
        st.markdown(f"### 📊 '{st.session_state.target_keyword_used}' এর জন্য ফলাফল")

        df = pd.DataFrame(st.session_state.search_results)
        display_df = df.drop(columns=['ID'])
        display_df.index = display_df.index + 1
        st.dataframe(display_df, use_container_width=True)

        st.markdown("---")
        st.markdown("### 📄 খতিয়ানের বিস্তারিত তথ্য দেখুন")
        options_dict = {
            f"মৌজা: {r['মৌজার নাম']} | খতিয়ান: {r['খতিয়ান নম্বর']} | মালিক: {r['মালিকের নাম'][:30]}...": r['ID'] for r
            in st.session_state.search_results}

        selected_option = st.selectbox("খতিয়ান নির্বাচন করুন:", list(options_dict.keys()))

        if st.button("বিস্তারিত দেখুন 👁️"):
            khatian_id = options_dict[selected_option]
            survey_key = st.session_state.survey_key_used

            with st.spinner("বিস্তারিত তথ্য আনা হচ্ছে..."):
                details = get_khatian_details(survey_key, khatian_id)

            if details:
                st.success("তথ্য সফলভাবে পাওয়া গেছে!")
                col1, col2 = st.columns(2)

                with col1:
                    st.markdown(f"**মৌজা:** {details.get('MOUZA_NAME', 'তথ্য নেই')}")
                    st.markdown(f"**খতিয়ান নং:** {details.get('KHATIAN_NO', 'তথ্য নেই')}")
                    st.markdown(f"**দাগ নং (Dags):** {details.get('DAGS', 'তথ্য নেই')}")

                with col2:
                    st.markdown(f"**মোট জমি:** {details.get('TOTAL_LAND', 'তথ্য নেই')}")
                    st.markdown(
                        f"**উপজেলা ও জেলা:** {details.get('UPAZILA_NAME', '')}, {details.get('DISTRICT_NAME', '')}")

                st.markdown(f"**মালিকানা:** {details.get('OWNERS', 'তথ্য নেই')}")
            else:
                st.error("বিস্তারিত তথ্য পাওয়া যায়নি।")
else:
    st.info("👈 দয়া করে বামপাশের মেনু থেকে লগইন করুন।")