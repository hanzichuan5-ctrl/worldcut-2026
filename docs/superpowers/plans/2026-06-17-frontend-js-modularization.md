# 前端 JS 模块化拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `index.html` 里内嵌的 2147 行 `<script>` 代码块拆成 `js/` 目录下的 8 个原生 ES module 文件,不改变任何行为、样式、文案或交互,不引入任何构建工具/npm/Node/测试框架,不修改 `server.py`。

**Architecture:** 用一个一次性的 Python 脚本(`scratch/split_modules.py`,完成后删除,不提交到仓库)机械地完成拆分:脚本里写死"符号名 → 目标文件"的映射表(167 个顶层函数/变量,已通过静态分析逐一核对得到),按原始源码逐字节抽取每个符号的代码块,自动扫描每个代码块引用了哪些属于"其他文件"的符号来生成 `import` 语句,再把所有内容写出成 8 个目标文件。这样比手工剪切粘贴 2147 行代码可靠得多,而且可以做"还原检查"(把 8 个新文件内容拼起来去掉 import/export 之后应该和原脚本逐符号一一对应)。

**Tech Stack:** 原生 ES module(`<script type="module">`)、Python(仅用于跑一次性的迁移脚本,不是项目依赖)、现有的 `python3 server.py`。

---

## 背景:已经做过的静态分析

执行 Task 1 之前,已经用脚本扫描了 `index.html` 第 444-2589 行(`<script>` 内容),得到:

- **167 个顶层符号**(函数声明 + 顶层 `let`/`const`),每个都有精确的起止行号
- **2 段"散落"的顶层语句**(不属于任何具名声明,但仍在脚本顶层执行):
  - 第 578-583 行:一个 `for` 循环,给 `matches` 里每个 match 对象挂 `baseOdds`/`oddsSource`/`oddsDecimal` 并调用 `applyDrawPrediction(match)`。**关键细节**:这段代码在 `staticMatches`(542 行,= `matches` 的浅拷贝)之后才执行,所以 `staticMatches` 里的对象**不会**带有 `baseOdds`/`oddsSource`/`oddsDecimal` 这几个字段——这是现在就有的行为,拆分时必须原样保留这个执行顺序,不能把这段代码挪到 `staticMatches` 定义之前。
  - 第 2482-2503、2577、2589 行:`bindViewTabs()`、`renderPredictionLoading(...)`、`setActiveView(activeView)`、两个 `forEach` 事件绑定块、`loadResults()`、`boot()`——这些是页面加载时的初始化代码,必须原样进 `main.js`,且执行顺序不能变。
- **20 个通过内联 `onclick=` 调用的函数**(包括静态 HTML 标签和 JS 拼出来塞进 `innerHTML` 的字符串):`addCalculatorSelectionsToSim`、`applyImportedOdds`、`clearCalculatorSelections`、`llmAutoPlaceBets`、`loadResults`、`loadSportteryCalculator`、`refreshSportteryOdds`、`renderCalculatorTickets`、`resetSimAccount`、`selectCalculatorMarket`、`selectCalculatorPredictions`、`setResultsPage`、`settleSimAccount`、`syncSimBetsToCalculator`、`toggleCalculatorCandidate`、`toggleCalculatorSelection`、`toggleLedger`、`toggleLlmHistory`、`toggleOddsImport`、`toggleSimPanel`。这 20 个必须在 `main.js` 里显式挂到 `window` 上。
  - 另外发现 4 个函数(`toggleHistory`、`runAiReview`、`fetchAndApply`、`refreshAllAi`)是通过 `btn.onclick = () => ...` 这种 JS 内部赋值绑定的,**不需要**挂到 `window`,因为调用方就是模块内部代码本身。
  - `refreshAllAi` 这个函数在当前代码里定义了但没有任何地方调用——这是现有代码里本来就有的"死代码"。本次是纯重构,**必须原样保留**,不能因为看起来没用就删掉。

## 符号 → 目标文件映射表(167 个,全部覆盖,无遗漏无重复)

