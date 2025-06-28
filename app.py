from __future__ import annotations
from streamlit_autorefresh import st_autorefresh
import random, time, datetime, secrets, threading, queue, re, itertools, sys, math
from typing import List, Dict
import streamlit as st, streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path

st.set_page_config(page_title="Визуализация многоканальных изображений", page_icon="🎯", layout="centered", initial_sidebar_state="collapsed")

MOBILE_QS_FLAG = "mobile"; BASE_URL = "https://storage.yandexcloud.net/test3123234442"; TIME_LIMIT = 15; TARGET_SHOWS = 21
GROUPS = ["img1_dif_corners","img2_dif_corners","img3_same_corners_no_symb","img4_same_corners","img5_same_corners"]
ALGS_LET = ["pca_rgb_result","socolov_lab_result","socolov_rgb_result","umap_rgb_result"]
ALGS_COR = ["socolov_lab_result","socolov_rgb_result"]
CORNER = {"img1_dif_corners":"нет","img2_dif_corners":"нет","img3_same_corners_no_symb":"да","img4_same_corners":"да","img5_same_corners":"да"}
LETTER = {"img1_dif_corners":"ж","img2_dif_corners":"фя","img3_same_corners_no_symb":"Не вижу","img4_same_corners":"аб","img5_same_corners":"юэы"}
WITH_CHARS = ["img1_dif_corners","img2_dif_corners","img4_same_corners","img5_same_corners"]; NO_CHAR = "img3_same_corners_no_symb"

if "initialized" not in st.session_state:
    st.session_state.update(initialized=True, questions=[], idx=0, name="", phase="intro", phase_start_time=None, pause_until=0, _timer_flags={}, session_id=secrets.token_hex(8))

components.html(f"""<script>(function(){{const f='{MOBILE_QS_FLAG}',m=innerWidth<1024;if(m)document.documentElement.classList.add('mobile-client');const qs=new URLSearchParams(location.search);if(m&&!qs.has(f)){{qs.set(f,'1');location.search=qs.toString();}}}})();</script>""", height=0)

if st.experimental_get_query_params().get(MOBILE_QS_FLAG) == ["1"]:
    st.markdown("""<style>body{background:#808080;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}h2{font-size:1.3rem;font-weight:500;line-height:1.4;}</style><h2>Уважаемый участник<br>Данное исследование доступно только с <strong>ПК или ноутбука</strong>.</h2>""", unsafe_allow_html=True); st.stop()

st.markdown("""<style>html,body,.stApp,[data-testid="stAppViewContainer"],.main,.block-container{background:#808080!important;color:#111!important;}h1,h2,h3,h4,h5,h6,p,label,li,span{color:#111!important;}header[data-testid="stHeader"]{display:none;}.stButton>button{min-height:52px!important;padding:0 20px!important;border:1px solid #555!important;background:#222!important;color:#fff!important;border-radius:8px!important;}.stButton>button:hover{background:#333!important;color:#fff!important;}.stButton>button:focus{background:#333!important;color:#fff!important;box-shadow:none!important;}.stButton>button:disabled{background:#444!important;color:#888!important;cursor:not-allowed!important;opacity:0.6!important;}.stButton>button>div,.stButton>button>div>p{color:inherit!important;}input[data-testid="stTextInput"]{height:52px;padding:0 16px;font-size:1.05rem;}</style>""", unsafe_allow_html=True)

@st.cache_resource
def open_book():
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gsp"]), scopes)
    return gspread.authorize(creds).open("human_study_results")

@st.cache_resource
def get_worksheets():
    book = open_book()
    try: log_ws = book.worksheet("stage2_log")
    except:
        log_ws = book.add_worksheet("stage2_log", rows=1000, cols=20)
        log_ws.append_row(["timestamp","user","qnum","group","alg","qtype","prompt","answer","correct","time_ms","is_correct","session_id"])
    try: stat_ws = book.worksheet("stage2_stats")
    except:
        stat_ws = book.add_worksheet("stage2_stats", rows=100, cols=3)
        stat_ws.append_row(["image_id","alg","shows"])
    return log_ws, stat_ws
LOG_WS, STAT_WS = get_worksheets()

@st.cache_data(ttl=10)
def read_counters():
    records = STAT_WS.get_all_records()
    return {(r["image_id"], r["alg"]): int(r.get("shows", 0)) for r in records}

def bump_counter(img, alg):
    rows = STAT_WS.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if len(row) >= 3 and row[0] == img and row[1] == alg:
            STAT_WS.update_cell(i, 3, int(row[2] or 0) + 1); return
    STAT_WS.append_row([img, alg, 1], value_input_option="RAW")

