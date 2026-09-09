import streamlit as st
import requests
import time
import pandas as pd
import unicodedata
from playwright.sync_api import sync_playwright

# অ্যাপের কনফিগারেশন
st.set_page_config(page_title="ভূমি রেকর্ড অনুসন্ধান", page_icon="🗺️", layout="wide")

st.title("🗺️ ভূমি রেকর্ড অনুসন্ধান (Scraper)")
st.write("লগইন করে খতিয়ানের ধরন (নামজারি বা সার্ভে) নির্বাচন করে নির্দিষ্ট ব্যক্তির জায়গা খুঁজুন।")

# --- Session State ---
if 'is_logged_in' not in st.session_state:
    st.session_state.is_logged_in = False
if 'user_token' not in st.session_state:
    st.session_state.user_token = ""
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


# --- আপনার ক্যাপচার করা অরিজিনাল পাবলিক হেডার ---
PUBLIC_API_TOKEN = "Bearer iynoeZ9E7B7Uv3Qa9LZicvPdQhLAnNKO"


def get_public_headers():
    return {
        'Accept': 'application/json',
        'Authorization': PUBLIC_API_TOKEN,
        'Referer': 'https://dlrms.land.gov.bd/',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }


# --- পাব্লিক এপিআই ফেচ করার ফাংশন (Playwright ছাড়াই সুপারফাস্ট রান করবে) ---
@st.cache_data(ttl=3600)
def fetch_public_data(url):
    try:
        res = requests.get(url, headers=get_public_headers(), timeout=10)
        if res.status_code == 200:
            return res.json().get('data', [])
    except Exception:
        pass
    return []