```
state.js (29): scheduleMatch, matches, staticMatches, dates, active, activeView,
  finishedResults, resultsRows, resultsPage, aiResults, GLOBAL_SIM_ACCOUNT_ID,
  AUTO_BET_STRATEGY_VERSION, RESULTS_PAGE_SIZE, simAccount, llmBetHistory,
  postReviews, simStats, settlementInfo, workerInfo, workerLog, calcMatches,
  calcSelections, calcCandidateKeys, calcSourceInfo, calcRefreshTimer,
  calcRefreshRunning, simAccountId, lastAutoBetSignature, llmBetRunning
  + 第 578-583 行的初始化 for 循环(原样保留在 matches/staticMatches 之后、dates 之前的相对位置)

utils.js (16): escapeHtml, americanToDecimal, decimalToAmerican, cnDate, cnDateTime,
  probsFromDecimal, pickFromProbs, confFromProb, drawSignalFromProbs, shouldPickDraw,
  likelyDrawScore, impliedPercentFromDecimal, impliedPercent, normalizeTeamName,
  findScheduleMatch, walkJson

odds-feed.js (20): scoreFromMarket, applyDrawPrediction, sportteryToMatch, marketLabel,
  betPlayLabel, oddsLabel, decimalOddsLabel, oddsTrendSeries, renderSparkline,
  renderOddsTrend, findSportteryMatch, markFinishedMatches, sportteryPick,
  normalizeSportteryDecimal, parseSportteryPayload, chooseSportteryPool,
  applySportteryItems, toggleOddsImport, applyImportedOdds, refreshSportteryOdds

calculator.js (54): calculatorMatchKey, calculatorFixtureKey, calculatorSourceMatches,
  calculatorMatchByKey, calculatorFixtureMatches, clearCalculatorFixtureSelection,
  groupedCalculatorMatches, calculatorSelectionsFor, calculatorCandidateCount,
  setCalculatorMarketSelection, calculatorDefaultPickIndex, selectCalculatorMarket,
  toggleCalculatorCandidate, toggleCalculatorSelection, clearCalculatorSelections,
  normalizeCalculatorPassType, denormalizeCalculatorPassType, simMatchIdForCalculator,
  calculatorBetSessionId, simLegKey, selectCalculatorPredictions, calcCombinations,
  calcLimitedPayout, formatCalcMoney, setCalculatorStatus, setSimStatus,
  selectedCalculatorLegs, candidateCalculatorLegs, calculatorPassOptionLegs,
  updateCalculatorPassOptions, calculateSportteryBonus, cartesianOdds,
  calculatorTicketLeg, buildCalculatorTicket, buildCalculatorTickets,
  renderCalculatorTickets, simLegFromCalculator, calculatorBetKey,
  addCalculatorSelectionsToSim, pickIndexFromLabel, matchNameParts,
  findCalculatorMatchForBet, pendingSimBets, simBetIdentity,
  chooseSimBetsForCalculator, inferCalculatorTimesFromBets,
  inferCalculatorPassTypeFromBets, applyCalculatorControlsFromSim,
  syncSimBetsToCalculator, renderCalculatorSummary, renderCalculator,
  loadSportteryCalculator, startCalculatorRealtime, stopCalculatorRealtime

simulation.js (22): pickIndex, kellyFraction, readBankrollInput, loadSimAccount,
  loadServerSimState, saveSimAccount, updateDbStatus, ensureSimAccount, betKey,
  betKeyForPick, simulateMatch, matchById, pendingMatches, decimalForPick,
  oddsSignature, resetSimAccount, toggleLedger, settleSimAccount, renderSimAccount,
  renderLedger, idsForSimBetItem, renderSimulation

llm.js (14): loadLlmBetHistory, calculateLocalStats, llmAutoPlaceBets,
  applyLlmBetPlan, recordLlmBetPlan, toggleLlmHistory, renderLlmHistory,
  renderPostReviews, restoreRenderedAiResults, toggleHistory, runAiReview,
  fetchAndApply, applyAiResult, refreshAllAi

view.js (11): refreshDateFilters, renderFilters, setActiveView, bindViewTabs,
  renderPredictionLoading, render, toggleSimPanel, resultRowHtml,
  renderResultsPage, setResultsPage, loadResults

main.js (1 具名符号 + 散落初始化代码): boot
  + 第 2482-2503、2577、2589 行的初始化代码(原样保留执行顺序)
  + 20 个 onclick 函数的 window 挂载语句
```

合计 29+16+20+54+22+14+11+1 = 167,与扫描得到的符号总数一致。

---

### Task 1: 生成并核对完整符号清单(可重复执行的核对脚本)

**Files:**
- Create: `scratch/extract_symbols.py`(一次性脚本,执行完即删除,不提交)

