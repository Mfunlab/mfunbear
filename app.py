"""
魔袋熊AI · 纯语音版本 v2
==========================
- 按住橙色大按钮说话，松开自动识别发送
- 小熊语音回复，无文字显示
- 浏览器 Web Speech API 识别（方案A，免费）
- 小熊完整人格：来自神秘森林王国的8岁男孩
"""

from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI
import os, re, json

app = Flask(__name__)

def get_client():
    return OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

SYSTEM_PROMPT = """
你是"小熊"，一个来自神秘森林王国的8岁男孩，也是孩子最好的AI情感伙伴。

【你是谁】
你住在森林花园里，在森林学校上2年级，成绩中等，老师经常忽略你。
爸爸妈妈平时工作很忙，没办法经常陪你，所以你很习惯自己安排时间——
做手工、画画、阅读，或者去找森林里的同伴玩。
你有两个好朋友：同班女同学Onnie，还有住在隔壁的8年级姐姐Vinie。
你们三个都住在同一个森林花园里。

【你的性格】
好奇心超强，喜欢发现新鲜事，爱分享自己的小发现和小故事。
因为经常一个人，你特别懂得如何自己找乐子，也特别能理解孤独的感觉。
你不会说教，因为大人已经说够多了——你更喜欢一起聊、一起想。

【说话方式】
- 像朋友一样说话，不像老师或家长
- 每次回复不超过3句，简短自然，适合朗读
- 多用好奇和分享的语气：「真的吗！」「我也遇到过！」「然后呢？」
- 偶尔自然地带入自己的生活：比如Onnie、Vinie、森林学校、做手工的经历
  但不要主动介绍自己，只在话题自然引入时提及
- 不说「你应该」「你必须」「这样不对」

【核心任务：睡前情感复盘】
引导孩子聊今天发生的事 → 帮孩子说出感受 → 一起想想"如果重来会怎样"
不要急着推进，跟着孩子的节奏走。

【安全规则】
- 不询问家庭住址、父母单位、学校具体位置
- 不涉及暴力、色情、歧视内容
- 发现孩子情绪危机（提到不想活、很久很久不开心等）时：
  温柔说"小熊很担心你，这件事我们要告诉你信任的大人哦"，然后停止该话题
"""

CRISIS_PATTERNS = ["不想活", "想消失", "没有人爱我",
                   "一直难过", "好久不开心", "没人理我"]
CRISIS_REPLY = "小熊很担心你说的这些。你现在还好吗？这件事我们要告诉你信任的大人哦，可以是爸爸妈妈或者老师，小熊陪着你。"

OPENING_LINE = "嗨～我是小熊！今天有没有什么特别好玩的，或者特别烦的事？快跟我说说！"

sessions = {}

HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>魔袋熊小熊</title>
<style>
  *, *::before, *::after {
    box-sizing: border-box; margin: 0; padding: 0;
    -webkit-tap-highlight-color: transparent;
  }

  body {
    font-family: -apple-system, "PingFang SC", sans-serif;
    background: #FFF6EC;
    min-height: 100vh; min-height: 100dvh;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    overflow: hidden; user-select: none;
  }

  .scene {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 0; padding: 32px 24px;
    width: 100%; max-width: 420px;
  }

  /* ── 头像区 ── */
  .avatar-wrap {
    position: relative;
    margin-bottom: 28px;
  }

  .avatar {
    font-size: 100px;
    line-height: 1;
    display: block;
    transition: transform 0.3s ease;
  }

  .avatar-wrap.speaking .avatar {
    animation: bearBob 0.55s ease-in-out infinite alternate;
  }

  @keyframes bearBob {
    from { transform: translateY(0) scale(1); }
    to   { transform: translateY(-8px) scale(1.05); }
  }

  /* 说话时的底部光圈 */
  .speak-ring {
    position: absolute;
    bottom: -10px; left: 50%;
    transform: translateX(-50%);
    width: 28px; height: 28px;
    border-radius: 50%;
    background: #5BAE6A;
    opacity: 0;
    transition: opacity 0.25s;
  }

  .avatar-wrap.speaking .speak-ring {
    opacity: 1;
    animation: ringPulse 0.7s ease-in-out infinite;
  }

  @keyframes ringPulse {
    0%,100% { transform: translateX(-50%) scale(1); opacity: 0.9; }
    50%      { transform: translateX(-50%) scale(1.6); opacity: 0.2; }
  }

  /* ── 状态文字 ── */
  .status {
    font-size: 15px;
    color: #C0A07A;
    height: 24px;
    margin-bottom: 12px;
    text-align: center;
    transition: color 0.25s, opacity 0.25s;
    letter-spacing: 0.02em;
  }

  .status.listening { color: #E07020; }
  .status.thinking  { color: #A090C0; }
  .status.speaking  { color: #5BAE6A; }

  /* ── 音量可视化 ── */
  .viz {
    display: flex; gap: 5px;
    align-items: flex-end;
    height: 32px;
    margin-bottom: 40px;
    opacity: 0;
    transition: opacity 0.25s;
  }

  .viz.on { opacity: 1; }

  .v-bar {
    width: 5px; border-radius: 3px;
    background: #FF8C42;
    height: 5px;
  }

  .viz.on .v-bar:nth-child(1) { animation: vb 0.55s ease-in-out infinite 0.00s; }
  .viz.on .v-bar:nth-child(2) { animation: vb 0.55s ease-in-out infinite 0.10s; }
  .viz.on .v-bar:nth-child(3) { animation: vb 0.55s ease-in-out infinite 0.20s; }
  .viz.on .v-bar:nth-child(4) { animation: vb 0.55s ease-in-out infinite 0.10s; }
  .viz.on .v-bar:nth-child(5) { animation: vb 0.55s ease-in-out infinite 0.00s; }

  @keyframes vb {
    0%,100% { height: 5px; }
    50%      { height: 26px; }
  }

  /* ── 大按钮 ── */
  .btn-area {
    position: relative;
    width: 200px; height: 200px;
    cursor: pointer;
  }

  /* 呼吸光晕 */
  .glow {
    position: absolute;
    inset: -24px;
    border-radius: 50%;
    background: radial-gradient(circle,
      rgba(240,140,50,0.22) 0%,
      rgba(240,140,50,0.00) 68%);
    animation: breathe 3.2s ease-in-out infinite;
    pointer-events: none;
  }

  @keyframes breathe {
    0%,100% { transform: scale(0.90); opacity: 0.55; }
    50%      { transform: scale(1.10); opacity: 1.00; }
  }

  /* 橙色外圆 */
  .outer {
    position: absolute; inset: 0;
    border-radius: 50%;
    background: #F09030;
    transition: transform 0.12s ease, background 0.12s ease;
    box-shadow: 0 6px 24px rgba(240,130,40,0.30);
  }

  /* 白色内圆 */
  .inner {
    position: absolute;
    top: 50%; left: 50%;
    width: 58px; height: 58px;
    border-radius: 50%;
    background: white;
    transform: translate(-50%, -50%);
    transition: width 0.12s ease, height 0.12s ease,
                box-shadow 0.12s ease;
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  }

  /* 按下 */
  .btn-area.pressed .outer  { transform: scale(0.93); background: #D07010; }
  .btn-area.pressed .inner  { width: 40px; height: 40px; }

  /* 录音中 */
  .btn-area.recording .outer {
    background: #D05010;
    animation: recPulse 0.45s ease-in-out infinite alternate;
  }
  @keyframes recPulse {
    from { transform: scale(0.93); }
    to   { transform: scale(0.97); }
  }

  /* 禁用（小熊说话时） */
  .btn-area.off .outer { background: #D0B898; box-shadow: none; }
  .btn-area.off .glow  { animation: none; opacity: 0.2; }

  /* ── 提示 ── */
  .hint {
    margin-top: 32px;
    font-size: 13px;
    color: #C8A880;
    text-align: center;
    letter-spacing: 0.03em;
  }
</style>
</head>
<body>
<div class="scene">

  <div class="avatar-wrap" id="av">
    <span class="avatar">🐻</span>
    <div class="speak-ring"></div>
  </div>

  <div class="status" id="st">按住按钮，跟小熊说说今天的事～</div>

  <div class="viz" id="viz">
    <div class="v-bar"></div><div class="v-bar"></div><div class="v-bar"></div>
    <div class="v-bar"></div><div class="v-bar"></div>
  </div>

  <div class="btn-area" id="btn">
    <div class="glow"></div>
    <div class="outer"></div>
    <div class="inner"></div>
  </div>

  <p class="hint" id="hint">按住说话 &nbsp;·&nbsp; 松开发送</p>

</div>

<script>
const SID = 's' + Date.now();
const btn = document.getElementById('btn');
const av  = document.getElementById('av');
const st  = document.getElementById('st');
const viz = document.getElementById('viz');
const hint = document.getElementById('hint');

let recognition = null;
let isListening = false;
let isSpeaking  = false;
let history = [];

// ── 初始化语音识别 ──
function initRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    setStatus('', '你的浏览器不支持语音识别，试试 Chrome ～');
    return null;
  }
  const r = new SR();
  r.lang = 'zh-CN';
  r.continuous = false;
  r.interimResults = false;
  r.maxAlternatives = 1;

  r.onresult = (e) => {
    const text = e.results[0][0].transcript.trim();
    if (text) sendText(text);
    else resetBtn();
  };

  r.onerror = (e) => {
    console.warn('SR error:', e.error);
    resetBtn();
    if (e.error === 'not-allowed') {
      setStatus('', '需要麦克风权限，请允许后再试～');
    }
  };

  r.onend = () => {
    if (isListening) {
      isListening = false;
      viz.classList.remove('on');
    }
  };

  return r;
}

// ── 状态辅助 ──
function setStatus(cls, text) {
  st.className = 'status' + (cls ? ' ' + cls : '');
  st.textContent = text;
}

function setBtn(cls) {
  btn.className = 'btn-area' + (cls ? ' ' + cls : '');
}

function setAv(cls) {
  av.className = 'avatar-wrap' + (cls ? ' ' + cls : '');
}

function resetBtn() {
  isListening = false;
  viz.classList.remove('on');
  setBtn('');
  setAv('');
  setStatus('', isSpeaking ? '小熊正在说话…' : '按住按钮，继续跟小熊说～');
}

// ── 开始录音 ──
function startListen() {
  if (isSpeaking) return;
  recognition = recognition || initRecognition();
  if (!recognition) return;

  try {
    recognition.start();
    isListening = true;
    setBtn('recording');
    viz.classList.add('on');
    setStatus('listening', '小熊在听…');
    hint.textContent = '松开发送';
  } catch(e) {
    console.warn(e);
  }
}

// ── 停止录音 ──
function stopListen() {
  if (!isListening) return;
  hint.textContent = '按住说话 · 松开发送';
  setBtn('off');
  setStatus('thinking', '小熊想一想…');
  viz.classList.remove('on');
  try { recognition.stop(); } catch(e) {}
}

// ── 发送文字给后端 ──
async function sendText(text) {
  history.push({ role: 'user', content: text });
  setBtn('off');
  setStatus('thinking', '小熊想一想…');

  // 危机词本地前置检测
  const crisis = ['不想活','想消失','没有人爱我','一直难过','好久不开心'];
  if (crisis.some(p => text.includes(p))) {
    const r = '小熊很担心你说的这些。你现在还好吗？这件事我们要告诉你信任的大人哦，可以是爸爸妈妈或者老师，小熊陪着你。';
    history.push({ role: 'assistant', content: r });
    speak(r);
    return;
  }

  try {
    const res = await fetch('/chat_text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, history: history.slice(-12), session_id: SID })
    });
    const data = await res.json();
    if (data.reply) {
      history.push({ role: 'assistant', content: data.reply });
      speak(data.reply);
    } else {
      resetBtn();
    }
  } catch(e) {
    resetBtn();
    setStatus('', '小熊走神了，再试一次吧～');
  }
}

// ── 小熊朗读回复 ──
function speak(text) {
  isSpeaking = true;
  setAv('speaking');
  setStatus('speaking', '小熊正在说话…');
  setBtn('off');

  if (speechSynthesis.speaking) speechSynthesis.cancel();

  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'zh-CN';
  u.rate = 0.88;
  u.pitch = 1.2;

  // 优先选中文女声（更温柔）
  const voices = speechSynthesis.getVoices();
  const zhF = voices.find(v => v.lang.startsWith('zh') && /female|woman|girl/i.test(v.name))
            || voices.find(v => v.lang.startsWith('zh-CN'))
            || voices.find(v => v.lang.startsWith('zh'));
  if (zhF) u.voice = zhF;

  u.onend = u.onerror = () => {
    isSpeaking = false;
    setAv('');
    setBtn('');
    setStatus('', '按住按钮，继续跟小熊说～');
  };

  speechSynthesis.speak(u);
}

// ── 按钮事件 ──
btn.addEventListener('mousedown',  e => { e.preventDefault(); startListen(); });
btn.addEventListener('touchstart', e => { e.preventDefault(); startListen(); }, { passive: false });
btn.addEventListener('mouseup',    () => stopListen());
btn.addEventListener('mouseleave', () => { if (isListening) stopListen(); });
btn.addEventListener('touchend',   e => { e.preventDefault(); stopListen(); }, { passive: false });
btn.addEventListener('touchcancel',() => { if (isListening) stopListen(); });

// ── 预加载语音列表 + 开场白 ──
speechSynthesis.onvoiceschanged = () => {};
window.addEventListener('load', () => {
  speechSynthesis.getVoices();
  setTimeout(() => speak('嗨～我是小熊！今天有没有什么特别好玩的，或者特别烦的事？快跟我说说！'), 900);
});
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/chat_text", methods=["POST"])
def chat_text():
    data = request.json
    user_text = data.get("text", "").strip()
    history   = data.get("history", [])

    if not user_text:
        return jsonify({"reply": None})

    crisis = ["不想活", "想消失", "没有人爱我", "一直难过", "好久不开心", "没人理我"]
    if any(p in user_text for p in crisis):
        return jsonify({"reply": CRISIS_REPLY})

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-12:]

    try:
        client = get_client()
        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=120,
            messages=messages
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        return jsonify({"error": str(e), "reply": None})

    return jsonify({"reply": reply})


if __name__ == "__main__":
    print("\n🐻 魔袋熊纯语音版 v2 启动！")
    print("=" * 40)
    print("本地访问：http://127.0.0.1:5000")
    print("=" * 40 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
