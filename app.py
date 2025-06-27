from __future__ import annotations
from streamlit_autorefresh import st_autorefresh
import streamlit as st, streamlit.components.v1 as components
import gspread, secrets, random, time, datetime, threading, queue, re, itertools, sys, json
from oauth2client.service_account import ServiceAccountCredentials
from pathlib import Path

st.set_page_config(page_title="Визуализация многоканальных изображений", page_icon="🎯",
                   layout="centered", initial_sidebar_state="collapsed")

MOBILE_QS_FLAG = "mobile"
BASE_URL = "https://storage.yandexcloud.net/test3123234442"
TIME_LIMIT = 15
TARGET_SHOWS = 21

GROUPS = ["img1_dif_corners", "img2_dif_corners", "img3_same_corners_no_symb",
          "img4_same_corners", "img5_same_corners"]
ALGS_LET = ["pca_rgb_result", "socolov_lab_result", "socolov_rgb_result", "umap_rgb_result"]
ALGS_COR = ["socolov_lab_result", "socolov_rgb_result"]

CORNER = {"img1_dif_corners": "нет", "img2_dif_corners": "нет",
          "img3_same_corners_no_symb": "да", "img4_same_corners": "да",
          "img5_same_corners": "да"}
LETTER = {"img1_dif_corners": "ж", "img2_dif_corners": "фя",
          "img3_same_corners_no_symb": "Не вижу", "img4_same_corners": "аб",
          "img5_same_corners": "юэы"}

components.html(f"""
<script>
(function(){{
  const f='{MOBILE_QS_FLAG}',m=innerWidth<1024;
  if(m)document.documentElement.classList.add('mobile-client');
  const qs=new URLSearchParams(location.search);
  if(m&&!qs.has(f)){{qs.set(f,'1');location.search=qs.toString();}}
}})();
</script>""", height=0)