- [ ] **Step 1: 写提取脚本**

```python
# scratch/extract_symbols.py
import re

with open('index.html', encoding='utf-8') as f:
    lines = f.readlines()

START, END = 443, 2590  # <script> 行号, </script> 行号(1-indexed)

symbols = []
li = START
while li < END:
    line = lines[li-1].rstrip('\n')
    m_func = re.match(r'^(async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(', line)
    m_var = re.match(r'^(let|const)\s+([A-Za-z_$][\w$]*)\s*=', line)
    if m_func or m_var:
        name = (m_func or m_var).group(2)
        depth, j, started = 0, li, False
        is_func = bool(m_func)
        open_chars = '{' if is_func else '{[('
        close_chars = '}' if is_func else '}])'
        while j <= END:
            for ch in lines[j-1]:
                if ch in open_chars:
                    depth += 1; started = True
                elif ch in close_chars:
                    depth -= 1
            if started and depth <= 0:
                if is_func or lines[j-1].rstrip().endswith((';', '}', ')')):
                    break
            j += 1
        symbols.append((name, 'function' if is_func else 'var', li, j))
        li = j + 1
        continue
    li += 1

names = [s[0] for s in symbols]
dupes = [n for n in set(names) if names.count(n) > 1]
print(f"TOTAL symbols: {len(symbols)}")
print(f"Duplicate names: {dupes}")
for s in symbols:
    print(s)
```

- [ ] **Step 2: 执行并核对数量**

Run: `python scratch/extract_symbols.py > scratch/symbols_check.txt`
Expected: 输出里 `TOTAL symbols: 167`,`Duplicate names: []`。

如果数字不是 167,或者出现 duplicate,**停下来**,先去对比这份 plan 里的映射表和实际代码的差异,不要往下走——这意味着代码自上次分析后发生了变化,或者脚本的括号计数在某个函数里出了偏差。

- [ ] **Step 3: 核对映射表覆盖了 scratch/symbols_check.txt 里的每一个名字**

把本 plan 里"符号 → 目标文件映射表"章节列出的全部名字收集成一个集合,和 `scratch/symbols_check.txt` 里的 167 个名字逐一比对(可以用脚本做集合差集),确认两边完全一致(无遗漏、无多余)。

- [ ] **Step 4: 提交前清理**

这一步的 `scratch/` 目录只是核对用的脚手架,不是交付物。任务全部完成后(Task 6 验证通过)要在最终提交前删除整个 `scratch/` 目录。现在先不删,后面 Task 还要复用。

---

### Task 2: 编写并运行模块拆分脚本,生成 8 个目标文件

**Files:**
- Create: `scratch/split_modules.py`(一次性脚本,完成后删除)
- Create: `js/state.js`
- Create: `js/utils.js`
- Create: `js/odds-feed.js`
- Create: `js/calculator.js`
- Create: `js/simulation.js`
- Create: `js/llm.js`
- Create: `js/view.js`
- Create: `js/main.js`

- [ ] **Step 1: 写拆分脚本**

