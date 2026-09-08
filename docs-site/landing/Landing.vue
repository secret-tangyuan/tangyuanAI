<script setup>
import { onMounted, onUnmounted, ref } from 'vue'
import { useData } from 'vitepress'
import { initLanding } from './js/main.js'
import './css/style.css'

const rootEl = ref(null)
let cleanup = null

// 复用 VitePress 的 isDark（VueUse useDark）：切换会同步 localStorage + <html>.dark
const { isDark } = useData()
const toggleTheme = () => {
  isDark.value = !isDark.value
}

onMounted(() => {
  cleanup = initLanding(rootEl.value)
})
onUnmounted(() => {
  if (cleanup) cleanup()
  cleanup = null
})
</script>

<template>
<div class="landing" ref="rootEl">

  <!-- ══════════ Navigation ══════════ -->
  <header class="nav" id="nav">
    <div class="nav__inner">
      <a class="brand" href="#top" aria-label="tangyuanAI 首页">
        <span class="brand__mark" aria-hidden="true"></span>
        <span class="brand__word">tangyuan<span>AI</span></span>
      </a>
      <nav class="nav__links" aria-label="主导航">
        <a href="/docs/">文档</a>
        <a href="#problem">问题</a>
        <a href="#pillars">特性</a>
        <a href="#architecture">架构</a>
        <a href="#quickstart">快速开始</a>
        <a href="#compare">对比</a>
      </nav>
      <div class="nav__cta">
        <button class="theme-toggle" type="button" aria-label="切换深浅色" title="切换深浅色" @click="toggleTheme">
          <svg class="ico theme-toggle__sun" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>
          <svg class="ico theme-toggle__moon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
        </button>
        <a class="btn btn--ghost" href="/docs/">文档</a>
        <a class="btn btn--dark" href="https://github.com/secret-tangyuan/tangyuanAI" target="_blank" rel="noopener">
          <svg class="ico" viewBox="0 0 16 16" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z"/></svg>
          Star
          <span class="badge-star" id="starCount">★</span>
        </a>
      </div>
    </div>
  </header>

  <main id="top">

    <!-- ══════════ Hero ══════════ -->
    <section class="hero">
      <div class="hero__inner">
        <div class="hero__main">
          <p class="kicker reveal">TANGYUANAI · QUICK API · SIMPLE AGENTS</p>
          <h1 class="hero__title reveal">快速对接 LLM API<br>
            <mark class="hl">简洁构建 Agent</mark>
          </h1>
          <p class="hero__sub reveal">一个轻量、模块化的 Agent 框架。<br class="br-desktop">
            一个 <code>Agent</code> 类、一个 <code>protocol</code> 字段——快速对接 OpenAI / Anthropic / 自家网关，几行代码构建 Agent。</p>
          <div class="hero__actions reveal">
            <button class="btn btn--primary btn--lg" data-copy="uv add tangyuanAI">
              uv add tangyuanAI
            </button>
            <a class="btn btn--default btn--lg" href="/docs/">
              阅读文档
              <svg class="ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
            </a>
          </div>
          <ul class="hero__meta reveal">
            <li>v0.1.0</li>
            <li>Python 3.10+</li>
            <li>Apache-2.0</li>
            <li>PyPI · <span class="mono-mint">tangyuanAI</span></li>
          </ul>
        </div>

        <div class="hero__code reveal">
          <div class="code-panel">
            <div class="code-panel__bar">
              <span class="code-panel__title">weather_agent.py</span>
              <button class="code-panel__copy" data-copy="#herocode" aria-label="复制代码">
                <svg class="ico" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="0"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>
                复制
              </button>
            </div>
            <pre class="code-panel__body" id="herocode" v-pre><code><span class="c"># 定义 Agent —— 一个类，一个 protocol 字段</span>
<span class="k">import</span> tangyuanAI

<span class="k">@</span>tangyuanAI.template_agent(
    <span class="s">"weather"</span>, description=<span class="s">"天气查询助手"</span>)
<span class="k">class</span> <span class="t">WeatherAgent</span>(tangyuanAI.Agent):
    prompt      = <span class="s">"你是天气助手"</span>
    protocol    = <span class="s">"openai"</span>   <span class="c"># 一行切协议</span>
    model_name  = <span class="s">"gpt-5"</span>