Q = globals().setdefault("_Q", queue.Queue(maxsize=1000))
if not globals().get("_W"):
    def w():
        buf = []
        while True:
            try:
                buf.append(Q.get(timeout=1))
                if len(buf) >= 5: LOG_WS.append_rows(buf, value_input_option="RAW"); buf.clear()
            except queue.Empty:
                if buf: LOG_WS.append_rows(buf, value_input_option="RAW"); buf.clear()
    threading.Thread(target=w, daemon=True).start(); globals()["_W"] = True

if "letters_plan" not in st.session_state:
    order = random.sample(ALGS_LET, len(ALGS_LET))
    st.session_state.letters_plan = {g: order[i] for i, g in enumerate(WITH_CHARS)}
    st.session_state.letters_plan[NO_CHAR] = random.choice(ALGS_LET)

def url(g, a): return f"{BASE_URL}/{g}_{a}.png"
def clean(s): return set(re.sub("[ ,.;:-]+", "", (s or "").lower()))

def make_qs() -> List[Dict]:
    cnt = read_counters(); qs = []
    for g in GROUPS:
        alg = st.session_state.letters_plan[g]
        if cnt.get((g, alg), 0) < TARGET_SHOWS:
            qs.append({"group": g, "alg": alg, "img": url(g, alg), "qtype": "letters", "prompt": "Если на изображении вы видите буквы, то укажите, какие именно.", "correct": LETTER[g]})
    for g, alg in itertools.product(GROUPS, ALGS_COR):
        if cnt.get((g, alg), 0) < TARGET_SHOWS:
            qs.append({"group": g, "alg": alg, "img": url(g, alg), "qtype": "corners", "prompt": "Считаете ли вы, что правый верхний угол и нижний левый угол одного цвета с точностью до оттенка?", "correct": CORNER[g]})
    random.shuffle(qs)
    for i, q in enumerate(qs, 1): q["№"] = i
    return qs
if not st.session_state.questions: st.session_state.questions = make_qs()

def render_timer(sec: int, tid: str):
    if tid in st.session_state._timer_flags: return
    components.html(f"""<div style="font-size:1.2rem;font-weight:bold;color:#111;margin-bottom:10px;margin-left:-8px;">Осталось&nbsp;времени: <span id="t{tid}">{sec}</span>&nbsp;сек</div><script>(function(){{let t={sec};const s=document.getElementById('t{tid}');const i=setInterval(()=>{{if(--t<0){{clearInterval(i);return;}}if(s)s.textContent=t;}},1000);}})();</script>""", height=50)
    st.session_state._timer_flags[tid] = True

if not st.session_state.name:
    st.markdown("""<div style="color:#111;"><h2>Уважаемый участник,<br>добро пожаловать в эксперимент по изучению восприятия изображений.</h2><p><b>Как проходит эксперимент</b><br>В ходе эксперимента вам нужно будет отвечать на простые вопросы об изображениях, которые вы увидите на экране. Всего вам предстоит ответить на <b>15</b> вопросов. Прохождение теста займет около 10-15 минут.</p><p><b>Пожалуйста, проходите тест спокойно: исследование не направлено на оценку испытуемых. Оценивается работа алгоритмов, которые выдают картинки разного качества.</b></p><p><b>Что это за изображения?</b><br>Изображения — результат работы разных методов. Ни одно из них не является «эталоном». Цель эксперимента — понять, какие методы обработки лучше сохраняют информацию.</p><p><b>Важно</b><br>Эксперимент полностью анонимен. Проходить его следует <b>только на компьютере или ноутбуке</b>.</p><p>Для начала теста введите любой псевдоним и нажмите Enter или нажмите «Сгенерировать псевдоним».</p></div>""", unsafe_allow_html=True)
    n = st.text_input("", placeholder="Ваш псевдоним", key="username", label_visibility="collapsed")
    if st.button("🎲 Сгенерировать псевдоним"):
        st.session_state.name = f"Участник_{secrets.randbelow(900000)+100000}"; st.experimental_rerun()
    if n: st.session_state.name = n.strip(); st.experimental_rerun()
    st.stop()

if st.session_state.idx >= len(st.session_state.questions):
    st.markdown("<div style='margin-top:50px;padding:40px;text-align:center;font-size:2rem;color:#fff;background:#262626;border-radius:12px;'>Вы завершили прохождение.<br><b>Спасибо за участие!</b></div>", unsafe_allow_html=True); st.balloons(); st.stop()

q = st.session_state.questions[st.session_state.idx]