```python
# scratch/split_modules.py
import re

with open('index.html', encoding='utf-8') as f:
    lines = f.readlines()

START, END = 443, 2590

# 复用 Task 1 的提取逻辑,拿到 (name, kind, start, end) 列表
def extract_symbols():
    symbols = []
    li = START
    while li < END:
        line = lines[li-1].rstrip('\n')
        m_func = re.match(r'^(async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(', line)
        m_var = re.match(r'^(let|const)\s+([A-Za-z_$][\w$]*)\s*=', line)
        if m_func or m_var:
            name = (m_func or m_var).group(2)
            depth, j, started = 0, li, False
            is_func = bool(m_func)
            open_chars = '{' if is_func else '{[('
            close_chars = '}' if is_func else '}])'
            while j <= END:
                for ch in lines[j-1]:
                    if ch in open_chars:
                        depth += 1; started = True
                    elif ch in close_chars:
                        depth -= 1
                if started and depth <= 0:
                    if is_func or lines[j-1].rstrip().endswith((';', '}', ')')):
                        break
                j += 1
            symbols.append((name, 'function' if is_func else 'var', li, j))
            li = j + 1
            continue
        li += 1
    return symbols

symbols = extract_symbols()
sym_by_name = {s[0]: s for s in symbols}
all_names = set(sym_by_name)

BUCKETS = {
  'state': ['scheduleMatch','matches','staticMatches','dates','active','activeView',
    'finishedResults','resultsRows','resultsPage','aiResults','GLOBAL_SIM_ACCOUNT_ID',
    'AUTO_BET_STRATEGY_VERSION','RESULTS_PAGE_SIZE','simAccount','llmBetHistory',
    'postReviews','simStats','settlementInfo','workerInfo','workerLog','calcMatches',
    'calcSelections','calcCandidateKeys','calcSourceInfo','calcRefreshTimer',
    'calcRefreshRunning','simAccountId','lastAutoBetSignature','llmBetRunning'],
  'utils': ['escapeHtml','americanToDecimal','decimalToAmerican','cnDate','cnDateTime',
    'probsFromDecimal','pickFromProbs','confFromProb','drawSignalFromProbs',
    'shouldPickDraw','likelyDrawScore','impliedPercentFromDecimal','impliedPercent',
    'normalizeTeamName','findScheduleMatch','walkJson'],
  'odds-feed': ['scoreFromMarket','applyDrawPrediction','sportteryToMatch','marketLabel',
    'betPlayLabel','oddsLabel','decimalOddsLabel','oddsTrendSeries','renderSparkline',
    'renderOddsTrend','findSportteryMatch','markFinishedMatches','sportteryPick',
    'normalizeSportteryDecimal','parseSportteryPayload','chooseSportteryPool',
    'applySportteryItems','toggleOddsImport','applyImportedOdds','refreshSportteryOdds'],
  'calculator': ['calculatorMatchKey','calculatorFixtureKey','calculatorSourceMatches',
    'calculatorMatchByKey','calculatorFixtureMatches','clearCalculatorFixtureSelection',
    'groupedCalculatorMatches','calculatorSelectionsFor','calculatorCandidateCount',
    'setCalculatorMarketSelection','calculatorDefaultPickIndex','selectCalculatorMarket',
    'toggleCalculatorCandidate','toggleCalculatorSelection','clearCalculatorSelections',
    'normalizeCalculatorPassType','denormalizeCalculatorPassType','simMatchIdForCalculator',
    'calculatorBetSessionId','simLegKey','selectCalculatorPredictions','calcCombinations',
    'calcLimitedPayout','formatCalcMoney','setCalculatorStatus','setSimStatus',
    'selectedCalculatorLegs','candidateCalculatorLegs','calculatorPassOptionLegs',
    'updateCalculatorPassOptions','calculateSportteryBonus','cartesianOdds',
    'calculatorTicketLeg','buildCalculatorTicket','buildCalculatorTickets',
    'renderCalculatorTickets','simLegFromCalculator','calculatorBetKey',
    'addCalculatorSelectionsToSim','pickIndexFromLabel','matchNameParts',
    'findCalculatorMatchForBet','pendingSimBets','simBetIdentity',
    'chooseSimBetsForCalculator','inferCalculatorTimesFromBets',
    'inferCalculatorPassTypeFromBets','applyCalculatorControlsFromSim',
    'syncSimBetsToCalculator','renderCalculatorSummary','renderCalculator',
    'loadSportteryCalculator','startCalculatorRealtime','stopCalculatorRealtime'],
  'simulation': ['pickIndex','kellyFraction','readBankrollInput','loadSimAccount',
    'loadServerSimState','saveSimAccount','updateDbStatus','ensureSimAccount','betKey',
    'betKeyForPick','simulateMatch','matchById','pendingMatches','decimalForPick',
    'oddsSignature','resetSimAccount','toggleLedger','settleSimAccount','renderSimAccount',
    'renderLedger','idsForSimBetItem','renderSimulation'],
  'llm': ['loadLlmBetHistory','calculateLocalStats','llmAutoPlaceBets','applyLlmBetPlan',
    'recordLlmBetPlan','toggleLlmHistory','renderLlmHistory','renderPostReviews',
    'restoreRenderedAiResults','toggleHistory','runAiReview','fetchAndApply',
    'applyAiResult','refreshAllAi'],
  'view': ['refreshDateFilters','renderFilters','setActiveView','bindViewTabs',
    'renderPredictionLoading','render','toggleSimPanel','resultRowHtml',
    'renderResultsPage','setResultsPage','loadResults'],
  'main': ['boot'],
}

# 完整性核对:映射表覆盖了扫描出来的全部符号,且没有多余/重复
assigned = [n for names in BUCKETS.values() for n in names]
assert len(assigned) == len(set(assigned)), "映射表里有重复名字"
assert set(assigned) == all_names, f"映射表和扫描结果不一致: 缺失={all_names-set(assigned)} 多余={set(assigned)-all_names}"

name_to_bucket = {n: b for b, names in BUCKETS.items() for n in names}

FILE_FOR_BUCKET = {
  'state': 'state.js', 'utils': 'utils.js', 'odds-feed': 'odds-feed.js',
  'calculator': 'calculator.js', 'simulation': 'simulation.js',
  'llm': 'llm.js', 'view': 'view.js', 'main': 'main.js',
}

def src(name):
    _, kind, s, e = sym_by_name[name]
    return ''.join(lines[s-1:e])

def export_src(name):
    text = src(name)
    if text.startswith('function ') or text.startswith('async function '):
        return 'export ' + text
    if text.startswith('let ') or text.startswith('const '):
        return 'export ' + text
    raise ValueError(f"unexpected declaration shape for {name}")

IDENT_RE = re.compile(r'[A-Za-z_$][\w$]*')

def external_deps(name, bucket):
    text = src(name)
    used = set(IDENT_RE.findall(text)) & all_names
    used.discard(name)
    deps = {}
    for dep in used:
        dep_bucket = name_to_bucket[dep]
        if dep_bucket != bucket:
            deps.setdefault(dep_bucket, set()).add(dep)
    return deps

# state.js 里那段第 578-583 行的初始化循环,原样保留,放在 matches/staticMatches 之后
STATE_INIT_BLOCK = ''.join(lines[577:583])  # 0-indexed 577..582 -> 行 578-583

for bucket, names in BUCKETS.items():
    if bucket == 'main':
        continue  # main.js 单独处理(Task 4)
    fname = f"js/{FILE_FOR_BUCKET[bucket]}"
    all_deps = {}
    for n in names:
        for dep_bucket, deps in external_deps(n, bucket).items():
            all_deps.setdefault(dep_bucket, set()).update(deps)
    import_lines = [
        f"import {{ {', '.join(sorted(deps))} }} from './{FILE_FOR_BUCKET[b]}';"
        for b, deps in sorted(all_deps.items())
    ]
    body_parts = []
    for n in names:
        body_parts.append(export_src(n))
        if bucket == 'state' and n == 'staticMatches':
            body_parts.append(STATE_INIT_BLOCK)
    content = '\n'.join(import_lines) + ('\n\n' if import_lines else '') + '\n'.join(body_parts)
    with open(fname, 'w', encoding='utf-8') as out:
        out.write(content)
    print(f"wrote {fname}: {len(names)} symbols, deps={ {k: sorted(v) for k,v in all_deps.items()} }")
```

