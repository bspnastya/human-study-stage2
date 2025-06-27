from __future__ import annotations
from streamlit_autorefresh import st_autorefresh
import random, time, datetime, secrets, threading, queue, re, itertools, json, sys
from typing import List, Dict
import streamlit as st, streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path


st.set_page_config(page_title="Визуализация многоканальных изображений",
                   page_icon="🎯", layout="centered",
                   initial_sidebar_state="collapsed")

MOBILE_QS_FLAG = "mobile"
BASE_URL       = "https://storage.yandexcloud.net/test3123234442"
TIME_LIMIT     = 15
TARGET_SHOWS   = 21                            

GROUPS = ["img1_dif_corners", "img2_dif_corners",
          "img3_same_corners_no_symb",
          "img4_same_corners", "img5_same_corners"]

ALGS_LET = ["pca_rgb_result",
            "socolov_lab_result",
            "socolov_rgb_result",
            "umap_rgb_result"]

ALGS_COR = ["socolov_lab_result", "socolov_rgb_result"]

CORNER = {"img1_dif_corners":"нет","img2_dif_corners":"нет",
          "img3_same_corners_no_symb":"да","img4_same_corners":"да",
          "img5_same_corners":"да"}

LETTER = {"img1_dif_corners":"ж","img2_dif_corners":"фя",
          "img3_same_corners_no_symb":"Не вижу",
          "img4_same_corners":"аб","img5_same_corners":"юэы"}

LETTER_GROUPS_WITH_CHARS = [
    "img1_dif_corners","img2_dif_corners",
    "img4_same_corners","img5_same_corners"
]
NO_CHAR_GROUP = "img3_same_corners_no_symb"


if "initialized" not in st.session_state:
    st.session_state.update(
        initialized=True, questions=[], idx=0, name="",
        phase="intro", phase_start_time=None, pause_until=0.0,
        _timer_flags={}, session_id=secrets.token_hex(8)
    )


components.html(f"""
<script>
(function() {{
  const f='{MOBILE_QS_FLAG}', m=innerWidth<1024;
  if (m) document.documentElement.classList.add('mobile-client');
  const qs=new URLSearchParams(location.search);
  if (m && !qs.has(f)) {{ qs.set(f,'1'); location.search=qs.toString(); }}
}})();
</script>""", height=0)

if st.experimental_get_query_params().get(MOBILE_QS_FLAG)==["1"]:
    st.markdown("""
    <style>
      body{background:#808080;color:#fff;display:flex;align-items:center;
            justify-content:center;height:100vh;margin:0;}
      h2{font-size:1.3rem;font-weight:500;line-height:1.4;}
    </style>
    <h2>Уважаемый участник<br>Данное исследование доступно только с <strong>ПК или ноутбука</strong>.</h2>
    """, unsafe_allow_html=True)
    st.stop()


st.markdown("""
<style>
html,body,.stApp,[data-testid="stAppViewContainer"],.main,.block-container{
    background:#808080!important;color:#111!important;}
h1,h2,h3,h4,h5,h6,p,label,li,span{color:#111!important;}
header[data-testid="stHeader"]{display:none;}
.stButton>button{min-height:52px;padding:0 20px;border:1px solid #555;
    background:#222;color:#ddd;border-radius:8px;}
input[data-testid="stTextInput"]{height:52px;padding:0 16px;font-size:1.05rem;}
</style>
""", unsafe_allow_html=True)


def open_book():
    scopes = ["https://spreadsheets.google.com/feeds",
              "https://www.googleapis.com/auth/drive"]
    creds  = ServiceAccountCredentials.from_json_keyfile_dict(
                dict(st.secrets["gsp"]), scopes)
    return gspread.authorize(creds).open("human_study_results")

BOOK   = open_book()
LOG_WS = BOOK.worksheet("stage2_log")
STAT_WS= BOOK.worksheet("stage2_stats")

def read_counters() -> dict[tuple[str,str], int]:
    return {(r["image_id"], r["alg"]): int(r["shows"])
            for r in STAT_WS.get_all_records()}

