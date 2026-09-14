<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

const JOB_ID_KEY = "xiaod.currentJobId";
const JOB_CACHE_KEY = "xiaod.currentJob";

const config = ref({
  has_llm: false,
  has_feishu: false,
  has_langsmith: false,
  has_ytdlp: false,
  has_ffmpeg: false,
  has_whisper: false,
  whisper_model: "small",
  agent: "音视频转录整理助理（小D）",
});
const text = ref("");
const job = ref(null);
const jobs = ref([]);
const notice = ref("");
const submitting = ref(false);
let timer = null;

const steps = [
  "收到链接",
  "取字幕或音频",
  "转写",
  "提纯稿",
  "飞书文档",
];

const currentStep = computed(() => {
  const status = job.value?.status || "";
  const stage = job.value?.stage || "";
  if (!job.value) return -1;
  if (["needs_human", "failed", "stopped"].includes(status)) return -1;
  if (["已收到", "已分类", "开始处理"].includes(stage)) return 0;
  if (["正在找字幕", "正在下载音频", "已取音频", "已取字幕", "已读本地文件"].includes(stage)) return 1;
  if (["正在转写", "已转写"].includes(stage)) return 2;
  if (["正在整理文稿", "已提纯"].includes(stage)) return 3;
  if (stage === "正在创建飞书文档" || status === "done" || status === "needs_feishu") return 4;
  if (status === "running") return 1;
  return 0;
});

const jobProgress = computed(() => {
  const value = Number(job.value?.progress || 0);
  if (Number.isNaN(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
});

function readCachedJob() {
  try {
    const raw = window.localStorage.getItem(JOB_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed?.id ? parsed : null;
  } catch {
    return null;
  }
}

function rememberJob(value) {
  if (!value?.id) return;
  window.localStorage.setItem(JOB_ID_KEY, value.id);
  window.localStorage.setItem(JOB_CACHE_KEY, JSON.stringify(value));
}

function pickJob(list) {
  const running = list.find((item) => item.status === "running");
  if (running) return running;
  const saved = window.localStorage.getItem(JOB_ID_KEY);
  if (saved) {
    const found = list.find((item) => item.id === saved);
    if (found) return found;
  }
  return list[0] || null;
}

function selectJob(item) {
  if (!item) return;
  job.value = item;
  if (item.text) text.value = item.text;
}

function friendlyError(payload) {
  if (typeof payload === "string" && payload.trim()) return payload;
  const detail = payload?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  return "暂时出了问题，请稍后重试。";
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    if (!res.ok) {
      notice.value = "还没连上本机服务。请先运行 uv run xiaod web。";
      return;
    }
    config.value = await res.json();
    notice.value = "";
  } catch {
    notice.value = "还没连上本机服务。请先运行 uv run xiaod web。";
  }
}

async function refreshJob(id) {
  const res = await fetch(`/api/jobs/${id}`);
  if (!res.ok) return;
  job.value = await res.json();
}

async function refreshList() {
  const res = await fetch("/api/jobs");
  if (!res.ok) return;
  jobs.value = await res.json();
  if (job.value?.id) {
    const fresh = jobs.value.find((item) => item.id === job.value.id);
    if (fresh) job.value = fresh;
  }
}

async function submit() {
  notice.value = "";
  submitting.value = true;
  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text.value }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      notice.value = friendlyError(data);
      return;
    }
    selectJob(data);
    await refreshList();
  } catch {
    notice.value = "暂时连不上控制台，请确认 FastAPI 已启动。";
  } finally {
    submitting.value = false;
  }
}