if (st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()).get(MOBILE_QS_FLAG) == ["1"]:
    st.markdown("""
    <style>body{background:#808080;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
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

if "initialized" not in st.session_state:
    st.session_state.update(initialized=True, questions=[], idx=0, name="",
                            phase="intro", phase_start_time=None,
                            _timer_flags={}, session_id=secrets.token_hex(8))

scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gsp"]), scopes)
book = gspread.authorize(creds).open("human_study_results")
LOG_WS = book.worksheet("stage2_log")
STAT_WS = book.worksheet("stage2_stats")

def read_counters():
    return {(r["image_id"], r["alg"]): int(r["shows"]) for r in STAT_WS.get_all_records()}

def bump_counter(img, alg):
    rows = STAT_WS.get_all_values()
    for i, row in enumerate(rows[1:], start=2):
        if row[0] == img and row[1] == alg:
            STAT_WS.update_cell(i, 3, int(row[2] or 0) + 1)
            return
    STAT_WS.append_row([img, alg, 1], value_input_option="RAW")

module = sys.modules[__name__]
if not hasattr(module, "_writer_started"):
    module._writer_started = True
    module._log_queue = queue.Queue(maxsize=1000)
    def writer():
        buf = []
        while True:
            try: buf.append(module._log_queue.get(timeout=1))
            except queue.Empty: pass
            if buf:
                try: LOG_WS.append_rows(buf, value_input_option="RAW"); buf.clear()
                except: buf.clear()
    threading.Thread(target=writer, daemon=True).start()

def make_qs():
    cnt = read_counters()
    letters = []
    for g in GROUPS:
        pool = [a for a in ALGS_LET if cnt.get((g, a), 0) < TARGET_SHOWS]
        if pool:
            a = random.choice(pool)
            letters.append({"group": g, "alg": a, "img": f"{BASE_URL}/{g}_{a}.png",
                            "qtype": "letters",
                            "prompt": "Если на изображении вы видите буквы, то укажите, какие именно.",
                            "correct": LETTER[g]})
    corners = [{"group": g, "alg": a, "img": f"{BASE_URL}/{g}_{a}.png",
                "qtype": "corners",
                "prompt": "Считаете ли вы, что правый верхний угол и нижний левый угол одного цвета с точностью до оттенка?",
                "correct": CORNER[g]}
               for g, a in itertools.product(GROUPS, ALGS_COR)
               if cnt.get((g, a), 0) < TARGET_SHOWS]
    seq = letters + corners
    random.shuffle(seq)
    for i, q in enumerate(seq, 1): q["№"] = i
    return seq

if not st.session_state.questions:
    st.session_state.questions = make_qs()

def render_timer(sec, tid):
    if tid in st.session_state["_timer_flags"]: return
    components.html(f"""
    <div style="display:flex;justify-content:center;margin:10px 0 15px 0;">
      <div style="font-size:20px;font-weight:700;">Осталось&nbsp;<span id="t{tid}">{sec}</span>&nbsp;сек</div>
    </div>
    <script>
      let t{tid}={sec};
      const s{tid}=document.getElementById('t{tid}');
      const i{tid}=setInterval(()=>{{if(--t{tid}<0){{clearInterval(i{tid});return;}}s{tid}.innerText=t{tid};}},1000);
    </script>""", unsafe_allow_html=True)
    st.session_state["_timer_flags"][tid] = True

def clean(s): return set(re.sub("[ ,.;:-]+", "", s.lower()))

def finish(ans):
    q = st.session_state.questions[st.session_state.idx]
    ms = int((time.time() - st.session_state.phase_start_time) * 1000)
    ok = clean(ans) == clean(q["correct"]) if q["qtype"] == "letters" else ans.lower() == q["correct"].lower()
    module._log_queue.put([datetime.datetime.utcnow().isoformat(), st.session_state.name, q["№"],
                           q["group"], q["alg"], q["qtype"], q["prompt"], ans,
                           q["correct"], ms, ok, st.session_state.session_id], block=False)
    bump_counter(q["group"], q["alg"])
    st.session_state.update(idx=st.session_state.idx + 1, phase="intro",
                            phase_start_time=None, _timer_flags={})
    st.experimental_rerun()

if st.session_state.idx >= len(st.session_state.questions):
    st.markdown("<div style='margin-top:50px;padding:40px;text-align:center;font-size:2rem;color:#fff;background:#262626;border-radius:12px;'>Вы завершили прохождение.<br><b>Спасибо за участие!</b></div>",
                unsafe_allow_html=True)
    st.balloons()
    st.stop()

if not st.session_state.name:
    st.markdown("""
    <div style="color:#111;">
      <h2>Уважаемый участник,<br>добро пожаловать в эксперимент по изучению восприятия изображений.</h2>
      <p><b>Как проходит эксперимент</b><br>
      В ходе эксперимента вам нужно будет отвечать на простые вопросы об изображениях, которые вы увидите на экране. Всего вам предстоит ответить на <b>40</b> вопросов. Прохождение теста займет около 10-15 минут.</p>
      <p><b>Пожалуйста, проходите тест спокойно: исследование не направлено на оценку испытуемых. Оценивается работа алгоритмов, которые выдают картинки разного качества.</b></p>
      <p><b>Что это за изображения?</b><br>
      Изображения — результат работы разных методов. Ни одно из них не является «эталоном». Цель эксперимента — понять, какие методы обработки лучше сохраняют информацию.</p>
      <p><b>Важно</b><br>
      Эксперимент полностью анонимен. Проходить его следует <b>только на компьютере или ноутбуке</b>.</p>
      <p>Для начала теста введите любой псевдоним и нажмите Enter или нажмите «Сгенерировать псевдоним».</p>
    </div>""", unsafe_allow_html=True)
    nick = st.text_input("", placeholder="Ваш псевдоним", key="nm", label_visibility="collapsed")
    if st.button("🎲 Сгенерировать псевдоним"):
        st.session_state.name = f"Участник_{secrets.randbelow(900000)+100000}"; st.experimental_rerun()
    if nick: st.session_state.name = nick.strip(); st.experimental_rerun()
    st.stop()

q = st.session_state.questions[st.session_state.idx]

if st.session_state.phase == "intro":
    st.markdown(q["prompt"], unsafe_allow_html=True)
    if st.button("Перейти к вопросу"): st.session_state.update(phase="question", phase_start_time=time.time()); st.experimental_rerun()
    st.stop()

remaining = TIME_LIMIT - (time.time() - st.session_state.phase_start_time)
if remaining < 0: remaining = 0

st.markdown(f"### Вопрос №{q['№']} из {len(st.session_state.questions)}")
render_timer(int(remaining), str(st.session_state.idx))

placeholder = st.empty()
if remaining > 0:
    placeholder.image(q["img"], width=300)
else:
    placeholder.markdown("<div style='color:#666;font-style:italic;padding:40px 0;text-align:center;'>Время показа изображения истекло.</div>",
                         unsafe_allow_html=True)

st.markdown("---")

if q["qtype"] == "corners":
    sel = st.radio("", ["Да, углы одного цвета.", "Нет, углы окрашены в разные цвета.", "Затрудняюсь ответить."],
                   index=None, key=f"r{st.session_state.idx}")
    if sel: finish("да" if sel.startswith("Да") else "нет" if sel.startswith("Нет") else "затрудняюсь")
else:
    txt = st.text_input(q["prompt"], key=f"t{st.session_state.idx}", placeholder="Введите русские буквы и нажмите Enter")
    col, _ = st.columns([1, 3])
    with col:
        btn_dis = bool(re.search(r"[А-Яа-яЁё]", txt))
        if st.button("Не вижу букв", disabled=btn_dis): finish("Не вижу")
    if txt and not btn_dis and re.fullmatch(r"[А-Яа-яЁё ,.;:-]+", txt): finish(txt.strip())
    elif txt and btn_dis: st.info("Нажмите Enter, если указали буквы.")

