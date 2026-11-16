# 错题一键提问

日期：2026-11-16。只把已提交的错题接到现有聊天。答对的题没有按钮。练习里存的解析不放进问题。

## 提问

按钮在判定下面，文字是 Ask about this。点一次用这套练习保存的课件新建一个聊天，立刻发出一条消息，输入框保持空白。

英文练习写成：

```
Why is this choice wrong?

Question: {题干}
I chose {选错的字母和文字}
The correct option is {正确的字母和文字}

Explain the difference using the selected documents.
```

中文练习同样三段，问句是“为什么这个选择是错的？”，结尾是“请根据所选课件说明两者的差别。”

聊天消息最长 2000 字。超长时从题干末尾截掉并加上省略号。截完仍超长，就留在练习页，提示 “This question is too long to ask.”

## 交接

`GET /api/quizzes/{id}` 现在返回 `document_ids`。这些编号在创建练习时已经写进数据库，创建接口仍然只返回题干和选项。

练习页先核对这套练习的课件是否都还在。缺了就留在练习页，提示 “A selected document was deleted. This question cannot be asked.”，不打开聊天。都在时调用现有的创建聊天接口，把 `{conversationId, text}` 写入 `sessionStorage` 的 `coursemate.askOnce`，再打开 `/chat`。

聊天页加载时先读出这条记录并立刻删除，然后打开该聊天并调用现有的发送。刷新不会再发。朗读开关保持原来的行为：打开时从回答的第一句开始读。

## 核对

`backend/tests/test_quizzes.py` 的 `test_legal_quiz_hides_answers` 断言练习详情里的 `document_ids` 是创建时传入的 `["doc-1"]`，创建结果和详情里的题目仍然只有 `id`、`stem`、`options`。

在 Chrome 里打开 `http://127.0.0.1:5173/quiz`：

- Heuristic Search 已提交，分数是 2 / 3。两道正确题没有按钮，错题有一个 Ask about this。
- 点下去后进入新聊天。发出的问题包含题干 “What can cause issues in heuristic search according to the sources?”、`I chose B. The use of a search agent`，以及 `The correct option is A. The definition of the heuristic function h(n), since it is simply an estimation`。回答已经开始，并引用了课件。
- 刷新后仍是这一问一答，`coursemate.askOnce` 已经没有了。
- 另放一套课件编号不存在的练习再点按钮，页面停在 `/quiz`，并出现 “A selected document was deleted. This question cannot be asked.”。这套临时练习随后已删掉。