# --- Playwright দিয়ে SSO লগইন ও সেশন টোকেন এক্সট্রাকশন (Stealth & Selector Verified) ---
def login_and_get_token(phone, password):
    phone = phone.strip()
    if phone.startswith("0"):
        phone = phone[1:]

    try:
        with sync_playwright() as p:
            # আসল ব্রাউজারের মতো আচরণ করানোর জন্য বিশেষ আর্গুমেন্ট
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            context.set_default_timeout(60000)
            page = context.new_page()

            # ১. লগইন পেজে যাওয়া
            page.goto("https://lsg-land-owner.land.gov.bd/login", wait_until="networkidle")

            # ২. ইনপুট বক্স স্ক্রিনে আসা পর্যন্ত নিশ্চিতভাবে অপেক্ষা করা
            username_selector = 'input[name="username"]'
            page.wait_for_selector(username_selector, state="visible", timeout=30000)

            # ৩. ফর্ম ইনপুট
            page.fill(username_selector, phone)
            page.fill('input[name="password"]', password)

            # ৪. অটো-ক্যাপচা সলভ
            page.evaluate('''
                          let captchaLabel = document.getElementById("mainCaptcha");
                          let captchaInput = document.getElementById("txtInput");
                          if (captchaLabel && captchaInput) {
                              let code = captchaLabel.innerText || captchaLabel.value;
                              captchaInput.value = code.trim();
                              captchaInput.dispatchEvent(new Event('input', {bubbles: true}));
                              captchaInput.dispatchEvent(new Event('change', {bubbles: true}));
                          }
                          ''')

            # ৫. সাবমিট
            page.click('button[type="submit"]')
            page.wait_for_timeout(4000)

            if "login" in page.url:
                browser.close()
                return False, "লগইন ফেইলড! পাসওয়ার্ড ভুল অথবা ক্যাপচা ভেরিফিকেশন ফেইল।"

            # ৬. SSO রিডাইরেক্ট সম্পূর্ণ করা
            page.goto("https://dlrms.land.gov.bd/citizen/sso-login", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # ৭. মূল ড্যাশবোর্ডে যাওয়া
            page.goto("https://dlrms.land.gov.bd/", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            jwt_token = None

            # ৮. চেক ১: কুকিজ থেকে টোকেন বের করা
            cookies = context.cookies()
            for cookie in cookies:
                if cookie['name'] in ['auth_access_token', 'token', 'dlrms_app_token']:
                    jwt_token = cookie['value']
                    break

            # ৯. চেক ২: LocalStorage & SessionStorage চেক করা
            if not jwt_token:
                jwt_token = page.evaluate('''
                                          () => {
                                              return localStorage.getItem('auth_access_token') ||
                                                  localStorage.getItem('token') ||
                                                  sessionStorage.getItem('auth_access_token') ||
                                                  sessionStorage.getItem('token') ||
                                                  null;
                                          }
                                          ''')

            # ১০. চেক ৩: __NEXT_DATA__ পেজ স্টেট থেকে চেক করা
            if not jwt_token:
                jwt_token = page.evaluate('''
                                          () => {
                                              try {
                                                  return window.__NEXT_DATA__.props.pageProps.tokenStatus.token || null;
                                              } catch (e) {
                                                  return null;
                                              }
                                          }
                                          ''')

            browser.close()

            if jwt_token:
                if not jwt_token.startswith("Bearer "):
                    jwt_token = f"Bearer {jwt_token}"
                return True, jwt_token
            else:
                return False, "লগইন হয়েছে কিন্তু স্টোরেজে কোনো টোকেন পাওয়া যায়নি।"

    except Exception as e:
        return False, f"এরর: {str(e)}"

# --- সাইডবার লগইন ---
st.sidebar.header("🔐 সিস্টেমে লগইন করুন")

if not st.session_state.is_logged_in:
    phone_input = st.sidebar.text_input("মোবাইল নম্বর", placeholder="017........")
    pass_input = st.sidebar.text_input("পাসওয়ার্ড", type="password")

    if st.sidebar.button("লগইন 🚀"):
        if not phone_input or not pass_input:
            st.sidebar.warning("দয়া করে ফোন নম্বর এবং পাসওয়ার্ড দিন!")
        else:
            with st.spinner("লগইন হচ্ছে এবং সেশন ভেরিফাই করা হচ্ছে..."):
                success, result = login_and_get_token(phone_input, pass_input)

                if success:
                    st.session_state.is_logged_in = True
                    st.session_state.user_token = result
                    st.sidebar.success("✅ সফলভাবে লগইন হয়েছে!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(f"{result}")
else:
    st.sidebar.success("✅ আপনি সিস্টেমে লগইন অবস্থায় আছেন!")
    if st.sidebar.button("লগআউট 🚪"):
        st.session_state.is_logged_in = False
        st.session_state.user_token = ""
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

    # ১. বিভাগ লোড
    divisions_data = fetch_public_data("https://gateway.dlrms.land.gov.bd/core-api/api/public/divisions?ROW_STATUS=1")
    districts_data = fetch_public_data("https://gateway.dlrms.land.gov.bd/core-api/api/public/districts?ROW_STATUS=1")
    upazilas_data = fetch_public_data("https://gateway.dlrms.land.gov.bd/core-api/api/public/upazilas?ROW_STATUS=1")
    global_surveys_data = fetch_public_data(
        "https://gateway.dlrms.land.gov.bd/core-api/api/public/surveys?ROW_STATUS=1")

    search_type = st.sidebar.radio(
        "খতিয়ানের ধরন নির্বাচন করুন:",
        ("নামজারি খতিয়ান (Mutation)", "সার্ভে খতিয়ান (Survey)")
    )

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
        available_surveys = fetch_public_data(survey_api_url)

        if available_surveys:
            survey_dict = {s['LOCAL_NAME']: s['SURVEY_ID'] for s in available_surveys}
            selected_survey_name = st.sidebar.selectbox("সার্ভের ধরন (CS/RS/SA)", list(survey_dict.keys()))
            selected_survey_id = survey_dict.get(selected_survey_name)
            selected_survey_key = global_survey_keys.get(selected_survey_name, "")
        else:
            st.sidebar.warning("এই উপজেলায় কোনো সার্ভে পাওয়া যায়নি!")

    target_keyword = st.sidebar.text_input("যার নাম খুঁজছেন", value="")


    # অথেনটিকেটেড হেডারে রিকোয়েস্ট
    def get_auth_headers():
        return {
            'Accept': 'application/json',
            'Authorization': PUBLIC_API_TOKEN,
            'User-Token': st.session_state.user_token,
            'Referer': 'https://dlrms.land.gov.bd/',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }


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
                time.sleep(0.5)
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

            mouzas = fetch_public_data(mouza_url)
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