async function stopJob() {
  if (!job.value?.id || job.value.status !== "running") return;
  notice.value = "";
  try {
    const res = await fetch(`/api/jobs/${job.value.id}/stop`, { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      notice.value = friendlyError(data);
      return;
    }
    job.value = data;
    await refreshList();
  } catch {
    notice.value = "暂时连不上控制台，请确认 FastAPI 已启动。";
  }
}

watch(job, (value) => {
  if (value?.id) rememberJob(value);
}, { deep: true });

onMounted(async () => {
  const cached = readCachedJob();
  if (cached) job.value = cached;
  await loadConfig();
  await refreshList();
  const selected = pickJob(jobs.value) || cached;
  if (selected) selectJob(selected);
  timer = window.setInterval(async () => {
    if (job.value?.id && job.value.status === "running") {
      await refreshJob(job.value.id);
    }
    await refreshList();
  }, 1000);
});

onUnmounted(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<template>
  <main class="page">
    <header class="hero">
      <p class="kicker">航海 10096 · 官方小 D</p>
      <h1>音视频转录整理助理</h1>
      <p class="lead">
        当收到一个公开播客或视频链接时，自动下载音频、转录文字、整理成分享式提纯稿，并创建飞书文档交付链接。
      </p>
      <div class="chips">
        <span :class="['chip', config.has_ytdlp ? 'ok' : 'off']">yt-dlp {{ config.has_ytdlp ? "已安装" : "未安装" }}</span>
        <span :class="['chip', config.has_ffmpeg ? 'ok' : 'off']">ffmpeg {{ config.has_ffmpeg ? "已安装" : "未安装" }}</span>
        <span :class="['chip', config.has_whisper ? 'ok' : 'off']">faster-whisper {{ config.has_whisper ? "已安装" : "未安装" }}</span>
        <span :class="['chip', config.has_feishu ? 'ok' : 'off']">飞书 {{ config.has_feishu ? "已接通" : "未配置" }}</span>
        <span :class="['chip', config.has_llm ? 'ok' : 'off']">大模型 {{ config.has_llm ? "已接通" : "规则清洗" }}</span>
        <span :class="['chip', config.has_langsmith ? 'ok' : 'off']">LangSmith {{ config.has_langsmith ? "已接通" : "未配置" }}</span>
        <span class="chip">Whisper {{ config.whisper_model }}</span>
      </div>
    </header>

    <section class="grid">
      <article class="panel">
        <h2>现在就试一次</h2>
        <p class="hint">
          用浏览器能直接打开、不用登录就能播的链接。例如 B 站首页视频、小宇宙节目页、YouTube 公开视频。不要带大会员或付费墙。
        </p>
        <textarea v-model="text" rows="5" placeholder="https://www.bilibili.com/video/BVxxxxxxxx" />
        <div class="actions">
          <button :disabled="submitting" @click="submit">开始整理</button>
          <button
            v-if="job?.status === 'running'"
            class="ghost"
            :disabled="submitting"
            @click="stopJob"
          >
            停止任务
          </button>
          <p v-if="notice" class="notice">{{ notice }}</p>
        </div>
        <ol class="steps">
          <li v-for="(step, index) in steps" :key="step" :class="{ active: currentStep === index, done: currentStep > index }">
            {{ step }}
          </li>
        </ol>
        <div v-if="job" class="result">
          <p class="stage">{{ job.stage }}</p>
          <div
            v-if="job.status === 'running'"
            class="meter"
            role="progressbar"
            :aria-valuemin="0"
            :aria-valuemax="100"
            :aria-valuenow="jobProgress"
            :style="{ '--pct': `${jobProgress}%` }"
          >
            <div class="meter-fill" />
          </div>
          <p v-if="job.status === 'running'" class="hint">{{ jobProgress }}% · {{ job.reply }}</p>
          <p v-else class="reply">{{ job.reply }}</p>
          <p v-if="job.title"><strong>标题</strong> {{ job.title }}</p>
          <p v-if="job.feishu_url">
            <strong>文档</strong>
            <a :href="job.feishu_url" target="_blank" rel="noreferrer">打开飞书文档</a>
          </p>
          <pre v-if="job.article" class="article">{{ job.article }}</pre>
        </div>
      </article>

      <aside class="panel">
        <h2>它是什么</h2>
        <ul class="facts">
          <li>省人工：以前下载、转写、修错词、分段、贴飞书大约 2 小时；现在发链接等结果。</li>
          <li>工具：LangGraph 编排，yt-dlp + ffmpeg 取音频，faster-whisper 转写，飞书创建文档并授权。</li>
          <li>入口：本页控制台，或飞书 Bot 私聊发链接。</li>
        </ul>
        <h3>7 条验收</h3>
        <ol class="checks">
          <li>能接收公开播客 / 视频链接</li>
          <li>能下载或拿到音频 / 字幕</li>
          <li>能完成转写</li>
          <li>生成分享式提纯稿，不是摘要</li>
          <li>能创建飞书文档</li>
          <li>能把权限授给本人</li>
          <li>交付可打开、目录正常的链接</li>
        </ol>
        <h3>公开链接从哪来</h3>
        <ul class="facts">
          <li>B 站：打开 www.bilibili.com，点进一个不用登录就能播的视频，复制地址栏。</li>
          <li>小宇宙：打开 www.xiaoyuzhoufm.com，点进一期节目，复制分享链接。</li>
          <li>YouTube：打开一个没设私密/会员的视频，复制地址栏。</li>
        </ul>
        <h3>本期不做</h3>
        <p class="hint">不做小红书 / 抖音 / 公众号 / 视频号采集，不处理飞书妙记，不发布原片，不绕过登录墙。</p>
      </aside>
    </section>

    <section class="panel history" v-if="jobs.length">
      <h2>最近任务</h2>
      <ul>
        <li v-for="item in jobs" :key="item.id" @click="selectJob(item)">
          <span>{{ item.stage }}{{ item.status === "running" ? ` · ${item.progress || 0}%` : "" }}</span>
          <em>{{ item.text }}</em>
        </li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 20px 80px;
}

.hero h1,
.panel h2,
.panel h3 {
  margin: 0 0 12px;
}

.kicker {
  color: var(--accent);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 12px;
}

.lead,
.hint,
.reply,
.facts,
.checks {
  color: var(--muted);
  line-height: 1.7;
}

.chips,
.actions,
.steps {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip,
button,
.stage {
  border-radius: 999px;
  padding: 6px 12px;
}

.chip {
  background: var(--chip);
  color: var(--muted);
  font-size: 13px;
}

.chip.ok {
  color: var(--ok);
}

.grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 18px;
  margin-top: 28px;
}

.panel,
.history {
  background: color-mix(in srgb, var(--panel) 92%, transparent);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 22px;
}

textarea {
  width: 100%;
  margin: 12px 0;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: #10161d;
  color: var(--text);
  resize: vertical;
}

button {
  border: 0;
  background: var(--accent);
  color: white;
  cursor: pointer;
}

button:disabled {
  opacity: 0.6;
  cursor: wait;
}

button.ghost {
  background: transparent;
  color: var(--text);
  border: 1px solid var(--line);
}

.notice {
  color: var(--warn);
  margin: 8px 0 0;
}

.steps {
  list-style: none;
  padding: 0;
  margin: 18px 0 0;
}

.steps li {
  padding: 6px 10px;
  border-radius: 999px;
  background: var(--chip);
  color: var(--muted);
}

.steps li.active {
  background: #20406c;
  color: var(--text);
}

.steps li.done {
  color: var(--ok);
}

.result {
  margin-top: 18px;
}

.meter {
  margin: 12px 0 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--chip);
  overflow: hidden;
}

.meter-fill {
  height: 100%;
  width: var(--pct, 0%);
  background: var(--accent);
  transition: width 0.4s ease;
}

.stage {
  display: inline-block;
  background: #20406c;
}

.article {
  white-space: pre-wrap;
  background: #10161d;
  border-radius: 12px;
  padding: 12px;
  max-height: 320px;
  overflow: auto;
}

.history ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.history li {
  display: grid;
  gap: 4px;
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
  cursor: pointer;
}

.history em {
  color: var(--muted);
  font-style: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 860px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
