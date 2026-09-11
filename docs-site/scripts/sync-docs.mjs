// scripts/sync-docs.mjs
// 构建前把 ../docs/*.md 同步到 docs-site/docs-build/docs/（node_modules 同层），
// 并把 docs-site/landing/index.md（落地页包装）复制为 docs-build/index.md（/ 路由）。
//
// 原因：VitePress 的 srcDir 如果指向仓库根的 docs/（node_modules 之外），
// 在 pnpm 依赖隔离下，docs/*.md 里的 vue 依赖解析不到 docs-site/node_modules，
// 干净环境（Cloudflare Pages / CI）构建必挂。同步到构建目录内即可。
import { mkdirSync, readdirSync, copyFileSync, rmSync, existsSync, statSync, utimesSync } from 'node:fs'
import { resolve, dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const SRC = resolve(__dirname, '../../docs')      // tangyuanAI/docs/（数据源）
const DST_DOCS = resolve(__dirname, '../docs-build/docs') // 文档构建目录（/docs/* 路由）
const DST_ROOT = resolve(__dirname, '../docs-build')      // 构建目录根（/ 路由）
const LANDING_MD = resolve(__dirname, '../landing/index.md') // 落地页包装模板
const SKIP = new Set(['README.md'])

// 1) 同步文档 markdown → docs-build/docs/  (递归,保留子目录)
mkdirSync(DST_DOCS, { recursive: true })
function walkMd(root) {
  const out = []
  for (const f of readdirSync(root)) {
    if (f.startsWith('.')) continue
    const p = join(root, f)
    const st = statSync(p)
    if (st.isDirectory()) {
      out.push(...walkMd(p))
    } else if (st.isFile() && f.endsWith('.md') && !SKIP.has(f)) {
      out.push(p)
    }
  }
  return out
}
let copied = 0
for (const src of walkMd(SRC)) {
  const rel = src.slice(SRC.length + 1)
  const dst = join(DST_DOCS, rel)
  mkdirSync(dirname(dst), { recursive: true })
  if (!existsSync(dst) || statSync(src).mtimeMs !== statSync(dst).mtimeMs) {
    copyFileSync(src, dst)
    utimesSync(dst, statSync(src).atime, statSync(src).mtime)
    copied += 1
  }
}

// 2) 落地页包装 → docs-build/index.md（/ 路由的页面）
mkdirSync(DST_ROOT, { recursive: true })
const landingDst = join(DST_ROOT, 'index.md')
if (!existsSync(landingDst) || statSync(LANDING_MD).mtimeMs !== statSync(landingDst).mtimeMs) {
  copyFileSync(LANDING_MD, landingDst)
  utimesSync(landingDst, statSync(LANDING_MD).atime, statSync(LANDING_MD).mtime)
}

// 3) 同步 public/ 静态资源 → docs-build/public/
// VitePress 的 publicDir = srcDir/public，所以 _redirects 等必须进构建目录
const SRC_PUBLIC = resolve(__dirname, '../public')
const DST_PUBLIC = join(DST_ROOT, 'public')
mkdirSync(DST_PUBLIC, { recursive: true })
let pubCopied = 0
for (const f of readdirSync(SRC_PUBLIC)) {
  const src = join(SRC_PUBLIC, f)
  const dst = join(DST_PUBLIC, f)
  if (!existsSync(dst) || statSync(src).mtimeMs !== statSync(dst).mtimeMs) {
    copyFileSync(src, dst)
    pubCopied += 1
  }
}

console.log(`[sync-docs] ${copied} 个文档 → docs-build/docs/ + 落地页 → docs-build/index.md + ${pubCopied} 个 public 资源 (共 ${readdirSync(DST_DOCS).filter(f => f.endsWith('.md')).length} 个)`)