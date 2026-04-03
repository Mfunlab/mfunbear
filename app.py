"""
魔袋熊AI · 纯语音版本 v3
==========================
- 按住橙色大按钮说话，松开自动识别发送（浏览器Web Speech API）
- 阿里云TTS语音合成回复（自然童声）
- 无文字旁白，极简界面
- 小熊完整人格：来自神秘森林王国的8岁男孩
"""

from flask import Flask, request, jsonify, render_template_string, Response
from openai import OpenAI
import os, re, json, requests, base64

app = Flask(__name__)

# ── DeepSeek 对话 ──
def get_client():
    return OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

# ── 阿里云 TTS ──
ALI_AK_ID     = os.environ.get("ALI_AK_ID", "")
ALI_AK_SECRET = os.environ.get("ALI_AK_SECRET", "")
ALI_APPKEY    = os.environ.get("ALI_APPKEY", "")

def ali_tts(text: str) -> bytes | None:
    """
    调用阿里云 REST TTS 接口，返回 mp3 音频字节。
    音色：aixia（温柔女声）/ aijia（儿童女声）/ aiqi（清新女声）
    更多音色：https://help.aliyun.com/zh/isi/developer-reference/voice-list
    """
    import hmac, hashlib, uuid, time
    from urllib.parse import quote

    voice    = "aijia"   # 儿童女声，最适合小熊
    format_  = "mp3"
    sample   = "16000"
    speech   = quote(text)
    task_id  = str(uuid.uuid4()).replace("-", "")
    ts       = str(int(time.time()))

    # 构造签名
    str_to_sign = ALI_AK_ID + ts + task_id + ALI_APPKEY
    sig = hmac.new(
        ALI_AK_SECRET.encode("utf-8"),
        str_to_sign.encode("utf-8"),
        hashlib.sha1
    ).hexdigest().upper()

    url = (
        "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts"
        f"?appkey={ALI_APPKEY}"
        f"&token="       # REST模式部分场景可用AK直签，下面用token方式兜底
        f"&text={speech}"
        f"&format={format_}"
        f"&sample_rate={sample}"
        f"&voice={voice}"
        f"&speech_rate=-200"   # 语速稍慢，更适合孩子
        f"&pitch_rate=100"
    )

    # 阿里云 NLS REST 接口需要先获取 token
    token = get_ali_token()
    if not token:
        return None

    url = (
        "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts"
        f"?appkey={ALI_APPKEY}"
        f"&token={token}"
        f"&text={quote(text)}"
        f"&format={format_}"
        f"&sample_rate={sample}"
        f"&voice={voice}"
        f"&speech_rate=-200"
        f"&pitch_rate=100"
    )

    try:
        resp = requests.get(url, timeout=10)
        if resp.headers.get("Content-Type", "").startswith("audio"):
            return resp.content
        else:
            print("TTS error:", resp.text[:200])
            return None
    except Exception as e:
        print("TTS request error:", e)
        return None


_ali_token_cache = {"token": "", "expire": 0}

def get_ali_token() -> str:
    import time, hmac, hashlib, uuid
    from urllib.parse import quote

    if _ali_token_cache["token"] and time.time() < _ali_token_cache["expire"] - 60:
        return _ali_token_cache["token"]

    # 阿里云 CreateToken 接口
    import datetime
    dt = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    nonce = str(uuid.uuid4())

    params = {
        "AccessKeyId": ALI_AK_ID,
        "Action": "CreateToken",
        "Format": "JSON",
        "RegionId": "cn-shanghai",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": nonce,
        "SignatureVersion": "1.0",
        "Timestamp": dt,
        "Version": "2019-02-28",
    }

    sorted_params = "&".join(
        f"{quote(k, safe='')}={quote(str(v), safe='')}"
        for k, v in sorted(params.items())
    )
    str_to_sign = "GET&%2F&" + quote(sorted_params, safe="")
    sig = base64.b64encode(
        hmac.new((ALI_AK_SECRET + "&").encode(), str_to_sign.encode(), hashlib.sha1).digest()
    ).decode()

    params["Signature"] = sig
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())

    try:
        resp = requests.get(
            f"https://nls-meta.cn-shanghai.aliyuncs.com/?{query}", timeout=8
        )
        data = resp.json()
        token = data.get("Token", {}).get("Id", "")
        expire = data.get("Token", {}).get("ExpireTime", 0)
        if token:
            _ali_token_cache["token"] = token
            _ali_token_cache["expire"] = expire
            return token
        print("Token error:", data)
        return ""
    except Exception as e:
        print("Token request error:", e)
        return ""


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
- 回复语言流畅自然，避免括号、特殊符号，适合直接朗读

