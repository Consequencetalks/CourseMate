# Task 3 人工核对

日期：2026-11-15。资料是已导入的 `COMP4431_L2_2027.pdf`（`774d6008-14f8-49b9-857c-29ec55bdd8dc`）和 `Tut2_FriClass_2027.pdf`（`f598499e-4688-4453-bf60-27592ed24ffc`）。前 7 题在同一会话，后 3 题另开一个会话，避免上一题把检索带偏。DeepSeek 关闭 thinking，计时从发出问题到 SSE 结束。

课件按文本块切成很短的片段。答案如果散在同一页的多个小块里，前 5 个片段经常只含标题，不含定义。下面按检索到的原文判断引用是否支持回答。

## 1. 有依据：授课教师

- 问题：Who is the instructor named on the heuristic search lecture title slide, and which department and university are shown?
- 预期依据：L2 第 1 页，Raymond Pang，Department of Computing，The Hong Kong Polytechnic University。
- 耗时：1.51 秒
- 实际回答：无法确定。引用里只有 “Heuristic Search” 和 “COMP4431 Artificial Intelligence / Heuristic Search”，没有教师、院系和大学。
- 引用：L2 第 39、31、32、1 页，以及 Tut2 第 33 页的一个 Stanford 链接。第 1 页片段只有课程名和 Heuristic Search。
- 是否支持：引用支持“这些片段里没有教师姓名”。正确答案在标题页的后续小块里，没有进入前 5。

## 2. 追问：这一讲的题目

- 问题：What topic does that same title slide say the lecture covers?
- 预期依据：L2 第 1 页标题为 Heuristic Search。
- 耗时：1.02 秒
- 实际回答：The title slide says the lecture covers Heuristic Search。标注 [S1][S2][S3][S4]。
- 引用：S4 是 L2 第 1 页 “COMP4431 Artificial Intelligence / Heuristic Search”。S1 是第 39 页 “Heuristic Search”。S2、S3 是 “Issues of Heuristic Search”。
- 是否支持：S4 支持。S1–S3 只是相关标题，不是标题页。

## 3. 有依据：理性智能体

- 问题：According to the lecture, what is a rational agent?
- 预期依据：L2 第 5 页。理性智能体做正确的事，争取最好的结果。
- 耗时：1.10 秒
- 实际回答：无法确定。片段里只有 “Rational agent” / “Rational Agent”，没有定义。
- 引用：L2 第 33、2、3、7、5 页，原文都只是 “Rational agent” 或 “Rational Agent”。
- 是否支持：引用支持“片段里没有定义”。第 5 页的定义被切到别的块，没有进入前 5。

## 4. 有依据：A* 评价函数

- 问题：What is the A* evaluation function in the lecture, and what do g(n) and h(n) mean?
- 预期依据：L2 第 20 页。f(n) = g(n) + h(n)。g(n) 是到达 n 的已有代价，h(n) 是到目标的估计代价。
- 耗时：1.31 秒
- 实际回答：评价函数是 f(n) = g(n) + h(n)。片段没有定义 g(n) 和 h(n)，因此无法说明它们的含义。
- 引用：L2 第 20 页，“Evaluation function: f(n) = g(n) + h(n).”
- 是否支持：公式有依据。g(n)、h(n) 的定义在同一页的其他小块，没有被检索到；回答没有编造定义。

## 5. 追问：可采纳启发式

- 问题：When is a heuristic function admissible?
- 预期依据：L2 第 21 页。h(n) ≤ h*(n)，而且不会高估到目标的代价。
- 耗时：1.44 秒
- 实际回答：对每个节点 n，h(n) ≤ h*(n)，其中 h*(n) 是真实代价；可采纳启发式不会高估到达目标的代价。
- 引用：L2 第 21 页两段。一段是 “h(n) ≤ h*(n), where h*(n) is the true”。另一段是 “never overestimates the cost to reach the”。
- 是否支持：不等式和 never overestimates 都在引用里。句末被切开，回答补上了 cost 和 goal。

## 6. 有依据：latent diffusion 的三步

- 问题：In the image generation tutorial, what are the three steps of latent diffusion with text conditioning?
- 预期依据：Tut2 第 9 页。1 Compress，2 Denoise，3 Decode to pixels。
- 耗时：1.95 秒
- 实际回答：1 采样图像、噪声水平和噪声 ε；2 用 εθ 预测 ε；3 Decode to pixels。
- 引用：S5 是 Tut2 第 29 页，第三步写的是 “Minimize the squared prediction error”。S4 是第 9 页，含有 “3 Decode to pixels”，但同一页的前两步是 Compress 和 Denoise，没有进入这次引用。
- 是否支持：不支持。回答把第 29 页的训练步骤和第 9 页的 Decode to pixels 拼在一起，和第 29 页引用的第三步不一致。

## 7. 有依据：助教和学习目标

- 问题：Who is the TA of the generative AI image generation tutorial, and what are today's three learning goals?
- 预期依据：Tut2 第 1 页 TA 是 Zhuoyue WAN。第 2 页目标是 Explain、Compare、Follow。
- 耗时：0.97 秒
- 实际回答：无法确定，片段里没有助教姓名，也没有当天的三个学习目标。
- 引用：空。
- 是否支持：回答没有编造。预期内容在第 1–2 页，这次没有被检索到。

## 8. 资料未覆盖：期末考试日期

- 问题：What is the date of the COMP4431 final exam?
- 预期依据：两份课件都没有考试日期。
- 耗时：1.46 秒
- 实际回答：无法确定。
- 引用：L2 第 1 页，只有课程名和 Heuristic Search。
- 是否支持：引用里没有考试日期，回答没有编造日期。

## 9. 资料未覆盖：教材价格

- 问题：How much does the required textbook for this course cost?
- 预期依据：两份课件都没有教材价格。
- 耗时：1.01 秒
- 实际回答：无法确定。
- 引用：L2 第 1 页，只有课程名和 Heuristic Search。
- 是否支持：引用里没有价格，回答没有编造价格。

## 10. 资料未覆盖：世界杯

- 问题：Who won the 2022 FIFA World Cup?
- 预期依据：两份课件都没有这项内容。
- 耗时：1.11 秒
- 实际回答：无法确定。
- 引用：Tut2 第 13 页 “Nano Banana 2”，L2 第 32 页 “F / C”，L2 第 14 页 “16”。
- 是否支持：结论正确，回答没有编造冠军。这些引用和问题无关，只说明检索到的碎片里没有答案。

## 汇总

10 题都在 2 秒内返回，并写入了历史。引用能够支撑主要结论的是第 2、4、5 题。第 1、3、7 题课件里有答案，但前 5 个片段太碎，模型按检索结果说无法确定，没有编造。第 6 题把两页的步骤拼错，引用不支持。第 8–10 题都正确地说资料里没有答案。

## 浏览器

在聊天页勾选上述两份课件并新建会话。提问 A* 评价函数后，回答带有 L2 第 20 页来源卡，链接打开 `/api/documents/774d6008-14f8-49b9-857c-29ec55bdd8dc/file#page=20`。接着追问可采纳启发式，出现第 21 页两张来源卡。刷新后，同一会话的问题和回答还在。再点开考试日期那个历史会话，三条“无法确定”的记录也还在。
