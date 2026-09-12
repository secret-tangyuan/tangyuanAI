import { defineConfig } from 'vitepress'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { resolve, dirname, join, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
// 页面根目录（srcDir）：docs-site/docs-build/（构建前由 scripts/sync-docs.mjs 生成），
// 内含 / 落地页（index.md + Landing.vue）与 /docs/ 子目录（docs/*.md）。
// 必须放在 docs-site/ 内（与 node_modules 同层），否则 pnpm 依赖隔离下
// docs/*.md 里的 vue 依赖解析不到，干净环境（Cloudflare Pages / CI）构建会挂。
const PAGES_DIR = resolve(__dirname, '../docs-build')
// 文档 markdown 目录（侧栏数据源）：docs-build/docs/ (递归)
const DOCS_DIR = resolve(__dirname, '../docs-build/docs')

interface DocMeta {
  file: string  // 相对 DOCS_DIR 路径,不含 .md (e.g. "tutorial/01-getting-started")
  title: string
  order: number
  icon: string
}

/** 极简 frontmatter 解析（只取 slug/title/order/icon 标量字段,够用即可;兼容 CRLF/LF 换行） */
function parseFrontmatter(raw: string): Record<string, string | number> {
  const m = raw.match(/^---[\r\n]+([\s\S]*?)[\r\n]+---/)
  if (!m) return {}
  const meta: Record<string, string | number> = {}
  for (const line of m[1].split(/\r?\n/)) {
    const idx = line.indexOf(':')
    if (idx <= 0) continue
    const key = line.slice(0, idx).trim()
    const value = line.slice(idx + 1).trim().replace(/^['"]|['"]$/g, '')
    if (key in meta) continue
    meta[key] = /^\d+$/.test(value) ? Number(value) : value
  }
  return meta
}

/** 递归扫描 docs-build/docs/,按 frontmatter 的 order 排序 */
function walkMd(root: string, rel: string = ''): string[] {
  const out: string[] = []
  for (const f of readdirSync(root)) {
    if (f.startsWith('.')) continue
    const p = join(root, f)
    const st = statSync(p)
    if (st.isDirectory()) {
      out.push(...walkMd(p, rel ? `${rel}/${f}` : f))
    } else if (st.isFile() && f.endsWith('.md') && !f.startsWith('README')) {
      out.push(rel ? `${rel}/${f}` : f)
    }
  }
  return out
}

function loadDocs(): DocMeta[] {
  return walkMd(DOCS_DIR)
    .map((f) => {
      const raw = readFileSync(join(DOCS_DIR, f), 'utf-8')
      const meta = parseFrontmatter(raw)
      const base = f.replace(/\.md$/, '')
      return {
        file: base,
        title: String(meta.title ?? base),
        order: Number(meta.order ?? 999),
        icon: String(meta.icon ?? ''),
      }
    })
    .sort((a, b) => a.order - b.order)
}

const docs = loadDocs()

/** 文件相对路径 → 路由链接（文档挂在 /docs/ 下;index 是文档首页） */
const linkOf = (file: string) => {
  if (file === 'index') return '/docs/'
  // 把 posix 分隔符归一 (Windows 上 walkMd 可能用 \\, VitePress 路由要 /)
  return `/docs/${file.split(sep).join('/')}`
}

const sidebarItems = docs.map((d) => ({ text: d.title, link: linkOf(d.file) }))

/** 把 docs 按 order 排序,然后按 "组" 字段分组成层级 sidebar。order 相同 / 不带 _ 前缀的 docs 走 fallback。*/
const TUTORIAL_PREFIX = "tutorial/"
const SIDEBAR_GROUPS: { name: string; match: (f: string) => boolean; collapsed?: boolean }[] = [
  { name: "首页 Home", match: (f) => f === "index" },
  { name: "教程 Tutorial", match: (f) => f.startsWith(TUTORIAL_PREFIX), collapsed: false },
  { name: "入门 Getting Started", match: (f) => f === "getting-started" || f === "agent-registration" },
  { name: "核心能力 Core", match: (f) =>
    ["tools", "builtin-tools", "protocols", "output-and-hooks", "skill", "mcp", "mcp-skills", "persistence"].includes(f) },
  { name: "数据 / 插件 / 互操作", match: (f) =>
    ["kb", "image-generation", "image-input", "plugin-install", "plugin-dev", "plugin-compat", "a2a"].includes(f) },
]

function buildSidebar() {
  const groups: Record<string, typeof sidebarItems> = {}
  for (const g of SIDEBAR_GROUPS) groups[g.name] = []
  const ungrouped: typeof sidebarItems = []
  for (const item of sidebarItems) {
    const group = SIDEBAR_GROUPS.find((g) => g.match(item.link.replace("/docs/", "")))
    if (group) groups[group.name].push(item)
    else ungrouped.push(item)
  }
  const out: { text: string; items: typeof sidebarItems; collapsed?: boolean }[] = []
  for (const g of SIDEBAR_GROUPS) {
    if (groups[g.name].length === 0) continue
    out.push({ text: g.name, items: groups[g.name], collapsed: g.collapsed })
  }
  if (ungrouped.length > 0) {
    out.push({ text: "其他", items: ungrouped })
  }
  return out
}

const groupedSidebar = buildSidebar()

export default defineConfig({
  title: 'tangyuanAI',
  description: '轻量、模块化的多智能体协作框架',

  // srcDir 指向构建目录 docs-build/（构建前由 scripts/sync-docs.mjs 生成），
  // 必须放在 docs-site/ 内（与 node_modules 同层），否则 pnpm 依赖隔离下
  // docs/*.md 里的 vue 依赖解析不到，干净环境（Cloudflare Pages / CI）构建会挂。
  srcDir: PAGES_DIR,
  // public/（如 _redirects）相对 docs-site/ 根，显式指定避免受 srcDir 影响
  publicDir: resolve(__dirname, '../public'),
  cleanUrls: true,
  lastUpdated: true,
  ignoreDeadLinks: true,

  head: [
    ['link', { rel: 'icon', href: 'data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 16 16%27%3E%3Crect width=%2716%27 height=%2716%27 fill=%27%23BBDDFF%27/%3E%3C/svg%3E' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', { rel: 'stylesheet', href: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;600&family=Noto+Sans+SC:wght@400;500;700;900&display=swap' }],
  ],

  themeConfig: {
    logo: '/logo.svg',
    nav: [
      { text: '首页', link: '/' },
      { text: '文档', link: '/docs/' },
      { text: 'GitHub', link: 'https://github.com/secret-tangyuan/tangyuanAI' },
    ],
    sidebar: {
      "/docs/": groupedSidebar,
    },
    outline: {  // 右侧页面标题大纲(2-3 级)
      level: [2, 3],
      label: "本页目录",
    },
    search: {
      provider: 'local',
      options: {
        translations: {
          button: { buttonText: '搜索文档', buttonAriaLabel: '搜索文档' },
          modal: {
            displayDetails: '显示详情',
            resetButtonTitle: '重置',
            backButtonTitle: '返回',
            noResultsText: '没有找到相关结果',
            footer: { selectText: '选择', navigateText: '切换', closeText: '关闭' },
          },
        },
      },
    },
    docFooter: { prev: '上一篇', next: '下一篇' },
    sidebarMenuLabel: '目录',
    returnToTopLabel: '回到顶部',
    darkModeSwitchLabel: '外观',
    lastUpdatedText: '最后更新',
  },
})