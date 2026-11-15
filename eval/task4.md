# Task 4 人工核对

日期：2026-11-15。两套题都用英文生成。创建接口只返回题干和选项，答案和引用存在数据库里，提交后才出现。

## A* search and admissible heuristics

资料：`COMP4431_L2_2027.pdf`。耗时 2.37 秒。

1. 题干问可采纳启发式 h(n) 对每个节点必须满足什么。正确答案 B：h(n) ≤ h*(n)。引用是第 21 页 “h(n) ≤ h*(n), where h*(n) is the true”。不等式在引用里，支持。
2. 题干问可采纳启发式绝不会做什么。正确答案 B：高估到达目标的代价。引用是第 21 页 “never overestimates the cost to reach the”。支持，句子在片段末尾被切开。
3. 题干问哪个算法和可采纳启发式一起被讨论。正确答案 C：A* search。引用是第 20、39、25 页的 “A* Search” 和 “trace a case with A* algorithm”。这些片段只出现 A*，没有把 A* 和可采纳启发式连起来。解析提到了定义启发式的片段，但那些片段不在这题的引用里。部分支持。

## latent diffusion for image generation

资料：`Tut2_FriClass_2027.pdf`。耗时 2.33 秒。

1. 题干问像素在 latent diffusion 里变成什么。正确答案 B：变成 image latents。引用是第 9 页 “Pixels become image latents.”。支持。
2. 题干问去噪发生在哪里。正确答案 C：latent space。引用是第 5 页 “Denoise in latent space”。支持。
3. 题干问文字在这个过程里起什么作用。正确答案 B：引导反复的 latent 更新。引用是第 9 页 “Text guides repeated latent updates.”。支持。

## 汇总

6 题里 5 题的引用能支撑正确答案。A* 的第 3 题只引用了算法标题，没有引用可采纳启发式的定义。

浏览器里打开 A* 这套题，三题都选对后显示 Score: 3 / 3。单条引用直接显示，三条引用收成 Sources (3)，点开后是第 20、39、25 页的链接。点开第 20 页会打开 PDF。刷新后分数和已选答案还在。页面上再选 Tut2，用主题 image latent diffusion steps 生成，三题同时出现，提交前没有答案和解析。

## Heuristic Search（扩展同页正文之后）

资料：`COMP4431_L2_2027.pdf`。耗时 2.48 秒。这次没有返回材料不足。最近的页是第 39、31、32、1 页，所以题目来自第 31、32 页的正文，没有用到第 20、21 页的评价函数。

1. 题干问启发式不一定总能给出什么。正确答案 A：optimum choice。引用是第 31 页 “Heuristics may not always produce the” 和 “optimum choice”。两段拼起来支持。
2. 题干问启发式搜索有时会导向什么。正确答案 B：局部最优、次优解或死胡同。引用是第 31 页的 local minimum、2nd or 3rd best solution、dead end。支持。
3. 题干问什么会造成启发式搜索的问题。正确答案 A：h(n) 的定义只是估计。引用是第 32 页 “definition of a heuristic function h(n)” 和 “simply an estimation”。支持。