tangyuanAI.activate_template(<span class="s">"weather"</span>)
tangyuanAI.agent_list[<span class="s">"weather"</span>].conversation(
    <span class="s">"北京今天天气？"</span>)
<span class="c"># → "北京今天晴，温度 25°C"</span></code></pre>
          </div>
        </div>
      </div>
    </section>

    <!-- ══════════ Provider strip ══════════ -->
    <section class="strip" aria-label="支持的协议与供应商">
      <div class="strip__inner">
        <span class="strip__label mono">对接协议</span>
        <div class="strip__items">
          <span class="chip">OpenAI · Chat Completions</span>
          <span class="chip">OpenAI · Responses</span>
          <span class="chip">Anthropic · Messages</span>
          <span class="chip chip--primary">你的网关</span>
          <span class="chip chip--dash">register_protocol()</span>
        </div>
      </div>
    </section>

    <!-- ══════════ Problem ══════════ -->
    <section class="section" id="problem">
      <div class="section__head reveal">
        <p class="kicker">THE PROBLEM</p>
        <h2>每家 LLM API 都是<br><strong class="hl">另一种方言</strong></h2>
      </div>
      <p class="section__lead reveal">OpenAI 要 <code>role="tool"</code> 块；Anthropic 要 <code>tool_use_id</code> 回声；Responses 要 <code>input</code> 列表；你公司机房的网关，又讲另一种话。<strong>写死一个 SDK，就把自己锁死在一个 provider。</strong></p>

      <div class="grid grid--2">
        <figure class="card dialect reveal">
          <figcaption class="card__bar">
            <span class="dialect__name">OpenAI</span>
            <span class="dialect__tag mono">Chat Completions</span>
          </figcaption>
          <pre class="card__code" v-pre><code><span class="c"># 原生 function-calling</span>
<span class="k">messages</span>.<span class="k">append</span>(<span class="p">{</span>
    <span class="s">"role"</span>: <span class="s">"tool"</span>,
    <span class="s">"tool_call_id"</span>: call.<span class="k">id</span>,
    <span class="s">"content"</span>: result
<span class="p">}</span>)</code></pre>
        </figure>

        <figure class="card dialect reveal">
          <figcaption class="card__bar">
            <span class="dialect__name">Anthropic</span>
            <span class="dialect__tag mono">Messages API</span>
          </figcaption>
          <pre class="card__code" v-pre><code><span class="c"># tool_result 内容块 + 回声</span>
<span class="p">{</span>
    <span class="s">"type"</span>: <span class="s">"tool_result"</span>,
    <span class="s">"tool_use_id"</span>: block.<span class="k">id</span>,  <span class="c"># 必须回</span>
    <span class="s">"content"</span>: result,
    <span class="s">"is_error"</span>: <span class="k">False</span>
<span class="p">}</span></code></pre>
        </figure>

        <figure class="card dialect reveal">
          <figcaption class="card__bar">
            <span class="dialect__name">OpenAI</span>
            <span class="dialect__tag mono">/v1/responses</span>
          </figcaption>
          <pre class="card__code" v-pre><code><span class="c"># typed items 进 input 列表</span>
<span class="s">"input"</span>: <span class="p">[</span>
    <span class="p">{</span><span class="s">"type"</span>: <span class="s">"message"</span>, <span class="s">"role"</span>: <span class="s">"user"</span>,
     <span class="s">"content"</span>: <span class="p">[</span><span class="p">{</span><span class="s">"type"</span>: <span class="s">"input_text"</span>,
        <span class="s">"text"</span>: msg<span class="p">}</span><span class="p">]</span><span class="p">}</span>
<span class="p">]</span></code></pre>
        </figure>

        <figure class="card card--primary dialect reveal">
          <figcaption class="card__bar">
            <span class="dialect__name">你的网关</span>
            <span class="dialect__tag mono">内部协议</span>
          </figcaption>
          <pre class="card__code" v-pre><code><span class="c"># 只有你们自己人知道…</span>