- [ ] **Step 2: 运行脚本**

Run: `python scratch/split_modules.py`
Expected: 打印 7 行(`state.js` 到 `view.js`,不含 `main.js`),每行形如
`wrote js/calculator.js: 54 symbols, deps={'state': [...], 'utils': [...]}`,且没有抛出 `AssertionError`。

如果抛出 `AssertionError: 映射表和扫描结果不一致`,说明 index.html 在 Task 1 分析之后又变了,需要回到 Task 1 重新核对映射表,不要继续往下做。

- [ ] **Step 3: 检查每个生成文件的开头几行**

Run: `head -5 js/state.js js/utils.js js/odds-feed.js js/calculator.js js/simulation.js js/llm.js js/view.js`
Expected: 每个文件最前面是若干行 `import { ... } from './xxx.js';`(如果该文件不需要外部依赖则没有 import 行),紧接着是 `export function ...` 或 `export let/const ...`。

---

### Task 3: 手工编写 `main.js`(window 挂载 + 初始化顺序)

**Files:**
- Create: `js/main.js`(这个文件不走脚本生成,因为它是"胶水代码",需要人工核对初始化顺序)

- [ ] **Step 1: 确认 `boot` 函数原文**

Run: `sed -n '2579,2588p' index.html`
Expected: 输出 `async function boot(){ ... }` 的完整函数体(10 行,内容是 `await loadServerSimState(); renderPostReviews();` 包在 try/catch 里,然后 `refreshSportteryOdds();`)。

- [ ] **Step 2: 写 `js/main.js`**

