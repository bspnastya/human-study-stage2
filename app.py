from __future__ import annotations
from streamlit_autorefresh import st_autorefresh
import random, time, datetime, secrets, threading, queue, re, itertools, json, sys
from typing import List, Dict
import streamlit as st, gspread, streamlit.components.v1 as components
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path

st.set_page_config(page_title="Визуализация многоканальных изображений",
                   page_icon="🎯", layout="centered",
                   initial_sidebar_state="collapsed")

MOBILE_QS_FLAG = "mobile"
BASE_URL       = "https://storage.yandexcloud.net/test3123234442"
TIME_LIMIT     = 15
TARGET_SHOWS   = 21

GROUPS   = ["img1_dif_corners","img2_dif_corners","img3_same_corners_no_symb",
            "img4_same_corners","img5_same_corners"]
ALGS_LET = ["pca_rgb_result","socolov_lab_result","socolov_rgb_result","umap_rgb_result"]
ALGS_COR = ["socolov_lab_result","socolov_rgb_result"]
CORNER   = {"img1_dif_corners":"нет","img2_dif_corners":"нет","img3_same_corners_no_symb":"да",
            "img4_same_corners":"да","img5_same_corners":"да"}
LETTER   = {"img1_dif_corners":"ж","img2_dif_corners":"фя","img3_same_corners_no_symb":"Не вижу",
            "img4_same_corners":"аб","img5_same_corners":"юэы"}

if "initialized" not in st.session_state:
    st.session_state.update(initialized=True, questions=[], idx=0, name="",
                            phase="intro", phase_start_time=None, pause_until=0,
                            _timer_flags={}, session_id=secrets.token_hex(8))

components.html(f"""
<script>
(function() {{
  const f='{MOBILE_QS_FLAG}',m=innerWidth<1024;
  if(m)document.documentElement.classList.add('mobile-client');
  const qs=new URLSearchParams(location.search);
  if(m&&!qs.has(f)){{qs.set(f,'1');location.search=qs.toString();}}
}})();
</script>""", height=0)

if (st.query_params if hasattr(st,"query_params") else st.experimental_get_query_params()
     ).get(MOBILE_QS_FLAG)==["1"]:
    st.markdown("""<style>body{background:#808080;color:#fff;
    display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
    h2{font-size:1.3rem;font-weight:500;line-height:1.4;}</style>
    <h2>Уважаемый участник<br>Данное исследование доступно только с <strong>ПК или ноутбука</strong>.</h2>""",
    unsafe_allow_html=True)
    st.stop()

st.markdown("""
<style>
html,body,.stApp,[data-testid="stAppViewContainer"],.main,.block-container{background:#808080!important;color:#111!important;}
h1,h2,h3,h4,h5,h6,p,label,li,span{color:#111!important;}
header[data-testid="stHeader"]{display:none;}
.stButton>button{min-height:52px;padding:0 20px;border:1px solid #555;background:#222;color:#ddd;border-radius:8px;}
input[data-testid="stTextInput"]{height:52px;padding:0 16px;font-size:1.05rem;}
</style>""", unsafe_allow_html=True)

def open_book():
    scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds=ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gsp"]), scopes)
    return gspread.authorize(creds).open("human_study_results")

BOOK     = open_book()
LOG_WS   = BOOK.worksheet("stage2_log")
STAT_WS  = BOOK.worksheet("stage2_stats")

def read_counters():
    rows=STAT_WS.get_all_records()
    return {(r["image_id"], r["alg"]): int(r["shows"]) for r in rows}

def bump_counter(img, alg):
    vals=STAT_WS.get_all_values()
    for i,row in enumerate(vals[1:], start=2):
        if row[0]==img and row[1]==alg:
            STAT_WS.update_cell(i,3,int(row[2] or 0)+1); return
    STAT_WS.append_row([img,alg,1], value_input_option="RAW")

if "_WRITER" not in globals():
    log_q=queue.Queue(maxsize=1000)
    globals()["_GLOBAL_QUEUE"]=log_q
    Path("backup_results").mkdir(exist_ok=True)

    def writer():
        buf=[]
        while True:
            try: buf.append(log_q.get(timeout=1))
            except queue.Empty: pass
            if buf:
                try:
                    LOG_WS.append_rows(buf, value_input_option="RAW"); buf.clear()
                except:
                    for r in buf:
                        Path("backup_results", f"{int(time.time()*1e6)}.json"
                            ).write_text(json.dumps(r, ensure_ascii=False))
                    buf.clear()
    threading.Thread(target=writer, daemon=True).start()
    globals()["_WRITER"]=True
else:
    log_q=globals()["_GLOBAL_QUEUE"]

def url(g,a): return f"{BASE_URL}/{g}_{a}.png"
def clean(s): return set(re.sub("[ ,.;:-]+","",s.lower()))