<span class="s">"wrapper"</span>: <span class="p">{</span><span class="s">"inner"</span>: <span class="s">"payload"</span><span class="p">}</span>,
<span class="s">"route"</span>: <span class="s">"/api/gw/v3"</span>,
<span class="s">"vendor"</span>: <span class="s">"weird-warehouse"</span>
<span class="c"># 三个 URL 都要改</span></code></pre>
        </figure>
      </div>

      <p class="punch reveal">如果每对接一个 API 都要重写一遍循环，<br>那不是在做 Agent，是在做集成。</p>
    </section>

    <!-- ══════════ Pillars ══════════ -->
    <section class="section section--alt" id="pillars">
      <div class="section__head reveal">
        <p class="kicker">THE PITCH</p>
        <h2>三个支柱，撑起<strong class="hl">简洁 Agent 构建</strong></h2>
        <p class="section__lead">tangyuanAI 把 LLM API 的差异收拢到一个地方。目的不是功能堆叠——而是让你<em>几分钟对接新 API，几行代码构建 Agent。</em></p>
      </div>

      <div class="grid grid--3">
        <article class="card pillar reveal">
          <span class="pillar__num mono">01</span>
          <h3>一个 Agent 类<br>一个 <code>protocol</code> 字段</h3>
          <p>注册表把 protocol 字符串映射到 transport 实现。加新 provider = 一个 transport 类 + 一次 <code>register_protocol(...)</code>。</p>
          <pre class="pillar__code" v-pre><code><span class="k">class</span> <span class="t">Reviewer</span>(<span class="t">Agent</span>):
    <span class="k">protocol</span> = <span class="s">"anthropic"</span>  <span class="c"># 一行切</span></code></pre>
        </article>

        <article class="card pillar reveal">
          <span class="pillar__num mono">02</span>
          <h3>工具与协议无关<br>一次编写，处处可调</h3>
          <p>原生 function-calling 也好，stream 里塞 XML 也好，框架都桥接好。ACL、Pydantic 校验、单调用超时全部内置。</p>
          <pre class="pillar__code" v-pre><code><span class="k">def</span> <span class="t">get_weather</span>(city: <span class="k">str</span>) <span class="p">-&gt;</span> <span class="k">str</span>:</code></pre>
        </article>

        <article class="card pillar reveal">
          <span class="pillar__num mono">03</span>
          <h3>Agent 模板池<br><code>装饰器即配置</code></h3>
          <p>继承 Agent + 类属性 = 一种 Agent。<code>@template_agent</code> 注册到池，<code>activate_template("name")</code> 一行激活。同一份代码，换 provider = 改一个字段。</p>
          <pre class="pillar__code" v-pre><code><span class="k">@</span>tangyuanAI.template_agent(<span class="s">"writer"</span>,
    description=<span class="s">"写作助手"</span>)
<span class="k">class</span> <span class="t">Writer</span>(tangyuanAI.BaseAgent):
    <span class="k">protocol</span>   = <span class="s">"openai"</span>
    model_name  = <span class="s">"gpt-5"</span></code></pre>
        </article>
      </div>
    </section>

    <!-- ══════════ Architecture ══════════ -->
    <section class="section" id="architecture">
      <div class="section__head reveal">
        <p class="kicker">ARCHITECTURE</p>
        <h2>你写 Agent。<strong class="hl">协议在 transport 后面变</strong></h2>
      </div>

      <div class="arch">
        <div class="arch__row reveal">
          <div class="arch__layer">
            <span class="arch__idx mono">L1</span>
            <span class="arch__name mono">agent_list</span>
            <span class="arch__meta">你的应用 · 一个注册表</span>
          </div>
        </div>
        <div class="arch__row reveal">
          <div class="arch__layer arch__layer--core">
            <span class="arch__idx mono">L2</span>
            <span class="arch__name">Agent</span>
            <span class="arch__meta mono">prompt · tools · hooks · memory</span>
            <span class="arch__tick" aria-hidden="true">✓</span>
          </div>
        </div>
        <div class="arch__row reveal">
          <div class="arch__layer arch__layer--transport">
            <span class="arch__idx mono">L3</span>
            <span class="arch__name mono">LLMTransport</span>
            <span class="arch__meta mono">HttpxOpenAI · HttpxAnthropic · Responses · register_protocol()</span>
          </div>
        </div>
        <div class="arch__row reveal">
          <div class="arch__providers">
            <span class="prov">OpenAI</span>
            <span class="prov">Responses</span>
            <span class="prov">Anthropic</span>
            <span class="prov prov--primary">你的网关</span>
            <span class="prov prov--dash">你明天的网关</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ══════════ Quickstart ══════════ -->
    <section class="section section--alt" id="quickstart">
      <div class="section__head reveal">
        <p class="kicker">QUICKSTART</p>
        <h2>60 秒，从零到<strong class="hl">第一个 Agent</strong></h2>
      </div>

      <div class="terminal reveal" id="terminal">
        <div class="terminal__bar">
          <span class="traffic" aria-hidden="true"><i></i><i></i><i></i></span>
          <span class="terminal__title mono">weather_agent.py</span>
          <button class="terminal__copy" data-copy="#terminal code">
            <svg class="ico" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="0"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>
            复制
          </button>
        </div>
        <pre class="terminal__body" v-pre><code><span class="c"># 1. 装包并设置密钥</span>