def bump_counter(img:str, alg:str):
    data = STAT_WS.get_all_values()
    for i, row in enumerate(data[1:], start=2):
        if row[0]==img and row[1]==alg:
            STAT_WS.update_cell(i,3, int(row[2] or 0)+1)
            return
    STAT_WS.append_row([img, alg, 1], value_input_option="RAW")


GLOBAL_Q = globals().setdefault("_GLOBAL_Q", queue.Queue(maxsize=1000))
if not globals().get("_WRITER"):
    def writer():
        buf=[]
        while True:
            try: buf.append(GLOBAL_Q.get(timeout=1))
            except queue.Empty: pass
            if buf:
                try: LOG_WS.append_rows(buf, value_input_option="RAW"); buf.clear()
                except: buf.clear()
    threading.Thread(target=writer, daemon=True).start()
    globals()["_WRITER"]=True

if "letters_plan" not in st.session_state:
    shuf = random.sample(ALGS_LET, len(ALGS_LET))
    st.session_state.letters_plan = {
        g: shuf[i] for i, g in enumerate(LETTER_GROUPS_WITH_CHARS)
    }
    st.session_state.letters_plan[NO_CHAR_GROUP] = random.choice(ALGS_LET)


def url(g:str, a:str)->str: return f"{BASE_URL}/{g}_{a}.png"
def clean(s:str)->set[str]: return set(re.sub("[ ,.;:-]+", "", (s or "").lower()))


def make_qs() -> List[Dict]:
    cnt   = read_counters()
    seq   = []
    
    for g in GROUPS:
        alg = st.session_state.letters_plan[g]
        if cnt.get((g, alg),0) < TARGET_SHOWS:
            seq.append({"group":g,"alg":alg,"img":url(g,alg),
                        "qtype":"letters",
                        "prompt":"Если на изображении вы видите буквы, то укажите, какие именно.",
                        "correct":LETTER[g]})

    for g, alg in itertools.product(GROUPS, ALGS_COR):
        if cnt.get((g, alg),0) < TARGET_SHOWS:
            seq.append({"group":g,"alg":alg,"img":url(g,alg),
                        "qtype":"corners",
                        "prompt":"Считаете ли вы, что правый верхний угол и нижний левый угол одного цвета с точностью до оттенка?",
                        "correct":CORNER[g]})
    random.shuffle(seq)
    for i,q in enumerate(seq,1): q["№"]=i
    return seq

if not st.session_state.questions:
    st.session_state.questions = make_qs()


def render_timer(sec:int, tid:str):
    if tid in st.session_state._timer_flags: return
    components.html(f"""
    <div style="display:flex;justify-content:flex-start;margin:10px 0 15px 0;">
      <div style="font-size:20px;font-weight:700;">
        Осталось&nbsp;<span id="t{tid}">{sec}</span>&nbsp;сек
      </div>
    </div>
    <script>
      let t{tid}={sec};
      const s{tid}=document.getElementById('t{tid}');
      const i{tid}=setInterval(()=>{{if(--t{tid}<0){{clearInterval(i{tid});return;}}
                                     s{tid}.innerText=t{tid};}},1000);
    </script>""", unsafe_allow_html=True)
    st.session_state._timer_flags[tid]=True

if st.session_state.pause_until > time.time():
    st_autorefresh(interval=600, key="pause")
    st.stop()


if not st.session_state.name:
    st.markdown("""
    <div style="color:#111;">
      <h2>Уважаемый участник,<br>добро пожаловать в эксперимент по изучению восприятия изображений.</h2>
      <p><b>Как проходит эксперимент</b><br>
      Всего вы ответите на <b>40</b> вопросов. На всё уйдёт 10-15 минут.</p>
      <p><b>Важно&nbsp;— только ПК/ноутбук, полная анонимность.</b></p>
      <p>Введите псевдоним или нажмите «Сгенерировать».</p>
    </div>""", unsafe_allow_html=True)
    name = st.text_input("", placeholder="Ваш псевдоним",
                         key="usernm", label_visibility="collapsed")
    if st.button("🎲 Сгенерировать"):
        st.session_state.name = f"Участник_{secrets.randbelow(900000)+100000}"
        st.experimental_rerun()
    if name:
        st.session_state.name = name.strip()
        st.experimental_rerun()
    st.stop()


