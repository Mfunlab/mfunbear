"""
魔袋熊AI · 云端部署版本 (app.py)
==================================
部署到 Render 后，访问你的域名即可使用。
环境变量：DEEPSEEK_API_KEY
"""

from flask import Flask, request, jsonify, render_template_string
from openai import OpenAI
import os, re

app = Flask(__name__)

def get_client():
    return OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

SYSTEM_PROMPT = """
你是"小熊"，魔袋熊AI情感伙伴，专为6到12岁的孩子设计。

你是孩子每天晚上最期待见到的朋友。你温柔、好奇、有点调皮，说话像一个懂事的大哥哥/大姐姐，
但绝对不像老师或家长。

【睡前复盘三步法】
1. 引导孩子分享今天印象最深的一件事（不问"今天过得怎么样"，太笼统）
2. 帮孩子命名情绪，不评判感受
3. 引导孩子思考"如果可以重来会怎么做"，不给答案

【说话风格】
- 每次回复不超过3句话，简短像聊天
- 多用反问："真的吗？""然后呢？""那你当时怎么想的？"
- 不说大道理，不说"你应该…""你必须…"
- 偶尔用口头禅"小熊我也好奇！"

【安全规则】
- 不询问家庭住址、父母单位、学校位置
- 不涉及暴力、色情、歧视内容
- 发现孩子情绪危机时说："小熊很担心你，这件事要告诉你信任的大人哦。"
"""

CRISIS_PATTERNS = ["不想活", "想消失", "没有人爱我"]
CRISIS_REPLY = "小熊很担心你说的这些话。你现在还好吗？一定要告诉爸爸妈妈或者老师哦，小熊陪着你。"

sessions = {}

HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>魔袋熊小熊 🐻</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, sans-serif;
    background: #FFF8F0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px;
  }
  .header { text-align: center; padding: 20px 0 10px; }
  .bear-avatar { font-size: 64px; display: block; margin-bottom: 8px; }
  .header h1 { font-size: 22px; color: #5D3A1A; font-weight: 600; }
  .header p { font-size: 13px; color: #A0785A; margin-top: 4px; }
  .chat-box {
    width: 100%; max-width: 480px;
    background: white; border-radius: 20px;
    padding: 16px; margin: 16px 0;
    min-height: 400px; max-height: 55vh;
    overflow-y: auto;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    display: flex; flex-direction: column; gap: 12px;
  }
  .msg { display: flex; gap: 8px; align-items: flex-end; }
  .msg.bear { flex-direction: row; }
  .msg.user { flex-direction: row-reverse; }
  .avatar { font-size: 28px; flex-shrink: 0; line-height: 1; margin-bottom: 2px; }
  .bubble {
    max-width: 78%; padding: 10px 14px;
    border-radius: 18px; font-size: 15px; line-height: 1.55;
  }
  .msg.bear .bubble {
    background: #FFF0E0; color: #3D2000;
    border-bottom-left-radius: 4px;
  }
  .msg.user .bubble {
    background: #FF8C42; color: white;
    border-bottom-right-radius: 4px;
  }
  .typing .bubble { color: #A0785A; font-style: italic; }
  .input-area {
    width: 100%; max-width: 480px;
    display: flex; gap: 10px; align-items: flex-end;
  }
  textarea {
    flex: 1; border: 2px solid #FFD4A8;
    border-radius: 16px; padding: 12px 14px;
    font-size: 15px; font-family: inherit;
    resize: none; outline: none;
    background: white; color: #3D2000;
    max-height: 100px; line-height: 1.4;
    transition: border-color 0.2s;
  }
  textarea:focus { border-color: #FF8C42; }
  button {
    width: 48px; height: 48px; border-radius: 50%;
    background: #FF8C42; border: none; cursor: pointer;
    font-size: 22px; display: flex;
    align-items: center; justify-content: center;
    flex-shrink: 0; transition: background 0.15s, transform 0.1s;
  }
  button:hover { background: #E67A30; }
  button:active { transform: scale(0.95); }
  button:disabled { background: #FFD4A8; cursor: not-allowed; }
  .hint { font-size: 12px; color: #C0A080; text-align: center; margin-top: 8px; }
</style>
</head>
<body>
<div class="header">
  <span class="bear-avatar">🐻</span>
  <h1>小熊来啦</h1>
  <p>今天发生什么有趣的事？跟小熊说说吧～</p>
</div>
<div class="chat-box" id="chat">
  <div class="msg bear">
    <span class="avatar">🐻</span>
    <div class="bubble">嗨～小熊在这里！今天有没有让你特别开心或者特别烦的事呀？</div>
  </div>
</div>
<div class="input-area">
  <textarea id="input" placeholder="跟小熊说说今天的事…" rows="1"
    onkeydown="handleKey(event)"
    oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,100)+'px'">
  </textarea>
  <button id="send-btn" onclick="sendMessage()">➤</button>
</div>
<p class="hint">按 Enter 发送 · Shift+Enter 换行</p>
<script>
  const chat = document.getElementById('chat');
  const input = document.getElementById('input');
  const btn = document.getElementById('send-btn');
  const sessionId = 'session_' + Date.now();

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  }
  function addMsg(role, text) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.innerHTML = `<span class="avatar">${role==='bear'?'🐻':'🧒'}</span><div class="bubble">${text}</div>`;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }
  async function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    input.value = ''; input.style.height = 'auto'; btn.disabled = true;
    addMsg('user', text);
    const typing = addMsg('bear', '小熊想想…');
    typing.classList.add('typing');
    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: text, session_id: sessionId})
      });
      const data = await res.json();
      typing.remove();
      addMsg('bear', data.reply);
    } catch(e) {
      typing.remove();
      addMsg('bear', '小熊刚才走神了，再说一次好吗？');
    }
    btn.disabled = false; input.focus();
  }
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    user_msg = data.get("message", "").strip()
    session_id = data.get("session_id", "default")

    for p in CRISIS_PATTERNS:
        if p in user_msg:
            return jsonify({"reply": CRISIS_REPLY})

    if session_id not in sessions:
        sessions[session_id] = []
    history = sessions[session_id]
    history.append({"role": "user", "content": user_msg})

    response = get_client().chat.completions.create(
        model="deepseek-chat",
        max_tokens=200,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history[-10:]
    )
    reply = response.choices[0].message.content
    history.append({"role": "assistant", "content": reply})

    return jsonify({"reply": reply})


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
