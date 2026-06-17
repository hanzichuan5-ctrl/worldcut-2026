# 前端 JS 模块化拆分(方案 B)

## 目标

`index.html` 目前把一个 2147 行的 `<script>` 代码块直接内嵌在页面里(没有模块化、没有构建步骤),里面包含约 150 个函数和约 20 个顶层 `let`/`const` 状态变量。本次工作把它拆分成多个原生 ES module 文件,放在新建的 `js/` 目录下,按功能模块组织代码,但**不改变任何行为、输出、样式或交互**,也**不引入任何构建工具**。

## 不做的事情

- 不引入 React、Vue 或任何 UI 框架
- 不引入 Vite、webpack、esbuild 或任何打包工具
- 不引入任何 npm/Node 依赖
- 不引入测试框架
- 不修改 `server.py`
- 不做任何行为、文案、样式或交互上的改动——这是一次纯结构性重构

## 为什么不需要改后端

`server.py` 的 `Handler.do_GET` 只拦截特定的 `/api/*` 路径,其他所有路径都会走到 `SimpleHTTPRequestHandler` 默认的静态文件服务逻辑(通过现有的 `translate_path` 覆写,把任意相对路径解析到 `ROOT` 目录下)。请求 `/js/main.js` 会被解析成 `ROOT/js/main.js` 并自动以正确的 JavaScript MIME 类型返回。不需要改任何路由或 handler 代码。

## 拆分前的清单(必须先做这一步)

在搬动任何代码之前,先完整记录:

1. 当前 `<script>` 代码块里声明的**每一个**顶层函数名
2. **每一个**顶层 `let`/`const` 模块级状态变量
3. 所有通过内联 `onclick=`/`onchange=`/`oninput=` 属性引用的函数名——既包括静态 HTML 标签里的,也包括 JS 模板字符串拼出来再通过 `innerHTML` 注入页面的那些

这份清单就是后续写 `import`/`export` 语句时用来核对"有没有漏掉"的依据。设计阶段已经先扫了一遍,识别出 onclick 调用的函数有 20 个、顶层状态变量约 20 个,但真正动手拆分之前必须**对照当时最新的文件内容重新核对一遍**,而不是直接照搬这份设计文档里的数字(文件到那时可能已经有新的改动)。

## 目标模块划分

所有文件放在 `js/` 目录下,通过下面这行从 `index.html` 加载:

```html
<script type="module" src="js/main.js"></script>
```

替换掉现在内联的 `<script>...</script>` 代码块。

| 文件 | 负责的内容 |
| --- | --- |
| `state.js` | 共享的可变状态(`matches`、`activeView`、`simAccount`、`calc*` 等)以及生成这些状态用到的 `scheduleMatch`/赛程 fixture 数据 |
| `utils.js` | 通用工具函数:`escapeHtml`、日期格式化(`cnDate`/`cnDateTime`)、赔率换算(`americanToDecimal`、`probsFromDecimal` 等) |
| `odds-feed.js` | 体彩数据接入、解析、赔率走势渲染 |
| `calculator.js` | 串关计算器(目前代码量最大的部分,约 700 行) |
| `simulation.js` | 模拟资金账户、下注模拟、持仓/账本渲染 |
| `llm.js` | LLM 下注历史、自动下注计划应用、赛后复核渲染 |
| `view.js` | 视图/标签切换、赛果分页渲染、顶层 `render()` |
| `main.js` | 入口文件:import 上面所有模块,把那 20 个被 onclick 调用的函数重新挂回 `window`,并执行原脚本底部的初始化代码(事件绑定、`loadResults()`、`boot()`) |

模块划分依据的是现有代码里已经能看出来的功能聚类(按函数名前缀/用途分组),不是重新设计的理想架构——目的是把现有结构原样映射到不同文件里,而不是重新规划职责边界。

## 状态如何在模块间共享

`state.js` 直接 `export` 它的 `let` 变量(比如 `export let activeView = 'predictions'`)。ES module 的导出绑定是"活的":一个模块给它 import 进来的 `let` 变量赋值后,其他 import 了同一个绑定的模块会立刻看到最新的值。这样就能完全保留现在"隐式共享全局变量"的行为,而不需要引入状态容器、store 或发布订阅机制——引入那些东西会是一次有行为风险的重新设计,而不是单纯的重构。

每个模块只从 `state.js`/`utils.js` import 自己真正用到的那几个名字,把现在隐式的依赖关系通过 `import` 语句显式地写出来。

## 内联 HTML 事件处理函数的 window 挂载

`index.html` 的页面内容(静态标签 + JS 动态拼出来塞进 `innerHTML` 的内容)里有约 20 个函数是通过内联 `onclick=` 属性调用的(比如 `toggleSimPanel`、`loadResults`、`selectCalculatorMarket`、`toggleCalculatorCandidate`、`setResultsPage` 等)。ES module 里声明的顶层函数默认不会变成全局的,所以 `main.js` 必须在 import 这些函数之后,显式地把它们挂到 `window` 上(比如 `window.toggleSimPanel = toggleSimPanel;`)。这是这次迁移里唯一刻意引入的全局变量暴露;除此之外的所有函数都是模块私有的,除非被其他模块显式 import。

## 迁移方式

一次性整体搬移,不按函数逐个改动:这些函数之间耦合很深(共享状态、共享 DOM 元素 ID、互相调用,而这些调用关系将来会跨模块边界),拆到一半的中间状态会直接导致页面不可用。具体做法是把现有代码原样剪切到新文件里,加上 `import`/`export` 相关的代码,不改动任何业务逻辑,除了模块化语法本身必须的改动外也不做格式调整。

## 验证方式

项目目前没有任何前端自动化测试(没有 `package.json`,没有测试框架),这次重构也不会引入。验证方式是人工点击测试。

交付物:拆分完成后,产出一份验证清单,列出需要人工点击测试的每一个页面/视图和每一个交互控件,重点覆盖那 20 个绑定了 onclick 的函数(因为如果 `window` 挂载漏了哪个,这些函数最容易"悄无声息"地坏掉)。这份清单会交给你(或者到时候如果浏览器自动化可用,由我来跑一遍)来确认重构后的页面和重构前的行为完全一致。