```javascript
import { activeView, simAccount } from './state.js';
import { escapeHtml } from './utils.js';
import { refreshSportteryOdds, toggleOddsImport, applyImportedOdds } from './odds-feed.js';
import {
  addCalculatorSelectionsToSim, clearCalculatorSelections, loadSportteryCalculator,
  renderCalculatorTickets, selectCalculatorMarket, selectCalculatorPredictions,
  syncSimBetsToCalculator, toggleCalculatorCandidate, toggleCalculatorSelection,
  renderCalculator,
} from './calculator.js';
import {
  readBankrollInput, renderSimulation, resetSimAccount, saveSimAccount,
  settleSimAccount, toggleLedger, loadServerSimState,
} from './simulation.js';
import { llmAutoPlaceBets, toggleLlmHistory, renderPostReviews } from './llm.js';
import { bindViewTabs, loadResults, renderPredictionLoading, setActiveView, setResultsPage, toggleSimPanel } from './view.js';

// 这 20 个函数是通过 index.html 里的内联 onclick="..." 调用的(静态标签 + innerHTML
// 拼接的字符串都有),ES module 里的函数默认不是全局的,必须显式挂到 window 上,
// 否则点击对应按钮时会报 "xxx is not defined"。
window.addCalculatorSelectionsToSim = addCalculatorSelectionsToSim;
window.applyImportedOdds = applyImportedOdds;
window.clearCalculatorSelections = clearCalculatorSelections;
window.llmAutoPlaceBets = llmAutoPlaceBets;
window.loadResults = loadResults;
window.loadSportteryCalculator = loadSportteryCalculator;
window.refreshSportteryOdds = refreshSportteryOdds;
window.renderCalculatorTickets = renderCalculatorTickets;
window.resetSimAccount = resetSimAccount;
window.selectCalculatorMarket = selectCalculatorMarket;
window.selectCalculatorPredictions = selectCalculatorPredictions;
window.setResultsPage = setResultsPage;
window.settleSimAccount = settleSimAccount;
window.syncSimBetsToCalculator = syncSimBetsToCalculator;
window.toggleCalculatorCandidate = toggleCalculatorCandidate;
window.toggleCalculatorSelection = toggleCalculatorSelection;
window.toggleLedger = toggleLedger;
window.toggleLlmHistory = toggleLlmHistory;
window.toggleOddsImport = toggleOddsImport;
window.toggleSimPanel = toggleSimPanel;

// 下面原样保留原脚本底部的初始化顺序(原 index.html 第 2482-2503、2577、2589 行)
bindViewTabs();
renderPredictionLoading('正在同步赛果数据，避免把已完赛比赛混入赛前预测卡片。');
setActiveView(activeView);
['bankroll','riskMode','maxStake','minEdge'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', () => {
    if (id === 'bankroll') {
      simAccount = {initial: readBankrollInput(), cash: readBankrollInput(), bets: []};
    }
    renderSimulation();
  });
  document.getElementById(id)?.addEventListener('change', () => {
    if (id === 'bankroll') {
      simAccount = {initial: readBankrollInput(), cash: readBankrollInput(), bets: []};
      saveSimAccount();
    }
    renderSimulation();
  });
});
['calcTimes','calcPassType'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', renderCalculator);
  document.getElementById(id)?.addEventListener('change', renderCalculator);
});
loadResults();

async function boot(){
  try {
    await loadServerSimState();
    renderPostReviews();
  } catch (err) {
    const source = document.getElementById('oddsSource');
    if (source) source.querySelector('span').innerHTML = `<b>模拟账户：</b>账户读取失败：${escapeHtml(err.message)}`;
  }
  refreshSportteryOdds();
}
boot();
```

> 注意:这一步里 `import` 列表是根据 Task 2 脚本打印出来的各文件 `deps` 加上 `main.js` 自己直接用到的名字人工核对出来的。写完之后必须做 Task 4 的交叉核对,不能假设这里一次就写全了。

---

### Task 4: 交叉核对 import 完整性

**Files:**
- Create: `scratch/check_imports.py`

- [ ] **Step 1: 写核对脚本**