$ uv add tangyuanAI
$ export API_KEY="sk-…"

<span class="c"># 2. 注册工具 —— 一个函数 = 一份 JSON Schema</span>
<span class="k">@</span>tangyuanAI.tool_registry.register_tool(
    description=<span class="s">"uv add查询某城市天气（演示用返回假数据）"</span>,
    parameters=<span class="p">{</span><span class="s">"type"</span>: <span class="s">"object"</span>,
        <span class="s">"properties"</span>: <span class="p">{</span><span class="s">"city"</span>: <span class="p">{</span><span class="s">"type"</span>: <span class="s">"string"</span><span class="p">}</span><span class="p">}</span>,
        <span class="s">"required"</span>: <span class="p">[</span><span class="s">"city"</span><span class="p">]</span><span class="p">}</span>,
)
<span class="k">def</span> <span class="t">get_weather</span>(city: <span class="k">str</span>) <span class="p">-&gt;</span> <span class="k">str</span>:
    <span class="k">return</span> <span class="s">f"</span><span class="p">{</span>city<span class="p">}</span><span class="s"> 今天晴，温度 25°C"</span>

<span class="c"># 3. 定义 Agent</span>
<span class="k">@</span>tangyuanAI.template_agent(
    <span class="s">"weather"</span>, uuid=<span class="s">"weather-uuid-1"</span>,
    description=<span class="s">"天气查询助手"</span>,
)
<span class="k">class</span> <span class="t">WeatherAgent</span>(tangyuanAI.BaseAgent):
    prompt = <span class="s">"你是天气助手，用 get_weather 工具回答问题"</span>
    api_provider = <span class="s">"https://api.openai.com/v1/chat/completions"</span>
    model_name   = <span class="s">"gpt-5"</span>
    api_key      = <span class="s">"sk-…"</span>

<span class="c"># 4. 运行</span>
<span class="k">if</span> __name__ == <span class="s">"__main__"</span>:
    tangyuanAI.activate_template(<span class="s">"weather"</span>)
    tangyuanAI.agent_list[<span class="s">"weather"</span>].conversation(
        <span class="s">"北京今天天气怎么样？"</span>)
    <span class="c"># → "北京今天晴，温度 25°C"</span></code></pre>
      </div>
      <p class="terminal__foot reveal">切协议？把 <code>protocol</code> 改成 <code>"anthropic"</code> 就完了。<em>同一个类。</em></p>
    </section>

    <!-- ══════════ Compare ══════════ -->
    <section class="section" id="compare">
      <div class="section__head reveal">
        <p class="kicker">API INTEGRATION</p>
        <h2>从零接一个 LLM API？<br><strong class="hl">1 行</strong>就够了</h2>
      </div>

      <div class="compare">
        <div class="compare__side compare__side--old reveal">
          <div class="compare__label">
            <span class="mono">FROM SCRATCH · LLM SDK</span>
            <span class="mono">100+ 行</span>
          </div>
          <pre class="compare__code" v-pre><code><span class="c"># 自己接一个新 LLM API</span>