【核心任务：睡前情感复盘】
引导孩子聊今天发生的事 → 帮孩子说出感受 → 一起想想"如果重来会怎样"
不要急着推进，跟着孩子的节奏走。

【安全规则】
- 不询问家庭住址、父母单位、学校具体位置
- 不涉及暴力、色情、歧视内容
- 发现孩子情绪危机时温柔说："小熊很担心你，这件事我们要告诉你信任的大人哦"
"""

CRISIS_PATTERNS = ["不想活", "想消失", "没有人爱我", "一直难过", "好久不开心", "没人理我"]
CRISIS_REPLY   = "小熊很担心你说的这些。你现在还好吗？这件事我们要告诉你信任的大人哦，可以是爸爸妈妈或者老师，小熊陪着你。"
OPENING_LINE   = "嗨，我是小熊！今天有没有什么特别好玩的，或者特别烦的事，快跟我说说！"

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
    padding: 32px 24px; width: 100%; max-width: 420px;
  }
  .avatar-wrap { position: relative; margin-bottom: 40px; }
  .avatar { font-size: 108px; line-height: 1; display: block; transition: transform 0.3s; }
  .avatar-wrap.speaking .avatar { animation: bearBob 0.55s ease-in-out infinite alternate; }
  @keyframes bearBob {
    from { transform: translateY(0) scale(1); }
    to   { transform: translateY(-8px) scale(1.05); }
  }
  .speak-ring {
    position: absolute; bottom: -10px; left: 50%;
    transform: translateX(-50%);
    width: 28px; height: 28px; border-radius: 50%;
    background: #5BAE6A; opacity: 0; transition: opacity 0.25s;
  }
  .avatar-wrap.speaking .speak-ring {
    opacity: 1; animation: ringPulse 0.7s ease-in-out infinite;
  }
  @keyframes ringPulse {
    0%,100% { transform: translateX(-50%) scale(1); opacity: 0.9; }
    50%      { transform: translateX(-50%) scale(1.7); opacity: 0.15; }
  }
  .viz {
    display: flex; gap: 5px; align-items: flex-end;
    height: 32px; margin-bottom: 44px;
    opacity: 0; transition: opacity 0.25s;
  }
  .viz.on { opacity: 1; }
  .v-bar { width: 5px; border-radius: 3px; background: #FF8C42; height: 5px; }
  .viz.on .v-bar:nth-child(1) { animation: vb 0.55s ease-in-out infinite 0.00s; }
  .viz.on .v-bar:nth-child(2) { animation: vb 0.55s ease-in-out infinite 0.10s; }
  .viz.on .v-bar:nth-child(3) { animation: vb 0.55s ease-in-out infinite 0.20s; }
  .viz.on .v-bar:nth-child(4) { animation: vb 0.55s ease-in-out infinite 0.10s; }
  .viz.on .v-bar:nth-child(5) { animation: vb 0.55s ease-in-out infinite 0.00s; }
  @keyframes vb { 0%,100% { height: 5px; } 50% { height: 26px; } }
  .btn-area { position: relative; width: 200px; height: 200px; cursor: pointer; }
  .glow {
    position: absolute; inset: -24px; border-radius: 50%;
    background: radial-gradient(circle, rgba(240,140,50,0.22) 0%, rgba(240,140,50,0) 68%);
    animation: breathe 3.2s ease-in-out infinite; pointer-events: none;
  }
  @keyframes breathe {
    0%,100% { transform: scale(0.90); opacity: 0.55; }
    50%      { transform: scale(1.10); opacity: 1.00; }
  }
  .outer {
    position: absolute; inset: 0; border-radius: 50%;
    background: #F09030;
    transition: transform 0.12s ease, background 0.12s ease;
    box-shadow: 0 6px 24px rgba(240,130,40,0.30);
  }
  .inner {
    position: absolute; top: 50%; left: 50%;
    width: 58px; height: 58px; border-radius: 50%;
    background: white; transform: translate(-50%, -50%);
    transition: width 0.12s ease, height 0.12s ease;
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
  }
  .btn-area.pressed .outer  { transform: scale(0.93); background: #D07010; }
  .btn-area.pressed .inner  { width: 40px; height: 40px; }
  .btn-area.recording .outer {
    background: #D05010;
    animation: recPulse 0.45s ease-in-out infinite alternate;
  }
  @keyframes recPulse { from { transform: scale(0.93); } to { transform: scale(0.97); } }
  .btn-area.off .outer { background: #D0B898; box-shadow: none; }
  .btn-area.off .glow  { animation: none; opacity: 0.2; }
  .hint { margin-top: 32px; font-size: 13px; color: #C8A880; text-align: center; }
</style>
</head>
<body>

<div id="welcome" style="
  min-height:100vh; min-height:100dvh;
  display:flex; flex-direction:column;
  align-items:center; justify-content:center;
  background:#FFF6EC; padding:40px 24px; text-align:center;">
  <span style="font-size:100px;line-height:1;margin-bottom:24px;">🐻</span>
  <h1 style="font-size:24px;font-weight:600;color:#5D3A1A;margin-bottom:8px;">小熊来啦</h1>
  <p style="font-size:15px;color:#C0A07A;margin-bottom:48px;line-height:1.7;">
    来自神秘森林王国的好朋友<br>想听你说说今天的故事～
  </p>
  <div id="enter-btn" style="
    width:160px;height:160px;border-radius:50%;
    background:#F09030;cursor:pointer;
    display:flex;align-items:center;justify-content:center;
    box-shadow:0 6px 24px rgba(240,130,40,0.35);
    animation:breathe 3s ease-in-out infinite;">
    <div style="width:48px;height:48px;border-radius:50%;background:white;"></div>
  </div>
  <p style="margin-top:24px;font-size:13px;color:#C8A880;">点击进入，和小熊说话</p>
</div>

<div id="main" class="scene" style="display:none;">
  <div class="avatar-wrap" id="av">
    <span class="avatar">🐻</span>
    <div class="speak-ring"></div>
  </div>
  <div class="viz" id="viz">
    <div class="v-bar"></div><div class="v-bar"></div><div class="v-bar"></div>
    <div class="v-bar"></div><div class="v-bar"></div>
  </div>
  <div class="btn-area" id="btn">
    <div class="glow"></div>
    <div class="outer"></div>
    <div class="inner"></div>
  </div>
  <p class="hint">按住说话 &nbsp;·&nbsp; 松开发送</p>
</div>

<script>
const SID  = 's' + Date.now();
const btn  = document.getElementById('btn');
const av   = document.getElementById('av');
const viz  = document.getElementById('viz');

let recognition = null;
let isListening = false;
let isSpeaking  = false;
let currentAudio = null;
let history = [];

function setBtn(cls) { btn.className = 'btn-area' + (cls ? ' ' + cls : ''); }
function setAv(cls)  { av.className  = 'avatar-wrap' + (cls ? ' ' + cls : ''); }

function initRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  const r = new SR();
  r.lang = 'zh-CN';
  r.continuous = false;
  r.interimResults = false;
  r.maxAlternatives = 1;
  r.onresult = e => {
    const text = e.results[0][0].transcript.trim();
    if (text) sendText(text);
    else resetBtn();
  };
  r.onerror = () => resetBtn();
  r.onend = () => {
    if (isListening) { isListening = false; viz.classList.remove('on'); }
  };
  return r;
}

function resetBtn() {
  isListening = false;
  viz.classList.remove('on');
  setBtn(''); setAv('');
}

function startListen() {
  if (isSpeaking) return;
  recognition = recognition || initRecognition();
  if (!recognition) return;
  try {
    recognition.start();
    isListening = true;
    setBtn('recording');
    viz.classList.add('on');
  } catch(e) {}
}

function stopListen() {
  if (!isListening) return;
  setBtn('off');
  viz.classList.remove('on');
  try { recognition.stop(); } catch(e) {}
}

async function sendText(text) {
  history.push({ role: 'user', content: text });
  setBtn('off');

  const crisis = ['不想活','想消失','没有人爱我','一直难过','好久不开心'];
  if (crisis.some(p => text.includes(p))) {
    await speakAli('小熊很担心你说的这些。你现在还好吗？这件事我们要告诉你信任的大人哦，可以是爸爸妈妈或者老师，小熊陪着你。');
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
      await speakAli(data.reply);
    } else { resetBtn(); }
  } catch(e) { resetBtn(); }
}

async function speakAli(text) {
  isSpeaking = true;
  setAv('speaking');
  setBtn('off');

  try {
    const res = await fetch('/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    if (!res.ok) throw new Error('TTS failed');

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);

    if (currentAudio) { currentAudio.pause(); currentAudio = null; }

    const audio = new Audio(url);
    currentAudio = audio;

    audio.onended = audio.onerror = () => {
      isSpeaking = false;
      setAv(''); setBtn('');
      URL.revokeObjectURL(url);
      currentAudio = null;
    };

    await audio.play();
  } catch(e) {
    console.warn('Ali TTS failed, fallback to browser TTS:', e);
    speakFallback(text);
  }
}

function speakFallback(text) {
  if (speechSynthesis.speaking) speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'zh-CN'; u.rate = 0.88; u.pitch = 1.2;
  const voices = speechSynthesis.getVoices();
  const zh = voices.find(v => v.lang.startsWith('zh-CN')) || voices.find(v => v.lang.startsWith('zh'));
  if (zh) u.voice = zh;
  u.onend = u.onerror = () => { isSpeaking = false; setAv(''); setBtn(''); };
  speechSynthesis.speak(u);
}

btn.addEventListener('mousedown',   e => { e.preventDefault(); startListen(); });
btn.addEventListener('touchstart',  e => { e.preventDefault(); startListen(); }, { passive: false });
btn.addEventListener('mouseup',     () => stopListen());
btn.addEventListener('mouseleave',  () => { if (isListening) stopListen(); });
btn.addEventListener('touchend',    e => { e.preventDefault(); stopListen(); }, { passive: false });
btn.addEventListener('touchcancel', () => { if (isListening) stopListen(); });

function enterMain() {
  document.getElementById('welcome').style.display = 'none';
  document.getElementById('main').style.display = 'flex';
  setTimeout(() => speakAli('嗨，我是小熊！今天有没有什么特别好玩的，或者特别烦的事，快跟我说说！'), 300);
}

document.getElementById('enter-btn').addEventListener('click',    enterMain);
document.getElementById('enter-btn').addEventListener('touchend', e => { e.preventDefault(); enterMain(); });

speechSynthesis.onvoiceschanged = () => {};
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/tts", methods=["POST"])
def tts():
    """服务端调用阿里云TTS，返回mp3音频流给前端"""
    data = request.json
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "no text"}), 400

    audio = ali_tts(text)
    if audio:
        return Response(audio, mimetype="audio/mpeg")
    else:
        return jsonify({"error": "TTS failed"}), 500


@app.route("/chat_text", methods=["POST"])
def chat_text():
    data = request.json
    user_text = data.get("text", "").strip()
    history   = data.get("history", [])

    if not user_text:
        return jsonify({"reply": None})

    if any(p in user_text for p in CRISIS_PATTERNS):
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
        # 清理不适合朗读的符号
        reply = re.sub(r'[「」【】《》*#]', '', reply)
    except Exception as e:
        return jsonify({"error": str(e), "reply": None})

    return jsonify({"reply": reply})


if __name__ == "__main__":
    print("\n🐻 魔袋熊纯语音版 v3 · 阿里云TTS")
    print("=" * 40)
    print("本地访问：http://127.0.0.1:5000")
    print("=" * 40 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)