```python
# scratch/check_imports.py
import re, pathlib

FILES = ['state.js','utils.js','odds-feed.js','calculator.js','simulation.js','llm.js','view.js','main.js']
IDENT_RE = re.compile(r'[A-Za-z_$][\w$]*')
EXPORT_RE = re.compile(r'^export\s+(?:async\s+)?(?:function\s+([A-Za-z_$][\w$]*)|let\s+([A-Za-z_$][\w$]*)|const\s+([A-Za-z_$][\w$]*))', re.M)
IMPORT_RE = re.compile(r'^import\s*\{([^}]*)\}\s*from', re.M)

exported = {}
for fn in FILES:
    text = pathlib.Path('js', fn).read_text(encoding='utf-8')
    for m in EXPORT_RE.finditer(text):
        name = next(g for g in m.groups() if g)
        exported[name] = fn

for fn in FILES:
    text = pathlib.Path('js', fn).read_text(encoding='utf-8')
    imported = set()
    for m in IMPORT_RE.finditer(text):
        imported.update(n.strip() for n in m.group(1).split(','))
    # 去掉本文件自己 export 的名字、本文件 import 进来的名字、JS/DOM 内置名字之后,
    # 剩下还在 exported 全集里、但既不是本文件 export 也不是 import 进来的名字,就是漏 import 的
    own_exports = {n for n, f in exported.items() if f == fn}
    referenced = set(IDENT_RE.findall(text))
    missing = (referenced & set(exported)) - own_exports - imported
    if missing:
        print(f"{fn}: 可能缺少 import -> {sorted(missing)}")

print("done")
```

- [ ] **Step 2: 运行**

Run: `python scratch/check_imports.py`
Expected: 只输出 `done`,没有任何 `xxx: 可能缺少 import` 的行。

如果有输出,逐个检查:大部分情况是该名字在 `js/main.js` 或具体某个文件里被用到但 import 列表漏写了,回到对应文件补上 `import` 后再重新跑这一步,直到输出只有 `done`。

- [ ] **Step 3: 提交一次中间状态**

这时 `index.html` 还没有改,页面行为和重构前完全一样(因为浏览器还在用旧的内联 `<script>`,新的 `js/*.js` 还没被引用)。这是一个安全的提交点。

```bash
git add js/
git commit -m "Add modular js/ files (not yet wired into index.html)"
```

---

### Task 5: 切换 `index.html` 到模块化入口,删除旧的内联脚本

**Files:**
- Modify: `index.html:443-2590`(把整段内联 `<script>...</script>` 换成一行模块引用)

- [ ] **Step 1: 确认要替换的范围**

Run: `sed -n '443p;2590p' index.html`
Expected:
```
<script>
</script>
```

- [ ] **Step 2: 替换**

把 `index.html` 第 443 行到第 2590 行(整段 `<script>...</script>`,包含原来 2147 行的全部内容)替换成:

```html
<script type="module" src="js/main.js"></script>
```

- [ ] **Step 3: 确认替换后文件结构正常**

Run: `grep -n "<script" index.html`
Expected: 只有一行输出,内容是 `<script type="module" src="js/main.js"></script>`。

- [ ] **Step 4: 提交**

```bash
git add index.html
git commit -m "Switch index.html to modular js/main.js entry point"
```

---

### Task 6: 启动服务,跑一遍人工验证清单

**Files:** 无代码改动,这一步是验证

- [ ] **Step 1: 启动服务**

Run: `python server.py`(或确认已有的后台实例还在跑,端口 8765)
Expected: 控制台打印 `Serving on http://0.0.0.0:8765`,没有 Python 报错。

- [ ] **Step 2: 打开浏览器开发者工具的 Console,访问页面**

打开 `http://127.0.0.1:8765/`,看 Console 面板。
Expected: 没有红色报错(尤其注意 `Uncaught SyntaxError`、`is not defined`、`Failed to resolve module specifier` 这几类,说明 import/export 或 window 挂载漏了什么)。

- [ ] **Step 3: 逐项点击下面的验证清单**