client = httpx.AsyncClient(headers=<span class="p">{</span>
    <span class="s">"Authorization"</span>: <span class="s">f"Bearer </span><span class="p">{</span>key<span class="p">}</span><span class="s">"</span><span class="p">}</span>)
<span class="k">async def</span> <span class="t">chat</span>(messages):
    payload = <span class="p">{</span><span class="s">"model"</span>: MODEL,
        <span class="s">"messages"</span>: messages<span class="p">}</span>
    <span class="k">async for</span> chunk <span class="k">in</span> client.stream(
        <span class="s">"POST"</span>, url, json=payload):
        <span class="k">if</span> chunk[<span class="s">"type"</span>] == <span class="s">"tool_call"</span>:
            result = <span class="k">await</span> run_tool(
                chunk[<span class="s">"name"</span>], chunk[<span class="s">"input"</span>])
            messages.append(
                tool_msg(chunk[<span class="s">"id"</span>], result))
        <span class="k">elif</span> chunk[<span class="s">"type"</span>] == <span class="s">"error"</span>:
            <span class="k">await</span> backoff_retry()
<span class="c"># 鉴权 / 流式 / 工具桥接 / 重试…</span></code></pre>
          <p class="compare__foot">100+ 行，且只连通一家。</p>
        </div>

        <div class="compare__divider" aria-hidden="true">
          <span class="compare__vs">1&nbsp;=&nbsp;100</span>
        </div>

        <div class="compare__side compare__side--new reveal">
          <div class="compare__label">
            <span class="mono">TANGYUANAI</span>
            <span class="mono mono-mint">1 行</span>
          </div>
          <pre class="compare__code" v-pre><code><span class="k">class</span> <span class="t">AnyAgent</span>(tangyuanAI.BaseAgent):
    <span class="k">protocol</span> = <span class="s">"openai"</span>   <span class="c"># ← 改这一行切 API</span></code></pre>
          <ul class="compare__builtin">
            <li><span class="ck" aria-hidden="true"></span>鉴权</li>
            <li><span class="ck" aria-hidden="true"></span>流式装配</li>
            <li><span class="ck" aria-hidden="true"></span>工具桥接</li>
            <li><span class="ck" aria-hidden="true"></span>自动重试</li>
            <li><span class="ck" aria-hidden="true"></span>超时控制</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- ══════════ CTA ══════════ -->
    <section class="cta">
      <p class="kicker reveal">GET STARTED</p>
      <h2 class="cta__title reveal">几分钟，接入你的 API<br><strong class="hl">构建你的 Agent</strong></h2>
      <p class="cta__sub reveal">一个 <code>protocol</code> 字段 = 对接一个 LLM API。</p>
      <div class="cta__actions reveal">
        <button class="btn btn--primary btn--lg" data-copy="uv add tangyuanAI">uv add tangyuanAI</button>
        <a class="btn btn--default btn--lg" href="https://github.com/secret-tangyuan/tangyuanAI" target="_blank" rel="noopener">GitHub</a>
        <a class="btn btn--ghost btn--lg" href="/docs/">文档</a>
      </div>
    </section>

  </main>

  <!-- ══════════ Footer ══════════ -->
  <footer class="footer">
    <div class="footer__inner">
      <div class="footer__top">
        <div class="footer__brand">
          <span class="brand__mark" aria-hidden="true"></span>
          <span class="brand__word">tangyuan<span>AI</span></span>
        </div>
        <div class="footer__links">
          <a href="https://github.com/secret-tangyuan/tangyuanAI" target="_blank" rel="noopener">GitHub</a>
          <a href="/docs/">文档</a>
          <a href="https://pypi.org/project/tangyuanAI/" target="_blank" rel="noopener">PyPI</a>
          <a href="https://gravatar.com/secrettangyuan" target="_blank" rel="noopener">作者 · secret-tangyuan</a>
        </div>
      </div>
      <div class="footer__legal mono">
        <span>Apache License 2.0</span>
        <span>Python 3.10+</span>
        <span>© 2026 tangyuanAI</span>
      </div>
    </div>
  </footer>

  <div class="toast" id="toast" role="status" aria-live="polite">已复制到剪贴板</div>

</div>
</template>