def make_qs():
    cnt=read_counters()
    letters=[]
    for g in GROUPS:
        pool=[a for a in ALGS_LET if cnt.get((g,a),0)<TARGET_SHOWS]
        if pool:
            a=random.choice(pool)
            letters.append({"group":g,"alg":a,"img":url(g,a),"qtype":"letters",
                            "prompt":"Если на изображении вы видите буквы, то укажите, какие именно.",
                            "correct":LETTER[g]})
    corners=[{"group":g,"alg":a,"img":url(g,a),"qtype":"corners",
              "prompt":"Считаете ли вы, что правый верхний угол и нижний левый угол одного цвета с точностью до оттенка?",
              "correct":CORNER[g]}
             for g,a in itertools.product(GROUPS, ALGS_COR)
             if cnt.get((g,a),0)<TARGET_SHOWS]
    seq=letters+corners
    random.shuffle(seq)
    for i,q in enumerate(seq,1): q["№"]=i
    return seq

def render_timer(sec, tid):
    if tid in st.session_state["_timer_flags"]: return
    components.html(f"""
    <div style="display:flex;justify-content:center;margin:10px 0 15px 0;">
      <div style="font-size:20px;font-weight:700;">Осталось&nbsp;<span id="t{tid}">{sec}</span>&nbsp;сек</div>
    </div>
    <script>
      let t{tid}={sec}; const s{tid}=document.getElementById('t{tid}');
      const i{tid}=setInterval(()=>{{if(--t{tid}<0){{clearInterval(i{tid});return;}}
      if(s{tid}) s{tid}.innerText=t{tid};}},1000);
    </script>""", height=70)
    st.session_state["_timer_flags"][tid]=True

def finish(ans):
    q=st.session_state.questions[st.session_state.idx]
    ms=int((time.time()-st.session_state.phase_start_time)*1000)
    ok=clean(ans)==clean(q["correct"]) if q["qtype"]=="letters" else ans.lower()==q["correct"].lower()
    log_q.put([datetime.datetime.utcnow().isoformat(),st.session_state.name,q["№"],
               q["group"],q["alg"],q["qtype"],q["prompt"],ans,q["correct"],ms,ok,
               st.session_state.session_id])
    bump_counter(q["group"], q["alg"])
    st.session_state.update(idx=st.session_state.idx+1, phase="intro",
                            phase_start_time=None, _timer_flags={})
    st.experimental_rerun()

if not st.session_state.questions:
    st.session_state.questions=make_qs()

if st.session_state.pause_until>time.time():
    st_autorefresh(interval=600, key="pause"); st.stop()

if st.session_state.idx>=len(st.session_state.questions):
    st.markdown("<div style='margin-top:50px;padding:40px;text-align:center;font-size:2rem;color:#fff;background:#262626;border-radius:12px;'>Вы завершили прохождение.<br><b>Спасибо за участие!</b></div>", unsafe_allow_html=True)
    st.balloons(); st.stop()

if not st.session_state.name:
    st.markdown("""<div style="color:#111;">
    <h2>Уважаемый участник,<br>добро пожаловать в эксперимент по изучению восприятия изображений.</h2>
    <p>Для начала теста введите любой псевдоним и нажмите Enter или нажмите «Сгенерировать псевдоним».</p>
    </div>""", unsafe_allow_html=True)
    n=st.text_input("", placeholder="Ваш псевдоним", key="nm", label_visibility="collapsed")
    if st.button("🎲 Сгенерировать псевдоним"):
        st.session_state.name=f"Участник_{secrets.randbelow(900000)+100000}"; st.experimental_rerun()
    if n: st.session_state.name=n.strip(); st.experimental_rerun()
    st.stop()

q=st.session_state.questions[st.session_state.idx]

if st.session_state.phase=="intro":
    st.markdown(q["prompt"], unsafe_allow_html=True)
    if st.button("Перейти к вопросу"):
        st.session_state.update(phase="question", phase_start_time=time.time()); st.experimental_rerun()
    st.stop()

remaining=TIME_LIMIT-(time.time()-st.session_state.phase_start_time)
if remaining<0: remaining=0
st.markdown(f"### Вопрос №{q['№']} из {len(st.session_state.questions)}")
render_timer(int(remaining), str(st.session_state.idx))

placeholder=st.empty()
if remaining>0:
    placeholder.image(q["img"], width=300)
else:
    placeholder.markdown("<div style='color:#666;font-style:italic;padding:40px 0;text-align:center;'>Время показа изображения истекло.</div>", unsafe_allow_html=True)

st.markdown("---")

if q["qtype"]=="corners":
    sel=st.radio("",["Да, углы одного цвета.","Нет, углы окрашены в разные цвета.","Затрудняюсь ответить."],
                 index=None, key=f"r{st.session_state.idx}")
    if sel: finish("да" if sel.startswith("Да") else "нет" if sel.startswith("Нет") else "затрудняюсь")
else:
    txt=st.text_input(q["prompt"], key=f"t{st.session_state.idx}", placeholder="Введите буквы и Enter")
    col,_=st.columns([1,3])
    with col:
        btn_dis=bool(re.search(r"[А-Яа-яЁё]", txt))
        if st.button("Не вижу букв", disabled=btn_dis):
            finish("Не вижу")
    if txt and not btn_dis and re.fullmatch(r"[А-Яа-яЁё ,.;:-]+", txt):
        finish(txt.strip())
    elif txt and btn_dis:
        st.info("Нажмите Enter, если указали буквы.")