if st.session_state.phase == "intro":
    txt_c = """Сейчас вы увидите изображение. Цель данного вопроса — посмотреть на диаметрально противоположные углы,<b>правый верхний и левый нижний</b>, и определить, окрашены ли они в одинаково с точностью до оттенка.<br><br>Картинка будет доступна в течение <b>15&nbsp;секунд</b>. Время на ответ не ограничено."""
    txt_l = """Сейчас вы увидите изображение. Цель данного вопроса — определить, есть ли на представленной картинке<b>буквы русского алфавита</b>.<br><br>Найденные буквы необходимо ввести в текстовое поле: допускается разделение пробелами, запятыми и т.&nbsp;д., а также слитное написание.<br><br>Если букв нет — нажмите кнопку <b>«Не вижу букв»</b>."""
    st.markdown(f"<div style='font-size:1.1rem;line-height:1.6;margin-bottom:30px;'>{txt_c if q['qtype']=='corners' else txt_l}</div>", unsafe_allow_html=True)
    if st.button("Перейти к вопросу", key=f"go{st.session_state.idx}"):
        st.session_state.update(phase="question", phase_start_time=time.time()); st.experimental_rerun()
    st.stop()

if st.session_state.phase_start_time is None: st.session_state.phase_start_time = time.time()
remaining = max(0, TIME_LIMIT - (time.time() - st.session_state.phase_start_time))
st.markdown(f"### Вопрос №{q['№']} из {len(st.session_state.questions)}")
render_timer(math.ceil(remaining), str(st.session_state.idx))

if remaining > 0:
    components.html(f"""<div id="img_{st.session_state.idx}" style="text-align:left;margin:5px 0;"><img src="{q['img']}" width="300" style="border:1px solid #444;border-radius:8px;"></div><script>setTimeout(()=>{{const c=document.getElementById('img_{st.session_state.idx}');if(c)c.innerHTML='<div style="font-style:italic;color:#666;padding:20px 0;">Время показа изображения истекло.</div>'; }}, {TIME_LIMIT*1000});</script>""", height=310)
else:
    st.markdown("<div style='color:#666;font-style:italic;padding:40px 0;text-align:left;'>Время показа изображения истекло.</div>", unsafe_allow_html=True)

st.markdown("---")

def finish(ans: str):
    ms = int((time.time() - st.session_state.phase_start_time) * 1000)
    ok = clean(ans) == clean(q["correct"]) if q["qtype"] == "letters" else ans.lower() == q["correct"].lower()
    Q.put([datetime.datetime.utcnow().isoformat(), st.session_state.name, q["№"], q["group"], q["alg"], q["qtype"], q["prompt"], ans, q["correct"], ms, ok, st.session_state.session_id])
    bump_counter(q["group"], q["alg"])
    st.session_state.update(idx = st.session_state.idx + 1, phase = "intro", phase_start_time = None, _timer_flags = {})
    st.experimental_rerun()

if q["qtype"] == "corners":
    sel = st.radio(q["prompt"], ["Да, углы одного цвета.","Нет, углы окрашены в разные цвета.","Затрудняюсь ответить."], index=None, key=f"r{st.session_state.idx}")
    if sel: finish("да" if sel.startswith("Да") else "нет" if sel.startswith("Нет") else "затрудняюсь")
else:
    txt = st.text_input(q["prompt"], key=f"t{st.session_state.idx}", placeholder="Введите русские буквы и нажмите Enter")
    st.caption("Чтобы ввести буквы, нажмите Enter. Если не видите букв, очистите поле ввода.")
    col, _ = st.columns([1, 3])
    error_flag = False
    with col:
        has_letters = bool(re.search(r"[А-Яа-яЁё]", txt))
        btn_clicked = st.button("Не вижу букв", key=f"none{st.session_state.idx}", disabled=has_letters)
        if btn_clicked:
            if has_letters:
                error_flag = True
            else:
                finish("Не вижу")
    if error_flag:
        st.markdown("<div style='margin-top:10px;padding:12px 16px;border-radius:8px;background:#f8d7da;color:#111;font-size:1.05rem;font-weight:500;white-space:nowrap;'>Очистите&nbsp;поле&nbsp;ввода,&nbsp;если&nbsp;не&nbsp;видите&nbsp;букв.</div>", unsafe_allow_html=True)
    if not btn_clicked and txt and re.fullmatch(r"[А-Яа-яЁё ,.;:-]+", txt):
        finish(txt.strip())
    elif txt and not re.fullmatch(r"[А-Яа-яЁё ,.;:-]+", txt):
        st.error("Допустимы только русские буквы и знаки пунктуации.")