def finish(ans:str):
    q  = st.session_state.questions[st.session_state.idx]
    ms = int((time.time()-st.session_state.phase_start_time)*1000)
    ok = clean(ans)==clean(q["correct"]) if q["qtype"]=="letters" \
         else ans.lower()==q["correct"].lower()
    GLOBAL_Q.put([
        datetime.datetime.utcnow().isoformat(), st.session_state.name,
        q["№"], q["group"], q["alg"], q["qtype"], q["prompt"],
        ans, q["correct"], ms, ok, st.session_state.session_id
    ])
    bump_counter(q["group"], q["alg"])
    st.session_state.update(idx=st.session_state.idx+1,
                            phase="intro", phase_start_time=None,
                            _timer_flags={}, pause_until=time.time()+0.4)
    st.experimental_rerun()


if st.session_state.idx >= len(st.session_state.questions):
    st.markdown("""
    <div style='margin-top:50px;padding:40px;text-align:center;font-size:2rem;
                color:#fff;background:#262626;border-radius:12px;'>
      Вы завершили прохождение.<br><b>Спасибо за участие!</b>
    </div>""", unsafe_allow_html=True)
    st.balloons(); st.stop()


cur = st.session_state.questions[st.session_state.idx]

if st.session_state.phase=="intro":
    txt_c = """Сейчас вы увидите изображение. Цель — оценить, одинаковы ли цвета
    <b>правого верхнего</b> и <b>левого нижнего</b> углов «с точностью до&nbsp;оттенка».
    Картинка будет видна в течение <b>15 секунд</b>, время на ответ не ограничено."""
    txt_l = """Сейчас вы увидите изображение. Цель — определить, есть ли на нем
    <b>буквы русского алфавита</b>. Введите найденные буквы через пробелы,
    запятые или слитно. Если букв нет — нажмите <b>«Не вижу букв»</b>."""
    st.markdown(f"<div style='font-size:1.1rem;line-height:1.6;margin-bottom:30px;'>"
                f"{txt_c if cur['qtype']=='corners' else txt_l}</div>",
                unsafe_allow_html=True)
    if st.button("Перейти к вопросу"):
        st.session_state.update(phase="question",
                                phase_start_time=time.time())
        st.experimental_rerun()
    st.stop()


remaining = TIME_LIMIT - (time.time()-st.session_state.phase_start_time)
if remaining < 0: remaining = 0

st.markdown(f"### Вопрос №{cur['№']} из {len(st.session_state.questions)}")
render_timer(int(remaining), str(st.session_state.idx))

ph = st.empty()
if remaining>0:
    ph.image(cur["img"], width=300)
else:
    ph.markdown("<div style='color:#666;font-style:italic;padding:40px 0;"
                "text-align:center;'>Время показа изображения истекло.</div>",
                unsafe_allow_html=True)

st.markdown("---")

if cur["qtype"]=="corners":
    sel = st.radio("", ["Да, углы одного цвета.",
                        "Нет, углы окрашены в разные цвета.",
                        "Затрудняюсь ответить."],
                   index=None, key=f"r{idx}")
    if sel:
        finish("да" if sel.startswith("Да") else
               "нет" if sel.startswith("Нет") else "затрудняюсь")
else:
    txt = st.text_input(cur["prompt"], key=f"t{idx}",
                        placeholder="Введите буквы и Enter")
    btn_dis = bool(re.search(r"[А-Яа-яЁё]", txt or ""))
    col,_ = st.columns([1,3])
    with col:
        if st.button("Не вижу букв", key=f"none{idx}", disabled=btn_dis):
            finish("Не вижу")
    if txt and re.fullmatch(r"[А-Яа-яЁё ,.;:-]+", txt):
        finish(txt.strip())

