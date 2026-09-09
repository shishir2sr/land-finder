import streamlit as st
import requests
import time
import pandas as pd

# অ্যাপের কনফিগারেশন
st.set_page_config(page_title="ভূমি রেকর্ড অনুসন্ধান", page_icon="🗺️", layout="wide")

st.title("🗺️ ভূমি রেকর্ড অনুসন্ধান (Scraper)")
st.write("খতিয়ানের ধরন (নামজারি বা সার্ভে) নির্বাচন করে নির্দিষ্ট ব্যক্তির জায়গা খুঁজুন।")

# সাইডবার - টোকেন ইনপুট
st.sidebar.header("🔑 অথেনটিকেশন টোকেন")
auth_token = st.sidebar.text_input("Authorization", value="Bearer 4FLyu8fLf7BW2xomL5yWFy534TlGRnkb")
user_token = st.sidebar.text_area("User-Token", value="Bearer eyJ0eXAiOiJKV...")

# ডেটা রিলোড বাটন
if st.sidebar.button("ডেটা রিলোড করুন 🔄"):
    st.cache_data.clear()  # ক্যাশ মুছে ফেলবে
    st.rerun()  # পেজ রিলোড করবে


def get_headers(auth, user):
    final_auth = auth if auth.startswith("Bearer ") else f"Bearer {auth}"
    final_user = user if user.startswith("Bearer ") else f"Bearer {user}"
    return {
        'Accept': 'application/json',
        'Authorization': final_auth,
        'User-Token': final_user,
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }


# ক্যাশ ফাংশনে টোকেন আর্গুমেন্ট যোগ করা হলো, যাতে টোকেন বদলালে ক্যাশ ক্লিয়ার হয়
@st.cache_data(ttl=3600)
def fetch_options(url, auth, user):
    try:
        res = requests.get(url, headers=get_headers(auth, user))
        if res.status_code == 200:
            return res.json().get('data', [])
    except Exception as e:
        pass
    return []


# গ্লোবাল ডেটা লোড (টোকেন পাস করা হচ্ছে)
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

# যদি বিভাগ লোড না হয়, তবে ইউজারকে ওয়ার্নিং দেওয়া হবে
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

target_keyword = st.sidebar.text_input("যার নাম খুঁজছেন", value="জিয়াসমিন")


def get_mouzas(dist_code, upz_code, is_mutation=False, survey_id=None):
    url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/mouzas/jl-numbers?DISTRICT_BBS_CODE={dist_code}&UPAZILA_BBS_CODE={upz_code}"
    if not is_mutation and survey_id:
        url += f"&SURVEY_ID={survey_id}"

    try:
        res = requests.get(url, headers=get_headers(auth_token, user_token))
        if res.status_code == 200:
            return res.json().get('data', [])
        else:
            st.error(f"মৌজা লোড এরর! Status: {res.status_code}")
    except Exception as e:
        pass
    return []


def search_khatians(survey_key, mouza_id, mouza_name, target_name):
    matches = []
    page_no = 1

    while True:
        url = f"https://gateway.dlrms.land.gov.bd/core-api/api/public/index-khatian/{survey_key}?SURVEY={survey_key}&JL_NUMBER_ID={mouza_id}&PAGE_NO={page_no}&PAGE_SIZE=100"
        res = requests.get(url, headers=get_headers(auth_token, user_token))

        if res.status_code != 200:
            st.error(f"এপিআই এরর! Status Code: {res.status_code}। টোকেন এক্সপায়ার হতে পারে।")
            break

        data = res.json().get('data', {}).get('items', [])
        if not data:
            break

        for item in data:
            owners = item.get('OWNERS')
            if owners and target_name in owners:
                matches.append({
                    'মৌজার নাম': mouza_name,
                    'খতিয়ান নম্বর': item.get('KHATIAN_NO'),
                    'মালিকের নাম': owners
                })

        if len(data) < 100:
            break

        page_no += 1
        time.sleep(0.3)

    return matches


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

        if total_mouzas > 0:
            st.success(f"মোট {total_mouzas} টি মৌজা পাওয়া গেছে। স্ক্যান শুরু হচ্ছে...")
            progress_bar = st.progress(0)
            status_text = st.empty()

            all_results = []

            for index, mouza in enumerate(mouzas):
                mouza_id = mouza.get('ID')
                mouza_name = mouza.get('MOUZA_NAME')

                status_text.text(f"খোঁজা হচ্ছে: {mouza_name} মৌজায় ({index + 1}/{total_mouzas})")

                results = search_khatians(selected_survey_key, mouza_id, mouza_name, target_keyword)
                if results:
                    all_results.extend(results)

                progress_bar.progress((index + 1) / total_mouzas)

            status_text.text("স্ক্যান সম্পন্ন হয়েছে!")

            st.markdown("### 📊 ফলাফল")
            if all_results:
                df = pd.DataFrame(all_results)
                df.index = df.index + 1
                st.dataframe(df, use_container_width=True)

                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="ফলাফল CSV হিসেবে ডাউনলোড করুন 📥",
                    data=csv,
                    file_name=f'{target_keyword}_{selected_upz_name}_records.csv',
                    mime='text/csv',
                )
            else:
                st.warning("দুঃখিত! এই নামে কোনো রেকর্ড পাওয়া যায়নি।")
        else:
            st.error("কোনো মৌজা পাওয়া যায়নি। টোকেন বা সার্ভে আইডি ঠিক আছে কিনা চেক করুন।")