| 区域 | 操作 | 预期 |
| --- | --- | --- |
| 顶部视图切换 | 点击"预测"/"计算器"/"模拟盘"/"赛果"四个标签 | 对应面板正确显示,和重构前一致 |
| 预测页 | 点击"模拟盘"按钮(`toggleSimPanel`) | 模拟盘面板展开/收起 |
| 预测页 | 点击"刷新体彩赔率"(`refreshSportteryOdds`) | 赔率源文字更新,无报错 |
| 预测页 | 点击"导入体彩 JSON"(`toggleOddsImport`)再点"应用导入"(`applyImportedOdds`) | 导入框展开,应用后赔率更新或给出明确报错提示 |
| 模拟盘 | 点击"立即 LLM 下注"(`llmAutoPlaceBets`) | 触发下注流程(没配 API key 的情况下应给出和重构前一样的提示) |
| 模拟盘 | 点击"同步到计算器"(`syncSimBetsToCalculator`) | 计算器面板按持仓同步选中项 |
| 模拟盘 | 点击"查看持仓"(`toggleLedger`) | 持仓列表展开/收起 |
| 模拟盘 | 点击"LLM 历史"(`toggleLlmHistory`) | LLM 下注历史展开/收起 |
| 模拟盘 | 点击"结算赛果"(`settleSimAccount`) | 触发结算请求,行为与之前一致 |
| 模拟盘 | 点击"清空模拟账户"(`resetSimAccount`) | 账户清零,二次确认逻辑(如果原来有)保持一致 |
| 赛果页 | 点击"刷新"(`loadResults`) | 赛果列表刷新 |
| 赛果页 | 翻页按钮(`setResultsPage`) | 分页正常切换,边界(第一页/最后一页)按钮禁用状态正确 |
| 计算器 | 点击某个盘口行(`selectCalculatorMarket`) | 该行被选中/取消选中 |
| 计算器 | 点击候选勾选按钮(`toggleCalculatorCandidate`) | 候选状态切换,且 `event.stopPropagation()` 仍然生效(点这个按钮不会同时触发外层行的 `selectCalculatorMarket`) |
| 计算器 | 点击具体赔率按钮(`toggleCalculatorSelection`) | 选中状态切换,同样验证不会冒泡触发外层 `onclick` |
| 计算器 | 点击"按预测选择"(`selectCalculatorPredictions`) | 按预测结果自动选中对应盘口 |
| 计算器 | 点击"模拟出票"(`renderCalculatorTickets`) | 出票列表渲染 |
| 计算器 | 点击"写入模拟盘"(`addCalculatorSelectionsToSim`) | 选中的串关写入模拟盘持仓 |
| 计算器 | 点击"清空"(`clearCalculatorSelections`) | 选中项清空 |
| 计算器 | 点击"同步模拟盘"(`syncSimBetsToCalculator`,这里是无参数版本) | 同步逻辑触发 |
| 计算器 | 点击"刷新官网数据"(`loadSportteryCalculator`) | 重新拉取体彩计算器数据 |
| 输入框联动 | 修改"本金"(`bankroll`)输入框 | 触发 `input`/`change` 两个监听器,模拟盘金额联动更新并保存 |
| 输入框联动 | 修改"串关次数"(`calcTimes`)/"过关方式"(`calcPassType`) | 计算器重新渲染 |
| AI 复核(不在 onclick 列表,但是是 JS 内部 `btn.onclick=` 绑定) | 点击某场比赛的"AI 复核"按钮(`runAiReview`) | 触发分析请求,行为同前 |
| AI 复核 | 点击某场比赛的"历史"按钮(`toggleHistory`) | 历史记录展开/收起 |

- [ ] **Step 4: 如果任何一项行为和重构前不一致**

回到对应的 `js/*.js` 文件,大概率是漏 import 了某个符号,或者漏挂了某个 `window.xxx`。修复后重新跑 Task 4 的核对脚本,再重新走一遍这一步的清单,不要跳过。

- [ ] **Step 5: 验证全部通过后,清理脚手架文件**

```bash
rm -rf scratch
git add -A
git commit -m "Remove scratch migration scripts after verifying frontend modularization"
```

---

### Task 7: 最终复查

- [ ] **Step 1: 确认没有引入任何新依赖**

Run: `git diff --stat 922dbda..HEAD -- server.py package.json package-lock.json`
Expected: 没有输出(说明这几个文件完全没被改动/创建,`server.py` 零改动,也没有引入任何 npm 相关文件)。

- [ ] **Step 2: 确认 index.html 体积变化符合预期**

Run: `wc -l index.html js/*.js`
Expected: `index.html` 行数大幅减少(原来 2592 行,现在应该只剩头部 HTML/CSS + 一行 `<script type="module">`),`js/` 目录下 8 个文件的总行数大致等于原来 `<script>` 块的 2147 行 + 新增的 import/export/window 挂载语句。

- [ ] **Step 3: 把验证清单存档**

把 Task 6 Step 3 的表格保存成 `docs/superpowers/plans/2026-06-17-frontend-js-modularization-verification-checklist.md`,作为这次重构"行为未变"的验证记录,提交到仓库。
